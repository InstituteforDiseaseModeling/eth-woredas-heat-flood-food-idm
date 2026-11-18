# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Write the imported data to Delta tables
# MAGIC
# MAGIC **Purpose:** Keep every data import of the Ethiopia woreda map as a Delta table in `idm_conflict_and_health.ethiopia_climate`, so it can be used for analyses beyond the map. Runs in the daily job after `build_map_data` and before `publish`.
# MAGIC
# MAGIC **Reads:** the files the pipeline stages already wrote to the Volume: `build/raw/*/*.jsonl` and `build/forecast/*.jsonl` (HeatReady), `build/flood/*.json` and `app/data/flood.js` (GloFAS), `app/data/rain.js` (CHIRPS), `build/food/eth_rtfp_mkt.csv` and `release.txt` (World Bank RTFP), `app/data/ethiomet.js` (EthioMet), `app/data/data.js` (monthly woreda metrics).
# MAGIC
# MAGIC **Writes (tables):**
# MAGIC
# MAGIC | Table | One row per | Update rule |
# MAGIC |---|---|---|
# MAGIC | `heat_daily` | woreda and day | upsert; the newest project file wins for the same woreda and day |
# MAGIC | `heat_forecast` | woreda, day and forecast issue time | append; past forecasts are kept |
# MAGIC | `flood_discharge` | gauge and day (1997 to now) | upsert; revised values update in place |
# MAGIC | `flood_forecast` | gauge, day and fetch time | append; past forecasts are kept |
# MAGIC | `flood_gauges` | gauge | upsert |
# MAGIC | `rainfall_dekad` | woreda and dekad | upsert; preliminary values are replaced by final ones |
# MAGIC | `rainfall_dekad_catchment` | gauge catchment and dekad | upsert |
# MAGIC | `food_prices` | market, month and commodity columns (RTFP market file) | replaced when a new RTFP release is downloaded; earlier releases stay in Delta history |
# MAGIC | `ethiomet_bulletin` | bulletin, product and forecast day | upsert |
# MAGIC | `woreda_monthly_metrics` | woreda and month | upsert |
# MAGIC | `woreda_attributes` | woreda | upsert (population, age shares, names) |
# MAGIC | `woreda_metric_definitions` | metric | upsert (label, unit, description of each metric) |
# MAGIC
# MAGIC Every table has `loaded_at` (when the row was last written) and `row_hash` (used to skip unchanged rows). Woredas are identified by `adm3_pcode`, the OCHA admin-3 code.
# MAGIC
# MAGIC **Requirements:** the earlier job stages have run, so the files above exist. Serverless or any cluster with Unity Catalog write access to the schema.
# MAGIC
# MAGIC **How to run:** Run all with `DRY_RUN` = `true` first: it reads and counts everything and writes nothing. Then run with `DRY_RUN` = `false`. A table that fails prints a WARNING and the notebook carries on, so a table problem never blocks `publish`. The last cell lists each table's result.
# MAGIC
# MAGIC ### Widgets
# MAGIC
# MAGIC | Label | Widget | Type (default) | What to enter |
# MAGIC |---|---|---|---|
# MAGIC | A | `DRY_RUN` | dropdown (`true`) | `true` = read and count only; `false` = write the tables |
# MAGIC | B | `TABLES` | text (`all`) | `all`, or table names separated by commas (for example `heat_daily,flood_discharge`) |
# MAGIC
# MAGIC *Owner: IDM data management · Last updated: 2026-11-17*

# COMMAND ----------

dbutils.widgets.dropdown("DRY_RUN", "true", ["true", "false"], "A. Dry run")
dbutils.widgets.text("TABLES", "all", "B. Tables")
DRY_RUN = dbutils.widgets.get("DRY_RUN") == "true"
TABLES = dbutils.widgets.get("TABLES").strip()
print("Dry run:", DRY_RUN, "| Tables:", TABLES)

# COMMAND ----------

import json
import re
import sys
from datetime import date

PIPELINE = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/pipeline"
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

import numpy as np
import pandas as pd
from pyspark.sql import Window
from pyspark.sql import functions as F

import config

CATALOG, SCHEMA = "idm_conflict_and_health", "ethiopia_climate"
BUILD, APP = config.BUILD, config.APP

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helpers

# COMMAND ----------

def fq(name):
    return f"{CATALOG}.{SCHEMA}.{name}"


def read_js(path):
    """Read a `window.NAME = {...};` data file of the map as a dict."""
    text = path.read_text(encoding="utf-8").strip()
    text = re.sub(r"^window\.\w+\s*=\s*", "", text).rstrip(";")
    return json.loads(text)


def clean(sdf):
    """Turn NaN into null in numeric columns."""
    for c, t in sdf.dtypes:
        if t in ("double", "float"):
            sdf = sdf.withColumn(c, F.when(F.isnan(c), F.lit(None)).otherwise(F.col(c)))
    return sdf


def prepare(sdf, keys):
    sdf = clean(sdf)
    vals = [c for c in sdf.columns if c not in keys]
    sdf = sdf.withColumn("row_hash", F.xxhash64(*[F.col(c).cast("string") for c in vals]))
    return sdf.withColumn("loaded_at", F.current_timestamp())


def describe(name, sdf, note=""):
    print(f"{name}: {sdf.count():,} rows, {len(sdf.columns)} columns {note}")
    print("  " + ", ".join(sdf.columns[:12]) + (" ..." if len(sdf.columns) > 12 else ""))


def upsert(name, sdf, keys, update=True, comment=None):
    """Create the table, or merge into it. update=False only inserts keys not yet in the table."""
    sdf = prepare(sdf, keys)
    dup = sdf.groupBy(*keys).count().filter("count > 1").count()
    if dup:
        raise RuntimeError(f"{name}: {dup} duplicate keys in the source ({', '.join(keys)})")
    full = fq(name)
    if DRY_RUN:
        describe(name, sdf, "(dry run: nothing written)")
        return {"table": name, "rows": sdf.count(), "action": "dry run"}
    if not spark.catalog.tableExists(full):
        sdf.write.format("delta").saveAsTable(full)
        action = "created"
    else:
        sdf.createOrReplaceTempView("_src")
        cond = " AND ".join(f"t.`{k}` <=> s.`{k}`" for k in keys)
        # WITH SCHEMA EVOLUTION: a new column in a source (for example a new HeatReady metric) is added to the table.
        sql = f"MERGE WITH SCHEMA EVOLUTION INTO {full} t USING _src s ON {cond} "
        if update:
            sql += "WHEN MATCHED AND t.row_hash <> s.row_hash THEN UPDATE SET * "
        sql += "WHEN NOT MATCHED THEN INSERT *"
        spark.sql(sql)
        action = "merged"
    if comment:
        spark.sql(f"COMMENT ON TABLE {full} IS '{comment}'")
    n = spark.table(full).count()
    print(f"{name}: {action}, {n:,} rows in the table")
    return {"table": name, "rows": n, "action": action}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Table builders

# COMMAND ----------

def t_heat_daily():
    raw = f"{BUILD}/raw/*/*.jsonl"
    df = spark.read.json(raw).select("*", F.col("_metadata.file_path").alias("src_file"))
    df = df.withColumn("date", F.to_date("date")).filter(F.col("date") >= "2023-06-01")
    # Same rule as build_map_data: files sorted by path, the last row for a woreda and day wins.
    w = Window.partitionBy("name", "date").orderBy(F.col("src_file").desc())
    df = df.withColumn("_rn", F.row_number().over(w)).filter("_rn = 1").drop("_rn")
    df = df.withColumn("project", F.regexp_extract("src_file", r"/raw/([^/]+)/", 1)).drop("src_file")
    df = df.withColumnRenamed("name", "adm3_pcode")
    return upsert("heat_daily", df, ["adm3_pcode", "date"],
                  comment="Daily HeatReady heat metrics per Ethiopian woreda (adm3_pcode), June 2023 onward. Temperatures in degrees C, heat index in degrees F. data_source: era5 is final, anything else is provisional.")


def t_heat_forecast():
    df = spark.read.json(f"{BUILD}/forecast/*.jsonl")
    df = (df.withColumn("date", F.to_date("date"))
            .withColumn("forecast_issued_at", F.col("forecast_issued_at").cast("timestamp"))
            .withColumnRenamed("name", "adm3_pcode"))
    return upsert("heat_forecast", df, ["adm3_pcode", "date", "forecast_issued_at"], update=False,
                  comment="Six-day HeatReady forecast per woreda. Every forecast issue is kept, so past forecasts can be compared with later observations in heat_daily.")


def _flood_files():
    skip = {"cells.json", "ocha_dashboard.json"}
    return [p for p in sorted((BUILD / "flood").glob("*.json")) if p.name not in skip]


def t_flood_discharge():
    parts = []
    for p in _flood_files():
        raw = json.loads(p.read_text())
        q = np.array(raw["hist"]["q"], dtype=float)
        d = pd.DataFrame({"gauge_id": p.stem, "date": pd.to_datetime(raw["hist"]["date"]).date, "discharge_m3s": q})
        parts.append(d.dropna(subset=["discharge_m3s"]))
    df = spark.createDataFrame(pd.concat(parts, ignore_index=True))
    return upsert("flood_discharge", df, ["gauge_id", "date"],
                  comment="Daily river discharge (m3/s) at the 14 OCHA flood-monitoring gauges, 1997 to now (the source has no values for 1984-1996). GloFAS v4 reanalysis served by Open-Meteo.")


def t_flood_forecast():
    parts = []
    for p in _flood_files():
        raw = json.loads(p.read_text())
        d = pd.DataFrame(raw["fc"])
        d["date"] = pd.to_datetime(d["date"]).dt.date
        d = d.rename(columns={"river_discharge": "discharge_m3s", "river_discharge_median": "median_m3s",
                              "river_discharge_p25": "p25_m3s", "river_discharge_p75": "p75_m3s",
                              "river_discharge_min": "min_m3s", "river_discharge_max": "max_m3s"})
        d.insert(0, "gauge_id", p.stem)
        d["fetched_at"] = pd.to_datetime(raw["fetched"]).tz_convert("UTC").tz_localize(None)
        parts.append(d)
    df = spark.createDataFrame(pd.concat(parts, ignore_index=True))
    return upsert("flood_forecast", df, ["gauge_id", "date", "fetched_at"], update=False,
                  comment="30-day GloFAS ensemble forecast of river discharge (m3/s) per gauge. Every fetch is kept (fetched_at, UTC).")


def t_flood_gauges():
    flood = read_js(APP / "data" / "flood.js")
    pcodes = [w["pcode"] for w in read_js(APP / "data" / "data.js")["woredas"]]
    rows = []
    for s in flood["stations"]:
        rows.append({
            "gauge_id": s["id"], "label": s["label"], "river": s["river"], "zone": s["zone"],
            "lat": float(s["lat"]), "lon": float(s["lon"]),
            "trigger_level_m3s": None if s.get("trigger") is None else float(s["trigger"]),
            "rp2_m3s": s["rp"].get("2"), "rp5_m3s": s["rp"].get("5"), "rp10_m3s": s["rp"].get("10"),
            "peak_year": s["max_year"], "peak_m3s": s["max_q"],
            "woreda_pcode": None if s.get("woreda") is None else pcodes[s["woreda"]],
            "zone_woreda_pcodes": ",".join(pcodes[i] for i in s["zone_idx"]),
            "grid_cell_lat": float(s["cell"][0]), "grid_cell_lon": float(s["cell"][1]),
            "grid_match_error": float(s["match"]),
        })
    df = spark.createDataFrame(pd.DataFrame(rows))
    return upsert("flood_gauges", df, ["gauge_id"],
                  comment="The 14 OCHA flood-monitoring gauges: location, trigger level, 2/5/10-year return levels (Gumbel fit to annual peaks; the discharge series starts in 1997) and the woredas at risk.")


def _dekad_start(k):
    y, m, d = int(k[:4]), int(k[5:7]), int(k[8])
    return date(y, m, (1, 11, 21)[d - 1])


def t_rainfall():
    rain = read_js(APP / "data" / "rain.js")
    pcodes = [w["pcode"] for w in read_js(APP / "data" / "data.js")["woredas"]]
    dek, prelim = rain["dekads"], np.array(rain["prelim"], dtype=bool)
    T, P = len(dek), len(pcodes)
    arr = lambda k: np.array(rain["woreda"][k], dtype=float).ravel()
    df = pd.DataFrame({
        "adm3_pcode": np.tile(pcodes, T), "dekad": np.repeat(dek, P),
        "dekad_start": np.repeat([_dekad_start(k) for k in dek], P),
        "rain_mm": arr("mm"), "pct_of_normal": arr("pct"), "percentile_rank": arr("rank"),
        "is_prelim": np.repeat(prelim, P),
    })
    res = [upsert("rainfall_dekad", spark.createDataFrame(df), ["adm3_pcode", "dekad"],
                  comment="CHIRPS v3 rainfall per woreda and 10-day dekad (dekad 2026.11.1 = days 1-10 of November 2026). pct_of_normal and percentile_rank compare with 1991-2020. is_prelim = preliminary product, replaced by the final one 4 to 6 weeks later.")]
    stations = read_js(APP / "data" / "flood.js")["stations"]
    parts = []
    for gk, g in rain["gauges"].items():
        i = int(gk)
        gid = stations[i]["id"] if i < len(stations) else str(gk)
        parts.append(pd.DataFrame({
            "gauge_id": gid, "dekad": dek, "dekad_start": [_dekad_start(k) for k in dek],
            "rain_mm": np.array(g["mm"], dtype=float), "normal_mm": np.array(g["normal"], dtype=float),
            "pct_of_normal": np.array(g["pct"], dtype=float), "percentile_rank": np.array(g["rank"], dtype=float),
            "is_prelim": prelim, "catchment_area_km2": float(g["area_km2"]),
        }))
    res.append(upsert("rainfall_dekad_catchment", spark.createDataFrame(pd.concat(parts, ignore_index=True)),
                      ["gauge_id", "dekad"],
                      comment="CHIRPS v3 rainfall averaged over the upstream catchment of each flood gauge, per dekad."))
    return res


def t_food_prices():
    release = (BUILD / "food" / "release.txt").read_text().strip()
    df = spark.read.csv(str(BUILD / "food" / "eth_rtfp_mkt.csv"), header=True, inferSchema=True)
    df = df.withColumn("price_date", F.to_date("price_date")).withColumn("rtfp_release", F.lit(release))
    full = fq("food_prices")
    have = None
    if spark.catalog.tableExists(full):
        have = spark.table(full).agg(F.max("rtfp_release")).first()[0]
    if DRY_RUN:
        describe("food_prices", df, f"| release {release}, table has {have}")
        return {"table": "food_prices", "rows": df.count(), "action": "dry run"}
    if have == release:
        n = spark.table(full).count()
        print(f"food_prices: release {release} already loaded, {n:,} rows")
        return {"table": "food_prices", "rows": n, "action": "unchanged"}
    (df.withColumn("loaded_at", F.current_timestamp()).write.format("delta")
       .mode("overwrite").option("overwriteSchema", "true").saveAsTable(full))
    spark.sql(f"COMMENT ON TABLE {full} IS 'World Bank Real-Time Food Prices, Ethiopia market file (all markets and the national Market Average). Replaced when a new release is published; earlier releases are in the Delta history (rtfp_release column).'")
    n = spark.table(full).count()
    print(f"food_prices: loaded release {release} (had {have}), {n:,} rows")
    return {"table": "food_prices", "rows": n, "action": "replaced"}


def t_ethiomet():
    em = read_js(APP / "data" / "ethiomet.js")
    rows = []
    for pr in em["products"]:
        for d in pr["days"]:
            rows.append({
                "bulletin_url": em["url"], "bulletin_title": em["title"],
                "bulletin_start": pd.to_datetime(em["start"]).date(), "bulletin_end": pd.to_datetime(em["end"]).date(),
                "product": pr["name"], "product_group": pr["group"],
                "day_from": pd.to_datetime(d["from"]).date(), "day_to": pd.to_datetime(d["to"]).date(),
                "image_url": d.get("img"), "forecast_text": d.get("text"),
                "fetched_at": pd.to_datetime(em["fetched"]).tz_convert("UTC").tz_localize(None),
            })
    df = spark.createDataFrame(pd.DataFrame(rows))
    return upsert("ethiomet_bulletin", df, ["bulletin_url", "product", "day_from"],
                  comment="Ethiopian Meteorology Institute daily numerical weather prediction bulletin: forecast text and map image link per product and day. Not joined to woredas.")


def t_woreda_metrics():
    data = read_js(APP / "data" / "data.js")
    months, wor = data["months"], data["woredas"]
    pc = [w["pcode"] for w in wor]
    M, P = len(months), len(pc)
    partial = (data.get("partial") or {}).get("month")
    cols = {"adm3_pcode": np.tile(pc, M), "month": np.repeat(months, P)}
    for key, spec in data["metrics"].items():
        if spec["temporal"]:
            cols[key] = np.array(spec["values"], dtype=float).ravel()
    cols["is_partial_month"] = np.repeat([m == partial for m in months], P)
    cols["provisional_share"] = np.repeat(np.array(data["provisional_share"], dtype=float), P)
    res = [upsert("woreda_monthly_metrics", spark.createDataFrame(pd.DataFrame(cols)), ["adm3_pcode", "month"],
                  comment="Monthly heat metrics and exposure per woreda, as shown on the map (see woreda_metric_definitions). The current month is flagged is_partial_month (month to date).")]
    attrs = {"adm3_pcode": pc, "adm3_name": [w["name"] for w in wor], "zone": [w["zone"] for w in wor],
             "region": [w["region"] for w in wor]}
    for key, spec in data["metrics"].items():
        if not spec["temporal"] and spec["group"] in ("Population", "Age"):
            attrs[key] = np.array(spec["values"], dtype=float)
    res.append(upsert("woreda_attributes", spark.createDataFrame(pd.DataFrame(attrs)), ["adm3_pcode"],
                      comment="Woreda names (OCHA COD-AB) with population (LandScan 2024) and age structure (WorldPop R2025A)."))
    defs = [{"metric": k, "label": s["label"], "unit": s["unit"], "description": s["desc"], "metric_group": s["group"],
             "is_monthly": bool(s["temporal"])} for k, s in data["metrics"].items()]
    res.append(upsert("woreda_metric_definitions", spark.createDataFrame(pd.DataFrame(defs)), ["metric"],
                      comment="Label, unit and description of each metric on the map."))
    return res

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run

# COMMAND ----------

BUILDERS = {
    "heat_daily": t_heat_daily, "heat_forecast": t_heat_forecast,
    "flood_discharge": t_flood_discharge, "flood_forecast": t_flood_forecast, "flood_gauges": t_flood_gauges,
    "rainfall": t_rainfall, "food_prices": t_food_prices, "ethiomet_bulletin": t_ethiomet,
    "woreda_metrics": t_woreda_metrics,
}
wanted = list(BUILDERS) if TABLES.lower() == "all" else [t.strip() for t in TABLES.split(",") if t.strip()]
unknown = [t for t in wanted if t not in BUILDERS]
if unknown:
    raise ValueError(f"Unknown TABLES {unknown}; choose from {list(BUILDERS)}")

results, failed = [], []
for name in wanted:
    try:
        out = BUILDERS[name]()
        results.extend(out if isinstance(out, list) else [out])
    except Exception as e:
        failed.append(name)
        print(f"WARNING: {name} failed: {type(e).__name__}: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print(f"{'DRY RUN' if DRY_RUN else 'WRITE'}: {len(results)} tables ok, {len(failed)} failed")
for r in results:
    print(f"  {r['table']:28} {r['rows']:>12,} rows  {r['action']}")
if failed:
    print("FAILED (previous table contents unchanged):", ", ".join(failed))