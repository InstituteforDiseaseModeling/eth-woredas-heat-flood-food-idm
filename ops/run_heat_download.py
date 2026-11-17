# Databricks notebook source
# MAGIC %md
# MAGIC # Run the HeatReady download from our `-idm` projects
# MAGIC
# MAGIC **Purpose:** Pull the latest daily rows and the forecast from `eth-woreda-heat-1-idm` to `-6-idm` into the Volume (`build/raw/<project>/` and `build/forecast/`). This is the same code the daily job runs (`heat_api.py download final` and `heat_api.py forecast`), so use it for the first test and for manual re-runs.
# MAGIC
# MAGIC **What it does:**
# MAGIC - `download_final`: re-pulls the two latest months for each project. Older months are skipped because Andrew's original files already hold them (`build/raw/eth-woreda-heat-N-as2026/`). Writes `build/raw/eth-woreda-heat-N-idm/<month>.jsonl`.
# MAGIC - `forecast`: replaces `build/forecast/<project>.jsonl` with the forecast days now on the server.
# MAGIC - Andrew's files are never changed. Nothing is created or deleted on the HeatReady side.
# MAGIC
# MAGIC **API use:** about 20 to 60 `evaluate-heat-risk` calls in total (limit: 300 per hour). If the limit is hit, the script sleeps until the next hour.
# MAGIC
# MAGIC **Requirements:** secrets `heatready_username` and `heatready_key` in scope `ethiopia_climate`; the six `-idm` projects exist (notebook `create_heat_projects`).
# MAGIC
# MAGIC **How to run:** Choose `STEP`, then run all.
# MAGIC
# MAGIC ### Widgets
# MAGIC
# MAGIC | Label | Widget | Type (default) | What to enter |
# MAGIC |---|---|---|---|
# MAGIC | A | `STEP` | dropdown (`both`) | `download_final`, `forecast` or `both` |
# MAGIC
# MAGIC *Owner: IDM data management · Questions: jeremy.cooper@gatesfoundation.org · Last updated: 2026-11-11*

# COMMAND ----------

dbutils.widgets.dropdown("STEP", "both", ["download_final", "forecast", "both"], "A. Step")
STEP = dbutils.widgets.get("STEP").strip()
print("Step:", STEP)

# COMMAND ----------

import sys

PIPELINE = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/pipeline"
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

import heat_api

ids = [m["project_id"] for m in heat_api.manifest()]
assert all(i.endswith(heat_api.SUFFIX) and "as2026" not in i for i in ids), f"Unexpected project ids: {ids}"
print("Projects:", ids)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Download (two latest months)

# COMMAND ----------

if STEP in ("download_final", "both"):
    heat_api.cmd_download(final=True)
else:
    print("Skipped.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Forecast

# COMMAND ----------

if STEP in ("forecast", "both"):
    heat_api.cmd_forecast()
else:
    print("Skipped.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary: files written

# COMMAND ----------

import os
from datetime import datetime

for sub in ("raw", "forecast"):
    base = heat_api.BUILD / sub
    print(f"\n{sub}/")
    for p in sorted(base.glob("*idm*")):
        if p.is_dir():
            for f in sorted(p.glob("*.jsonl")):
                print(f"  {p.name}/{f.name}  {f.stat().st_size:,} bytes  {datetime.fromtimestamp(f.stat().st_mtime):%Y-%m-%d %H:%M}")
        else:
            print(f"  {p.name}  {p.stat().st_size:,} bytes  {datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}")