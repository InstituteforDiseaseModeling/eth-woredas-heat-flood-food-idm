# Databricks notebook source
# MAGIC %md
# MAGIC # Run the whole daily refresh from a notebook (stand-in for the job)
# MAGIC
# MAGIC **Purpose:** Run every stage of the Ethiopia woreda map pipeline in order, with the same rules as `job_daily_refresh.json`, so the full pipeline can be tested before the Lakeflow job exists. It does not publish to GitHub and does not write the Delta tables (the job's `publish` and `delta_tables` tasks do that).
# MAGIC
# MAGIC **Stages and rules (same as the job):**
# MAGIC 1. `setup_site`: copy the site files into the Volume's `app/`.
# MAGIC 1b. `oni`: soft. Download NOAA's Oceanic Nino Index (El Nino flags); a failure keeps the previous file.
# MAGIC 2. `heat_download`: re-pull the two latest months from HeatReady. One retry after 10 minutes.
# MAGIC 3. `heat_forecast`: pull the forecast days. One retry. Runs even if the download failed.
# MAGIC 4. `build_map_data`: runs the notebook `build_map_data`. Runs even if the heat steps failed (it uses what is on disk).
# MAGIC 5. `flood_gauges`: One retry after 2 minutes. Skipped if `build_map_data` failed.
# MAGIC 6. `food_prices`: runs the notebook `food_prices` with `COMMAND` = `update` (downloads the newest World Bank release if there is one). Skipped if `flood_gauges` failed.
# MAGIC 7. `rainfall` (CHIRPS, slow) and 8. `ethiomet`: soft. A failure prints a warning and keeps the previous file. Skipped if `food_prices` failed.
# MAGIC
# MAGIC **What it changes:** Files in the Volume under `build/` and `app/`. It does not touch GitHub. It calls HeatReady, Open-Meteo, World Bank, CHIRPS and EthioMet.
# MAGIC
# MAGIC **How to run:**
# MAGIC 1. Run all with `DRY_RUN` = `true` to see the plan.
# MAGIC 2. Set `DRY_RUN` to `false` and run again. Use `STAGES` to run a single stage; a stage you did not select never blocks the one you did.
# MAGIC 3. Read the summary table at the bottom. The notebook ends with an error if a required stage failed.
# MAGIC
# MAGIC ### Widgets
# MAGIC
# MAGIC | Label | Widget | Type (default) | What to enter |
# MAGIC |---|---|---|---|
# MAGIC | A | `DRY_RUN` | dropdown (`true`) | `true` = print the plan only; `false` = run |
# MAGIC | B | `STAGES` | dropdown (`all`) | `all` for the whole pipeline, or one stage |
# MAGIC
# MAGIC *Owner: IDM data management · Questions: jeremy.cooper@gatesfoundation.org · Last updated: 2026-11-17*

# COMMAND ----------

# MAGIC %pip install requests pandas numpy scipy geopandas shapely rasterio

# COMMAND ----------

ALL = ["setup_site", "oni", "heat_download", "heat_forecast", "build_map_data", "flood_gauges", "food_prices", "rainfall", "ethiomet"]
dbutils.widgets.dropdown("DRY_RUN", "true", ["true", "false"], "A. Dry run (true = plan only)")
dbutils.widgets.dropdown("STAGES", "all", ["all"] + ALL, "B. Stage (all = whole pipeline)")
choice = dbutils.widgets.get("STAGES").strip()
chosen = ALL if choice == "all" else [choice]
DRY_RUN = dbutils.widgets.get("DRY_RUN").strip().lower() == "true"
print("DRY RUN (nothing executed)" if DRY_RUN else "LIVE")
print("Selected:", chosen)

# COMMAND ----------

import os
import runpy
import sys
import time
import traceback
from datetime import datetime

PIPELINE = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/pipeline"
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)
os.chdir(PIPELINE)

import config

# stage: (kind, target, args, retries, retry_wait_s, soft, depends_on, run_even_if_dep_failed)
STAGES = {
    "setup_site":     ("script",   "setup_site.py",   [],                  0, 0,   False, [],                False),
    "oni":            ("script",   "oni.py",         [],                  0, 0,   True,  ["setup_site"],     False),
    "heat_download":  ("script",   "heat_api.py",     ["download", "final"], 1, 600, False, ["setup_site"],     False),
    "heat_forecast":  ("script",   "heat_api.py",     ["forecast"],        1, 600, False, ["heat_download"],  True),
    "build_map_data": ("notebook", "build_map_data",  [],                  0, 0,   False, ["heat_forecast"],  True),
    "flood_gauges":   ("script",   "flood_gauges.py", ["all"],             1, 120, False, ["build_map_data"], False),
    "food_prices":    ("notebook", "food_prices",     ["update"],          0, 0,   False, ["flood_gauges"],   False),
    "rainfall":       ("script",   "chirps.py",       ["all"],             0, 0,   True,  ["food_prices"],    False),
    "ethiomet":       ("script",   "ethiomet.py",     [],                  0, 0,   True,  ["food_prices"],    False),
}


def run_once(kind, target, args):
    if kind == "notebook":
        dbutils.notebook.run(f"{PIPELINE}/{target}", 3600, {"COMMAND": args[0]} if args else {})
        return
    sys.argv = [target, *args]
    try:
        runpy.run_path(os.path.join(PIPELINE, target), run_name="__main__")
    except SystemExit as e:
        if e.code not in (None, 0):
            raise RuntimeError(f"{target} exited with code {e.code}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run

# COMMAND ----------

results = {}   # stage -> (status, seconds, note)

for name in ALL:
    kind, target, args, retries, wait, soft, deps, even_if_failed = STAGES[name]
    if name not in chosen:
        results[name] = ("not selected", 0, "")
        continue
    bad = [d for d in deps if results.get(d, ("", 0, ""))[0] in ("FAILED", "skipped")]
    if bad and not even_if_failed:
        results[name] = ("skipped", 0, f"depends on {', '.join(bad)}")
        print(f"[{name}] skipped: {', '.join(bad)} did not succeed")
        continue
    label = f"{target} {' '.join(args)}".strip()
    if DRY_RUN:
        results[name] = ("planned", 0, f"{kind}: {label}" + (f" | retries {retries}" if retries else "") + (" | soft" if soft else ""))
        print(f"[{name}] would run {label}")
        continue

    t0 = time.time()
    status, note = "FAILED", ""
    for attempt in range(retries + 1):
        try:
            print(f"\n[{name}] {datetime.now():%H:%M:%S} start (attempt {attempt + 1}) {label}")
            run_once(kind, target, args)
            status, note = "ok", ""
            break
        except Exception as e:
            note = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"[{name}] error: {note}")
            traceback.print_exc()
            if attempt < retries:
                print(f"[{name}] retrying in {wait}s")
                time.sleep(wait)
    if status == "FAILED" and soft:
        status = "warning"
        print(f"[{name}] WARNING: soft stage failed; the previous output file is kept.")
    results[name] = (status, int(time.time() - t0), note)
    print(f"[{name}] {status} in {int(time.time() - t0)}s")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print(f"{'stage':16}{'status':14}{'seconds':>8}  note")
for name in ALL:
    status, secs, note = results[name]
    print(f"{name:16}{status:14}{secs:>8}  {note}")

required_failed = [n for n, (s, _, _) in results.items() if s == "FAILED"]
if required_failed:
    raise RuntimeError(f"Required stage(s) failed: {', '.join(required_failed)}")
print("\nDone. Nothing was published and no Delta tables were written (run publish_pages and write_delta_tables for that).")