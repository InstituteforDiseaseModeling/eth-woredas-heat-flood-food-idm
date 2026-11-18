"""Run another pipeline script; if it fails, log a warning and exit 0 so the job carries on.

Used for the optional steps (ONI index, rainfall, EthioMet bulletin). Like refresh_daily.ps1 did, a failure
keeps the previous output file instead of blocking the publish step. The failure is visible in
this task's log.

Usage: soft_run.py <script.py> [args...]
These scripts must not need secrets: they run as a subprocess without the notebook context.
"""
import subprocess
import sys

import config

here = config.PIPELINE_DIR
script, *args = sys.argv[1:]
result = subprocess.run([sys.executable, str(here / script), *args], cwd=here)
if result.returncode:
    print(f"WARNING: {script} {' '.join(args)} exited with code {result.returncode}; "
          f"keeping the previous output.", flush=True)
# No sys.exit(0): job tasks treat SystemExit as a failure, so just end the script.
