# Databricks notebook source
# MAGIC %md
# MAGIC # Check a GitHub token against the publish repo (read-only)
# MAGIC
# MAGIC **Purpose:** Find out whether a stored GitHub token is valid and can push to the repo where the map is published. It reads the token from a secret scope, makes three read-only calls to the GitHub API, and prints the results. It never prints the token, never pushes, and changes nothing.
# MAGIC
# MAGIC **Checks:**
# MAGIC 1. The token is accepted by GitHub, and which account it belongs to, its scopes and its expiry (when GitHub reports one).
# MAGIC 2. The repo exists, is visible to the token, is public or private, and whether the token has push permission.
# MAGIC 3. Whether the `gh-pages` branch exists yet (it is created by the first publish, so "not found" is normal before then).
# MAGIC
# MAGIC **Requirements:** READ on the secret scope you name; this compute can reach `api.github.com`.
# MAGIC
# MAGIC **How to run:** Fill in the widgets and run all. The defaults check the pipeline's own secret. Do not paste a token into any widget; widgets name where the secret is stored, not its value.
# MAGIC
# MAGIC ### Widgets
# MAGIC
# MAGIC | Label | Widget | Type (default) | What to enter |
# MAGIC |---|---|---|---|
# MAGIC | A | `SCOPE` | text (`ethiopia_climate`) | secret scope that holds the token |
# MAGIC | B | `KEY` | text (`github_token`) | key name of the secret |
# MAGIC | C | `REPO` | text (from `config.py`) | `owner/name` of the publish repo |
# MAGIC
# MAGIC *Owner: IDM data management · Questions: jeremy.cooper@gatesfoundation.org · Last updated: 2026-11-12*

# COMMAND ----------

import sys

PIPELINE = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/pipeline"
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

import config

dbutils.widgets.text("SCOPE", config.SCOPE, "A. Secret scope")
dbutils.widgets.text("KEY", "github_token", "B. Secret key")
dbutils.widgets.text("REPO", config.PUBLISH_REPO, "C. Repo (owner/name)")
SCOPE = dbutils.widgets.get("SCOPE").strip()
KEY = dbutils.widgets.get("KEY").strip()
REPO = dbutils.widgets.get("REPO").strip()
print(f"Secret: {SCOPE}/{KEY} | Repo: {REPO}")

# COMMAND ----------

import json
import urllib.error
import urllib.request

_token = dbutils.secrets.get(SCOPE, KEY)


def gh(path):
    """GET https://api.github.com<path>. Returns (status, json_or_None, headers). Network errors raise."""
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Authorization": f"Bearer {_token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "idm-eth-token-check"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode()), r.headers
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = None
        return e.code, body, e.headers

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Token

# COMMAND ----------

code, user, h = gh("/user")
token_ok = code == 200
print("status:", code)
if token_ok:
    print("account:", user.get("login"))
    print("scopes (classic tokens only; fine-grained tokens show none):", h.get("X-OAuth-Scopes") or "none reported")
    print("expires:", h.get("github-authentication-token-expiration") or "not reported (no expiry, or not a PAT)")
else:
    print("message:", (user or {}).get("message"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Repo and push permission

# COMMAND ----------

can_push = False
if token_ok:
    code, repo, _ = gh(f"/repos/{REPO}")
    print("status:", code)
    if code == 200:
        perms = repo.get("permissions") or {}
        can_push = bool(perms.get("push"))
        print("repo:", repo["full_name"], "| visibility:", repo.get("visibility"), "| default branch:", repo.get("default_branch"))
        print("permissions:", perms)
    else:
        print("message:", (repo or {}).get("message"), "(404 = repo does not exist, or the token cannot see it)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. gh-pages branch

# COMMAND ----------

if token_ok:
    code, br, _ = gh(f"/repos/{REPO}/branches/gh-pages")
    print("gh-pages:", "exists" if code == 200 else f"not found (status {code}); created by the first publish")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print("Token accepted by GitHub:", token_ok)
print("Can push to", REPO + ":", can_push)
print("RESULT:", "PASS. The token can publish to the repo." if token_ok and can_push
      else "NOT READY. See the lines above (token rejected, repo missing, or no push permission).")
