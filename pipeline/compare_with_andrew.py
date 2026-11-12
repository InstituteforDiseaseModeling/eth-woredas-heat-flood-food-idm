# Databricks notebook source
# MAGIC %md
# MAGIC # Compare our map data files with Andrew's (read-only)
# MAGIC
# MAGIC **Purpose:** Check that the pipeline running in Databricks reproduces Andrew's output. Compares the files in `app/data/` (ours) with Andrew's copies in `reference/andrew_app_data/` (his 11 November build).
# MAGIC
# MAGIC **What it compares:**
# MAGIC - **Structure** of each file that exists in both places (`data.js`, `geo.js`, `flood.js`, `food.js`, `rain.js`, `ethiomet.js`): the keys and the number of items at each level.
# MAGIC - **Values in `data.js`:** for each metric, the months and woredas both builds have, leaving out the most recent two months (our download is newer, so those legitimately differ). Reports the share of values that agree within a small tolerance and the largest difference.
# MAGIC
# MAGIC **Expect:** Differences only in the newest days, the forecast, and files where the source data moved on (flood, food prices, rain, bulletin). Large differences in older months mean something is wrong.
# MAGIC
# MAGIC **Changes nothing.** Reads only. No widgets, no secrets.
# MAGIC
# MAGIC *Owner: IDM data management · Questions: jeremy.cooper@gatesfoundation.org · Last updated: 2026-11-12*

# COMMAND ----------

import json
import re
import sys
from pathlib import Path

PIPELINE = "/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/pipeline"
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

import numpy as np

import config

OURS = config.APP / "data"
THEIRS = config.BASE / "reference" / "andrew_app_data"
FILES = ["data.js", "geo.js", "flood.js", "food.js", "rain.js", "ethiomet.js"]


def load(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\s*window\.(\w+)\s*=\s*", text)
    body = text[m.end():].rstrip().rstrip(";")
    return m.group(1), json.loads(body)


def shape(x, depth=0, max_depth=3):
    """Compact description of a JSON value: dict keys / list length / scalar type."""
    if isinstance(x, dict):
        if depth >= max_depth:
            return f"dict[{len(x)}]"
        return {k: shape(v, depth + 1, max_depth) for k, v in x.items()}
    if isinstance(x, list):
        return f"list[{len(x)}]"
    return type(x).__name__


def diff_shape(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"only in Andrew's: {path}/{k}")
            elif k not in b:
                out.append(f"only in ours: {path}/{k}")
            else:
                out += diff_shape(a[k], b[k], f"{path}/{k}")
    elif a != b:
        out.append(f"{path or '/'}: ours {a} vs Andrew's {b}")
    return out

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Structure, file by file

# COMMAND ----------

loaded = {}
for name in FILES:
    po, pt = OURS / name, THEIRS / name
    if not po.exists() or not pt.exists():
        print(f"{name:12} skipped (ours: {po.exists()}, Andrew's: {pt.exists()})")
        continue
    (vo, do), (vt, dt_) = load(po), load(pt)
    loaded[name] = (do, dt_)
    diffs = diff_shape(shape(do), shape(dt_))
    print(f"{name:12} window.{vo} vs window.{vt} | sizes {po.stat().st_size:,} vs {pt.stat().st_size:,} | {len(diffs)} structural difference(s)")
    for d in diffs[:12]:
        print("   ", d)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Values in data.js (older months only)

# COMMAND ----------

TOL = 0.051   # values are rounded to 1 decimal, so allow one rounding step
SKIP_LAST = 2

if "data.js" not in loaded:
    print("data.js missing in one of the folders.")
else:
    ours, theirs = loaded["data.js"]
    print("months  ours:", ours["months"][0], "to", ours["months"][-1], f"({len(ours['months'])})",
          "| Andrew's:", theirs["months"][0], "to", theirs["months"][-1], f"({len(theirs['months'])})")
    print("woredas same list and order:", ours["woredas"] == theirs["woredas"], f"({len(ours['woredas'])} vs {len(theirs['woredas'])})")
    print("metrics only in ours:", sorted(set(ours["metrics"]) - set(theirs["metrics"])))
    print("metrics only in Andrew's:", sorted(set(theirs["metrics"]) - set(ours["metrics"])))
    print("last_date  ours:", ours["last_date"], "| Andrew's:", theirs["last_date"])
    print()
    common_months = [m for m in ours["months"] if m in theirs["months"]][: -SKIP_LAST or None]
    print(f"{'metric':14}{'temporal':>9}{'values':>9}{'agree %':>9}{'max diff':>10}")
    worst = []
    for key in sorted(set(ours["metrics"]) & set(theirs["metrics"])):
        mo, mt = ours["metrics"][key], theirs["metrics"][key]
        if mo["temporal"] != mt["temporal"]:
            print(f"{key:14} temporal flag differs")
            continue
        pairs = []
        if mo["temporal"]:
            for mm in common_months:
                a, b = mo["values"][ours["months"].index(mm)], mt["values"][theirs["months"].index(mm)]
                pairs += list(zip(a, b))
        elif not key.startswith("fc_"):      # forecast layers change daily
            pairs = list(zip(mo["values"], mt["values"]))
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        if not pairs:
            continue
        d = np.abs(np.array([x for x, _ in pairs], dtype=float) - np.array([y for _, y in pairs], dtype=float))
        agree = float((d <= TOL).mean()) * 100
        print(f"{key:14}{str(mo['temporal']):>9}{len(d):>9,}{agree:>8.2f}%{d.max():>10.2f}")
        worst.append((agree, key))
    print("\nLowest agreement:", sorted(worst)[:3])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

if "data.js" in loaded:
    ok = bool(worst) and min(a for a, _ in worst) >= 99.0 and ours["woredas"] == theirs["woredas"]
    print("RESULT:", "PASS. Older months and metrics agree with Andrew's build (>= 99% on every metric)." if ok
          else "CHECK the tables above. Some metric agrees below 99% or the woreda lists differ.")