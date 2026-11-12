# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Run one pipeline stage by hand (for testing)
# MAGIC
# MAGIC **Purpose:** Run a single stage of the Ethiopia woreda map pipeline from a notebook, using the same scripts and arguments as the daily job. Use it to test each stage before the job runs unattended. All paths, projects and secrets come from `config.py`.
# MAGIC
# MAGIC **Stages (run in this order the first time):**
# MAGIC 1. `setup_site`: copy `index.html`, `app.js`, `style.css`, `.nojekyll` into the Volume's `app/`. Needs the folder `local_scripts/app`.
# MAGIC 2. (`build_map_data` is a notebook of its own: run the notebook `build_map_data` directly at this point.)
# MAGIC 3. `flood_gauges`: GloFAS river discharge for the 14 gauges -> `app/data/flood.js`. Needs internet access to Open-Meteo.
# MAGIC 4. `food_prices`: World Bank food prices linked to the new months -> `app/data/food.js`.
# MAGIC 5. `rainfall`: CHIRPS rainfall -> `app/data/rain.js`. Needs `app/data/rivers.js` and internet access to CHC UCSB. Slow.
# MAGIC 6. `ethiomet`: latest EthioMet bulletin -> `app/data/ethiomet.js`. Needs internet access to the EthioMet site.
# MAGIC
# MAGIC **What it changes:** Only files under the Volume's `app/` (and `build/` caches the scripts use). It does not publish anything and does not touch HeatReady.
# MAGIC
# MAGIC **How to run:** Choose `STAGE`, run all. A summary at the bottom lists the files in `app/` with sizes and times.
# MAGIC
# MAGIC ### Widgets
# MAGIC
# MAGIC | Label | Widget | Type (default) | What to enter |
# MAGIC |---|---|---|---|
# MAGIC | A | `STAGE` | dropdown (`setup_site`) | the stage to run (list above) |
# MAGIC
# MAGIC *Owner: IDM data management · Questions: jeremy.cooper@gatesfoundation.org · Last updated: 2026-11-12*

# COMMAND ----------

STAGES = {
    # stage: (script, arguments) exactly as in job_daily_refresh.json
    "setup_site":     ("setup_site.py", []),
    "flood_gauges":   ("flood_gauges.py", ["all"]),
    "food_prices":    ("food_prices.py", ["build"]),
    "rainfall":       ("chirps.py", ["all"]),
    "ethiomet":       ("ethiomet.py", []),
}
dbutils.widgets.dropdown("STAGE", "setup_site", list(STAGES), "A. Stage")
STAGE = dbutils.widgets.get("STAGE").strip()
SCRIPT, ARGS = STAGES[STAGE]
print(f"Stage: {STAGE} -> python {SCRIPT} {' '.join(ARGS)}")

# COMMAND ----------

import os
import runpy
import sys
import time
from datetime import datetime

PIPELINE = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/pipeline"
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)
os.chdir(PIPELINE)

import config

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run the stage

# COMMAND ----------

t0 = time.time()
sys.argv = [SCRIPT, *ARGS]
try:
    runpy.run_path(os.path.join(PIPELINE, SCRIPT), run_name="__main__")
    outcome = "finished"
except SystemExit as e:
    outcome = "finished" if e.code in (None, 0) else f"exited with code {e.code}"
print(f"\n{STAGE} {outcome} in {time.time() - t0:.0f}s")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary: files in app/

# COMMAND ----------

for p in sorted(config.APP.rglob("*")):
    if p.is_file():
        print(f"{str(p.relative_to(config.APP)):22} {p.stat().st_size:>12,} bytes  {datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}")