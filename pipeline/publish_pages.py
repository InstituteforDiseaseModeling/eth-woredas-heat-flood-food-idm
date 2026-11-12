# Databricks notebook source
# MAGIC %md
# MAGIC # Publish the map to GitHub Pages
# MAGIC
# MAGIC **Purpose:** Publish the site in the Volume's `app/` folder to the `gh-pages` branch of the publish repo (`PUBLISH_REPO` in `config.py`, currently `InstituteforDiseaseModeling/eth-woredas-heat-flood-food-idm`). GitHub Pages then serves it. The branch always holds exactly one commit with exactly the site files, replaced on every publish (the same single-commit force-push the original Windows script did).
# MAGIC
# MAGIC **What is published:** `index.html`, `app.js`, `style.css`, `config.js`, `.nojekyll` and `data/*.js` from the Volume's `app/` folder. Nothing else.
# MAGIC
# MAGIC **How it works:** It uploads each file with the GitHub API, builds one commit and moves `gh-pages` to it (creating the branch the first time). No git program is needed. If the files are identical to what is already published, it does nothing.
# MAGIC
# MAGIC **Safety checks (a failed check stops before anything is published):**
# MAGIC - the secret `github_token` can push to the repo;
# MAGIC - the required files exist (`index.html`, `app.js`, `style.css`, `config.js`, `data/data.js`, `data/geo.js`);
# MAGIC - the data is fresh: the last observed date in `data.js` is at most 3 days old, unless `ALLOW_STALE` = true.
# MAGIC
# MAGIC **What it changes:** Only the `gh-pages` branch of the publish repo. It never touches `main`, the Volume or HeatReady, and it never prints the token.
# MAGIC
# MAGIC **First publish:** After the first successful run, in the repo go to Settings > Pages, set Source to "Deploy from a branch", branch `gh-pages`, folder `/ (root)`. The site is then at `https://<owner>.github.io/<repo>/`.
# MAGIC
# MAGIC **Requirements:** secret `github_token` (Contents: Read and write on the repo) in scope `ethiopia_climate`; this compute can reach `api.github.com`; the pipeline has produced `app/data/data.js` and `geo.js`.
# MAGIC
# MAGIC **How to run:** Run all with `DRY_RUN` = `true` first. It runs every check and lists what it would publish. Then set `DRY_RUN` to `false` and run again. The Lakeflow job runs this notebook with `DRY_RUN` = `false`.
# MAGIC
# MAGIC ### Widgets
# MAGIC
# MAGIC | Label | Widget | Type (default) | What to enter |
# MAGIC |---|---|---|---|
# MAGIC | A | `DRY_RUN` | dropdown (`true`) | `true` = checks and plan only; `false` = publish |
# MAGIC | B | `ALLOW_STALE` | dropdown (`false`) | `true` = publish even if the data is more than 3 days old |
# MAGIC
# MAGIC *Owner: IDM data management · Questions: jeremy.cooper@gatesfoundation.org · Last updated: 2026-11-12*

# COMMAND ----------

dbutils.widgets.dropdown("DRY_RUN", "true", ["true", "false"], "A. Dry run (true = checks and plan only)")
dbutils.widgets.dropdown("ALLOW_STALE", "false", ["false", "true"], "B. Publish even if data is older than 3 days")
DRY_RUN = dbutils.widgets.get("DRY_RUN").strip().lower() == "true"
ALLOW_STALE = dbutils.widgets.get("ALLOW_STALE").strip().lower() == "true"
print("DRY RUN (nothing will be published)" if DRY_RUN else "LIVE: will publish to gh-pages")

# COMMAND ----------

import base64
import re
import sys
from datetime import date, datetime, timezone

PIPELINE = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/pipeline"
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

import requests

import config

REPO = config.PUBLISH_REPO
BRANCH = "gh-pages"
API = "https://api.github.com"
MAX_AGE_DAYS = 3

TOP_LEVEL = ["index.html", "app.js", "style.css", "config.js", ".nojekyll"]
REQUIRED = ["index.html", "app.js", "style.css", "config.js", "data/data.js", "data/geo.js"]

_token = config.secret("github_token", "GITHUB_TOKEN").strip()
_headers = {"Authorization": f"Bearer {_token}", "Accept": "application/vnd.github+json",
            "User-Agent": "idm-eth-publish", "X-GitHub-Api-Version": "2022-11-28"}


def gh(method, path, **kw):
    """Call the GitHub API. Returns (status, json_or_None). The token is never printed."""
    r = requests.request(method, API + path, headers=_headers, timeout=120, **kw)
    try:
        body = r.json()
    except ValueError:
        body = None
    return r.status_code, body


print("Repo:", REPO, "| branch:", BRANCH)
print("Source folder:", config.APP)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Collect the files

# COMMAND ----------

files = {}   # path in repo -> Path on the Volume
for name in TOP_LEVEL:
    p = config.APP / name
    if p.is_file():
        files[name] = p
for p in sorted((config.APP / "data").glob("*.js")):
    files[f"data/{p.name}"] = p

missing = [r for r in REQUIRED if r not in files]
total = 0
for rel, p in files.items():
    size = p.stat().st_size
    total += size
    print(f"  {rel:22} {size:>12,} bytes")
print(f"{len(files)} files, {total:,} bytes")
if missing:
    raise RuntimeError(f"Required file(s) missing from app/: {missing}. Run the pipeline first.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Freshness check

# COMMAND ----------

head = files["data/data.js"].read_text(encoding="utf-8")
m = re.search(r'"last_date":"(\d{4}-\d{2}-\d{2})"', head)
if not m:
    raise RuntimeError("Could not read last_date from data/data.js; refusing to publish.")
last = date.fromisoformat(m.group(1))
age = (datetime.now(timezone.utc).date() - last).days
print(f"Last observed date in data.js: {last} ({age} day(s) old)")
if age > MAX_AGE_DAYS and not ALLOW_STALE:
    raise RuntimeError(f"Data is {age} days old (limit {MAX_AGE_DAYS}). Fix the pipeline, or set ALLOW_STALE to true.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. GitHub: token, repo, branch

# COMMAND ----------

code, repo = gh("GET", f"/repos/{REPO}")
if code != 200:
    raise RuntimeError(f"Cannot read {REPO} (status {code}): {(repo or {}).get('message')}. Repo missing, or token not approved for it.")
perms = repo.get("permissions") or {}
print("repo:", repo["full_name"], "| visibility:", repo.get("visibility"), "| push permission:", perms.get("push"))
if not perms.get("push"):
    raise RuntimeError("The token has no push permission on the repo (needs Contents: Read and write).")

code, ref = gh("GET", f"/repos/{REPO}/git/ref/heads/{BRANCH}")
branch_exists = code == 200
print(f"{BRANCH}:", "exists" if branch_exists else "does not exist yet (will be created)")
site_url = f"https://{repo['owner']['login'].lower()}.github.io/{repo['name']}/"

if DRY_RUN:
    print("\n[DRY RUN] All checks passed. Would publish", len(files), "files to", f"{REPO}@{BRANCH}", "as one commit.")
    print("Site address once Pages is on:", site_url)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Publish

# COMMAND ----------

result = "dry run: nothing published"
if not DRY_RUN:
    # 1) one blob per file
    entries = []
    for rel, p in files.items():
        content = base64.b64encode(p.read_bytes()).decode("ascii")
        code, blob = gh("POST", f"/repos/{REPO}/git/blobs", json={"content": content, "encoding": "base64"})
        if code == 409:
            raise RuntimeError("GitHub says the repo is empty. Push one commit to main first (for example the README), then rerun.")
        if code != 201:
            raise RuntimeError(f"Blob upload failed for {rel} (status {code}): {(blob or {}).get('message')}")
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    # 2) a tree with only these files (no base tree, so anything else is dropped)
    code, tree = gh("POST", f"/repos/{REPO}/git/trees", json={"tree": entries})
    if code != 201:
        raise RuntimeError(f"Tree creation failed (status {code}): {(tree or {}).get('message')}")

    # 3) nothing to do if the published tree is already identical
    unchanged = False
    if branch_exists:
        code, cur = gh("GET", f"/repos/{REPO}/git/commits/{ref['object']['sha']}")
        unchanged = code == 200 and cur["tree"]["sha"] == tree["sha"]
    if unchanged:
        result = "no changes: the published site is already identical"
    else:
        # 4) one parentless commit
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        code, commit = gh("POST", f"/repos/{REPO}/git/commits",
                          json={"message": f"Data refresh {stamp} (last observed {last})", "tree": tree["sha"], "parents": []})
        if code != 201:
            raise RuntimeError(f"Commit creation failed (status {code}): {(commit or {}).get('message')}")
        # 5) move (or create) gh-pages, forcing past the old history
        if branch_exists:
            code, upd = gh("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}", json={"sha": commit["sha"], "force": True})
            ok = code == 200
        else:
            code, upd = gh("POST", f"/repos/{REPO}/git/refs", json={"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})
            ok = code == 201
        if not ok:
            raise RuntimeError(f"Updating {BRANCH} failed (status {code}): {(upd or {}).get('message')}")
        result = f"published commit {commit['sha'][:10]} to {REPO}@{BRANCH} ({len(files)} files)"
print(result)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print("Repo:      ", REPO)
print("Files:     ", len(files), f"({total:,} bytes)")
print("Data as of:", last)
print("Result:    ", result)
print("Site:      ", site_url, "(live once Settings > Pages points at gh-pages)")
