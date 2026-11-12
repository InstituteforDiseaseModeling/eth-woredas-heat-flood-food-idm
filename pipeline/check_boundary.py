# Databricks notebook source
# MAGIC %md
# MAGIC # Check the woreda boundary file against the downloaded heat data (read-only)
# MAGIC
# MAGIC **Purpose:** Confirm that `boundaries/OCHA_COD_AB/OCHA_COD_AB/eth_admin3.shp` is the layer the map pipeline expects, before `build_map_data.py` uses it.
# MAGIC
# MAGIC **Checks:**
# MAGIC 1. The file opens and has 1,148 features.
# MAGIC 2. It has the columns `adm3_pcode`, `adm3_name`, `adm2_name`, `adm1_name`, `area_sqkm`, and the pcodes are unique.
# MAGIC 3. The coordinate system is WGS84 (EPSG:4326).
# MAGIC 4. Every woreda name in Andrew's downloaded rows (October 2026, six projects) matches a pcode in the shapefile, and every pcode has data.
# MAGIC
# MAGIC **Changes nothing.** Reads only. No widgets, no secrets.
# MAGIC
# MAGIC *Owner: IDM data management · Questions: jeremy.cooper@gatesfoundation.org · Last updated: 2026-11-12*

# COMMAND ----------

# MAGIC %pip install geopandas

# COMMAND ----------

import sys

PIPELINE = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/pipeline"
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

import geopandas as gpd
import pandas as pd

import config

print("Shapefile:", config.SHP)
g = gpd.read_file(config.SHP)
print("features:", len(g), "| crs:", g.crs)

# COMMAND ----------

need = ["adm3_pcode", "adm3_name", "adm2_name", "adm1_name", "area_sqkm"]
missing = [c for c in need if c not in g.columns]
print("missing columns:", missing or "none")
print("unique pcodes:", g["adm3_pcode"].is_unique, "| null pcodes:", int(g["adm3_pcode"].isna().sum()))
print("regions:", g["adm1_name"].nunique(), "| zones:", g["adm2_name"].nunique(), "| woredas:", g["adm3_pcode"].nunique())
print("area_sqkm total:", round(float(g["area_sqkm"].sum())))

# COMMAND ----------

# Woreda names in Andrew's October 2026 rows (the polygon "name" is the OCHA pcode)
names = set()
for k in range(1, 7):
    p = config.BUILD / "raw" / f"eth-woreda-heat-{k}-as2026" / "2026-10.jsonl"
    names |= set(pd.read_json(p, lines=True)["name"].unique())

shp = set(g["adm3_pcode"])
print("woredas in downloaded data:", len(names))
print("in data but not in shapefile:", len(names - shp), sorted(names - shp)[:10])
print("in shapefile but not in data:", len(shp - names), sorted(shp - names)[:10])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

ok = (len(g) == 1148 and not missing and g["adm3_pcode"].is_unique
      and g.crs is not None and g.crs.to_epsg() == 4326 and names == shp)
print("RESULT:", "PASS. The boundary file matches the downloaded data." if ok else "CHECK the lines above.")