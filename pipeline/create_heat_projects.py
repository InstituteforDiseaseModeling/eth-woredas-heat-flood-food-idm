# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Create our own copies of the six Ethiopia woreda HeatReady projects
# MAGIC
# MAGIC **Purpose:** Create `eth-woreda-heat-1-idm` to `eth-woreda-heat-6-idm` under our own HeatReady account, from the same polygon files Andrew used (`build/projects/*.geojson`). The projects `eth-woreda-heat-N-as2026` belong to Andrew's account and are not visible to ours.
# MAGIC
# MAGIC **What it does:** For each project it checks whether it already exists (`get-project-status`, no rate limit). If not, and `DRY_RUN` is `false`, it sends the polygons with `evaluate-heat-risk` (6 calls, counted against the 300 calls/hour limit). The API then extracts population and downloads ERA5 in the background. The notebook waits and prints each project's `start` date once it is ready. Nothing is backfilled here.
# MAGIC
# MAGIC **Safe to re-run:** existing projects are skipped. If the wait takes too long, stop the notebook and run it again later; it picks up where it left off.
# MAGIC
# MAGIC **Requirements:** secrets `heatready_username` and `heatready_key` in scope `ethiopia_climate`; the Volume `build/projects/` folder with the six geojson files and `manifest.json`.
# MAGIC
# MAGIC **How to run:**
# MAGIC 1. Run all with `DRY_RUN` = `true`. It lists the projects and says which already exist.
# MAGIC 2. Set `DRY_RUN` to `false` and run again to create them.
# MAGIC
# MAGIC ### Widgets
# MAGIC
# MAGIC | Label | Widget | Type (default) | What to enter |
# MAGIC |---|---|---|---|
# MAGIC | A | `DRY_RUN` | dropdown (`true`) | `true` = report only; `false` = create the missing projects |
# MAGIC
# MAGIC *Owner: IDM data management · Questions: jeremy.cooper@gatesfoundation.org · Last updated: 2026-11-11*

# COMMAND ----------

dbutils.widgets.dropdown("DRY_RUN", "true", ["true", "false"], "A. Dry run (true = report only)")
DRY_RUN = dbutils.widgets.get("DRY_RUN").strip().lower() == "true"
print("DRY RUN (no projects created)" if DRY_RUN else "LIVE: missing projects will be created")

# COMMAND ----------

import os
import sys

PIPELINE = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/pipeline"
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

import heat_api   # reads the credentials from the secret scope; nothing is printed

print("Project ids:", [m["project_id"] for m in heat_api.manifest()])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Current state

# COMMAND ----------

todo = []
for m in heat_api.manifest():
    s = heat_api.status(m["project_id"])
    exists = s["_status"] == 200
    print(f"{m['project_id']:28} polygons in file: {m['n']:4}  exists: {exists}  "
          f"status: {s['_status']}" + (f"  start: {s.get('start')}  polygons: {s.get('polygon_count')}" if exists else ""))
    if not exists:
        todo.append(m["project_id"])
print(f"\n{len(todo)} project(s) to create.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create the missing projects

# COMMAND ----------

if DRY_RUN:
    print("[DRY RUN] Would create:", todo or "nothing")
elif not todo:
    print("Nothing to create. All six projects exist.")
else:
    heat_api.cmd_create()   # skips projects that exist; waits until each has a start date

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

if DRY_RUN:
    print(f"Dry run complete: {len(todo)} to create. Set DRY_RUN to false and run again to create them.")
else:
    heat_api.cmd_status()