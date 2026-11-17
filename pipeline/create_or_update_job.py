# Databricks notebook source
# MAGIC %md
# MAGIC # create_or_update_job
# MAGIC
# MAGIC Creates the Lakeflow job "Ethiopia woreda climate map: daily refresh" from `pipeline/job_daily_refresh.json`,
# MAGIC or updates it if a job with that name already exists. The JSON file in the repo is the source of truth: rerun this notebook after the file changes.
# MAGIC
# MAGIC It checks the file first (no placeholders left, every notebook and script path exists) and, with `DRY_RUN` true, only prints the plan.
# MAGIC
# MAGIC | Widget | Name | Default | Meaning |
# MAGIC |---|---|---|---|
# MAGIC | A | `DRY_RUN` | `true` | `true` = checks and plan only; `false` = create or update the job |
# MAGIC | B | `SCHEDULE` | `keep` | `keep` = new job uses the file's value (paused), an existing job keeps its current state; `paused` = pause it; `active` = switch the daily schedule on |
# MAGIC
# MAGIC The job runs `publish_pages` live, so a run of the job publishes the site.
# MAGIC
# MAGIC *Owner: IDM data management · Questions: jeremy.cooper@gatesfoundation.org · Last updated: 2026-11-16*

# COMMAND ----------

dbutils.widgets.dropdown("DRY_RUN", "true", ["true", "false"], "A. Dry run (true = checks and plan only)")
dbutils.widgets.dropdown("SCHEDULE", "keep", ["keep", "paused", "active"], "B. Schedule state")
DRY_RUN = dbutils.widgets.get("DRY_RUN").strip().lower() == "true"
SCHEDULE = dbutils.widgets.get("SCHEDULE").strip().lower()
print("DRY RUN (nothing will be created or changed)" if DRY_RUN else "LIVE: will create or update the job")

# COMMAND ----------

import json
from pathlib import Path

from databricks.sdk import WorkspaceClient

REPO = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm"
JOB_JSON = Path(REPO) / "pipeline" / "job_daily_refresh.json"

w = WorkspaceClient()
text = JOB_JSON.read_text()
if "REPLACE_WITH" in text:
    raise RuntimeError("job_daily_refresh.json still contains a REPLACE_WITH placeholder.")
spec = json.loads(text)
name = spec["name"]

# every notebook and script the tasks point at must exist
missing = []
for t in spec["tasks"]:
    path = (t.get("notebook_task") or {}).get("notebook_path") or (t.get("spark_python_task") or {}).get("python_file")
    if not path:
        missing.append(f"{t['task_key']}: no notebook or script path")
        continue
    try:
        w.workspace.get_status(path)
    except Exception:
        missing.append(f"{t['task_key']}: {path}")
if missing:
    raise RuntimeError("These task paths do not exist:\n  " + "\n  ".join(missing))
print(f"Checked {len(spec['tasks'])} tasks: all paths exist.")

# COMMAND ----------

existing = [j for j in w.jobs.list(name=name) if j.settings and j.settings.name == name]
if len(existing) > 1:
    raise RuntimeError(f"{len(existing)} jobs are named '{name}'. Delete the extras in the Jobs UI, then rerun.")
job = existing[0] if existing else None

file_state = spec.get("schedule", {}).get("pause_status", "PAUSED")
current = None
if job and job.settings.schedule and job.settings.schedule.pause_status:
    current = job.settings.schedule.pause_status.value
state = {"paused": "PAUSED", "active": "UNPAUSED"}.get(SCHEDULE) or (current or file_state)
if "schedule" in spec:
    spec["schedule"]["pause_status"] = state

print(f"Job:       {name}")
print(f"Action:    {'update job ' + str(job.job_id) if job else 'create a new job'}")
print(f"Schedule:  {spec.get('schedule', {}).get('quartz_cron_expression')} {spec.get('schedule', {}).get('timezone_id')} -> {state}")
print(f"Notify:    {spec.get('email_notifications', {}).get('on_failure')}")
print("Tasks:")
for t in spec["tasks"]:
    deps = ", ".join(d["task_key"] for d in t.get("depends_on", [])) or "-"
    print(f"  {t['task_key']:<20} after: {deps}")

# COMMAND ----------

result = "dry run: nothing created or changed"
if not DRY_RUN:
    if job:
        w.api_client.do("POST", "/api/2.2/jobs/reset", body={"job_id": job.job_id, "new_settings": spec})
        job_id = job.job_id
        result = f"updated job {job_id}"
    else:
        job_id = w.api_client.do("POST", "/api/2.2/jobs/create", body=spec)["job_id"]
        result = f"created job {job_id}"
    host = w.config.host.rstrip("/")
    result += f" ({state}): {host}/jobs/{job_id}"
print(result)
