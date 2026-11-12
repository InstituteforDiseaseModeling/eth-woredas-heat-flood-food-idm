# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # Test the HeatReady API credentials (read-only)
# MAGIC
# MAGIC **Purpose:** Check that the stored `heatready_username` and `heatready_key` work, that this compute can reach the API, and whether the six `eth-woreda-heat-*-as2026` projects are visible to this account. Creates and changes nothing, writes no files, and never prints the credentials.
# MAGIC
# MAGIC **Steps and API calls:**
# MAGIC 1. `status` (no credentials): is the API reachable? 1 call.
# MAGIC 2. `ping` (needs valid credentials, no project): do the credentials work? 1 call. If this fails, the notebook stops.
# MAGIC 3. `get-usage` (no project): shows this account's rate limits and usage. 1 call.
# MAGIC 4. `get-project-status` for the six projects: are Andrew's projects visible to this account? 6 calls (this action has no rate limit).
# MAGIC
# MAGIC **How to run:** Run all. Read the summary at the bottom.
# MAGIC
# MAGIC **Interpreting the result:**
# MAGIC - Step 1 fails with a connection error: this compute blocks outside web access.
# MAGIC - Step 2 returns 401 or 403: the key or username is wrong. Re-add both with notebook 12.
# MAGIC - Step 4 returns 200: this account can see the projects, so downloads can proceed.
# MAGIC - Step 4 returns 404: the projects belong to Andrew's account. Ask Andrew to share them, or we run `heat_api.py create` and `backfill` for this account (slow: 30 days per call).

# COMMAND ----------

import json
import requests

SCOPE = "ethiopia_climate"
BASE = "https://5trhrgas69.execute-api.us-east-1.amazonaws.com/v1/evaluate"
PROJECTS = [f"eth-woreda-heat-{k}-as2026" for k in range(1, 7)]

_user = dbutils.secrets.get(SCOPE, "heatready_username")
_key = dbutils.secrets.get(SCOPE, "heatready_key")


def call(action, payload=None, auth=True):
    body = {"action": action, "payload": payload or {}}
    if auth:
        body.update({"username": _user, "key": _key})
    r = requests.post(BASE, json=body, timeout=120)
    try:
        data = r.json()
    except ValueError:
        data = {"error": r.text[:200]}
    return r.status_code, data


def short(data, limit=600):
    return json.dumps(data, default=str)[:limit]


# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. API reachable (`status`, no credentials)

# COMMAND ----------

code, data = call("status", auth=False)
reachable = code == 200
print("status:", code, short(data))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Credentials (`ping`, no project)

# COMMAND ----------

code, data = call("ping")
creds_ok = code == 200
print("ping:", code, short(data))
if not creds_ok:
    print("STOP: credentials rejected or API error. Fix this before testing the projects.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Rate limits and usage (`get-usage`, no project)

# COMMAND ----------

if creds_ok:
    code, data = call("get-usage")
    print("get-usage:", code, short(data, 1500))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Project visibility (`get-project-status`)

# COMMAND ----------

results = {}
if creds_ok:
    for pid in PROJECTS:
        code, data = call("get-project-status", {"project_id": pid})
        results[pid] = code
        print(pid, code, {k: data.get(k) for k in ("start", "last_updated", "polygon_count", "error", "code")})

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print("API reachable:      ", reachable)
print("Credentials accepted:", creds_ok)
ok = [p for p, c in results.items() if c == 200]
print(f"Projects visible:    {len(ok)} of {len(PROJECTS)}", results or "")
if not reachable:
    print("RESULT: cannot reach the API from this compute.")
elif not creds_ok:
    print("RESULT: FAIL. Re-add heatready_username and heatready_key with notebook 12.")
elif len(ok) == len(PROJECTS):
    print("RESULT: PASS. Credentials work and all six projects are available.")
else:
    print("RESULT: PARTIAL. Credentials work but not all projects are visible to this account.")