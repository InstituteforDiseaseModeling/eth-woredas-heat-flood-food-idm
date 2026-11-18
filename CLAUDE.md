# CLAUDE.md

Guidance for Claude Code (and colleagues) working in this repository. The README has the full detail; this file is the short version plus the rules that are easy to break.

## What this is

Pipeline and static site for the Ethiopia woreda heat, flood, rain and food-price map (1,148 woredas). It runs on Databricks every other day as a Lakeflow job, writes its working files to a Unity Catalog Volume, stores the imports as Delta tables in `idm_conflict_and_health.ethiopia_climate`, and publishes the site to the `gh-pages` branch of this GitHub repo. It was migrated from Andrew Schroeder's repo (`ASchroederCR/eth-woredas-heat-flood-food`), and the scripts in `pipeline/` deliberately stay close to his files.

## Layout

- `pipeline/`: the refresh stages and shared code (`config.py` holds all paths and secrets access). Notebooks here: `build_map_data`, `food_prices`, `write_delta_tables`. Everything else is a plain `.py` script.
- `ops/`: notebooks you run by hand (`run_daily_refresh`, `run_pipeline_stage`, `publish_pages`, `create_or_update_job`, `run_heat_download`).
- `checks/`: read-only checks. `compare_with_andrew` should print PASS.
- `setup/`: one-off setup, not part of the refresh.
- `jobs/job_daily_refresh.json`: the job definition. The live job is created from it by `ops/create_or_update_job`.
- `app/`: the static site (`index.html`, `app.js`, `style.css`). Generated files (`app/data/*.js`, `app/config.js`) are written to the Volume and are not in the repo.

## Rules that are easy to break

- **The scheduled job runs the files in this workspace folder directly.** Saving an edit here changes what the next run executes, before you commit. Test with `ops/run_pipeline_stage` or a dry run first.
- **Never use `__file__` in a script that runs as a job task** (`setup_site.py`, `heat_api.py`, `flood_gauges.py`, `soft_run.py`): jobs run them without it. Use `config.PIPELINE_DIR`.
- **Never end a job script with `sys.exit(0)`**: the job counts `SystemExit` as a failure.
- `chirps.py`, `ethiomet.py` and `oni.py` stay scripts. `soft_run.py` runs them as subprocesses so a failure warns and keeps the previous file instead of blocking `publish`.
- **Secrets** live in the scope `ethiopia_climate` (`heatready_username`, `heatready_key`, `mapbox_token`, `github_token`) and are read through `config.secret()`. Never put a secret in code, a widget, a file or a commit. (The Mapbox `pk.` token is public by design, but GitHub's scanner still flags it; see the README.)
- Serverless compute does not allow setting Delta Spark configs such as `autoMerge`. `write_delta_tables` uses `MERGE WITH SCHEMA EVOLUTION` instead.
- Package versions are pinned in two places that must match: `pipeline/requirements.txt` and `jobs/job_daily_refresh.json`.
- `publish_pages` force-pushes a single commit to `gh-pages`. Run it with `DRY_RUN` true first, and do not edit `gh-pages` by hand.
- Do not hand-edit `app/data/*.js`; rerun the stage that writes it.

## Working in Databricks

- Edit in the Databricks Git folder and commit and push from the UI. Notebooks in Git folders are source-format `.py` files.
- Paths: code at `/Workspace/IDM_repos/idm_conflict_and_health/ethiopia_climate/eth-woredas-heat-flood-food-idm/`, data in the Volume `/Volumes/idm_conflict_and_health/ethiopia_climate/heat_map_files/{build,app,boundaries,reference}`.
- After changing `jobs/job_daily_refresh.json`, run `ops/create_or_update_job` (dry run first) so the live job matches.
- Follow Andrew's repo by pulling it in its own Git folder, diffing the changed files, porting what is useful, then running `checks/compare_with_andrew`.
- Notebook headers follow one pattern: purpose, reads, writes, how to run, widgets table, owner line.

## Data and tables

`README.md` has the table of every data input (source, what refreshes it, cadence) and the table of Delta tables. Woredas are keyed by `adm3_pcode`. Soft stages (`oni`, `rainfall`, `ethiomet_bulletin`) and `delta_tables` only warn on failure, so read their task logs for `WARNING` after a run.

Known gaps in the sources, not bugs in this code: GloFAS discharge has no values before 1997, and HeatReady is missing one project (287 woredas) on 2023-09-10, 2023-09-11, 2026-03-24 and 2026-03-25.

## When you change something

Update the README (and the schema or table comments if tables change) in the same change, keep the job JSON and the live job in step, and run the relevant check before you push.
