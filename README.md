# Ethiopia woreda heat, flood, rain and food-price map

Map of 1,148 Ethiopian woredas, refreshed daily by a Databricks job (see Daily job): heat metrics (HeatReady), river flood forecasts
(GloFAS via Open-Meteo), rainfall (CHIRPS), food prices (World Bank RTFP) and the EthioMet bulletin.
The pipeline runs on Databricks; the site is published to GitHub Pages from this repo's `gh-pages` branch.
The site is at https://institutefordiseasemodeling.github.io/eth-woredas-heat-flood-food-idm/ (the organization also serves it under docs.idmod.org).

Originally built by Andrew Schroeder (`ASchroederCR/eth-woredas-heat-flood-food`) and migrated to Databricks.

## Layout

| Path | What it is |
|---|---|
| `pipeline/` | The daily stages and shared code: `config.py`, `heat_api.py`, `flood_gauges.py`, `chirps.py`, `ethiomet.py`, `rivers.py`, `setup_site.py`, `soft_run.py`, `requirements.txt`, and the notebooks `build_map_data` and `food_prices`. Kept flat so each file maps one-to-one to Andrew's repo |
| `ops/` | Notebooks you run: `run_daily_refresh`, `run_pipeline_stage`, `run_heat_download`, `publish_pages`, `create_or_update_job` |
| `checks/` | Read-only checks: `check_boundary`, `check_github_token`, `test_heatready_api`, `compare_with_andrew` |
| `setup/` | One-off setup: `create_heat_projects` (notebook) and `prepare_projects.py` |
| `jobs/` | `job_daily_refresh.json`, the Lakeflow job definition (paused until switched on) |
| `app/` | The static site: `index.html`, `app.js`, `style.css`, `.nojekyll`. Generated files (`app/data/*.js`, `app/config.js`) are written to the Databricks Volume, not stored here |

## Where the data lives

Unity Catalog Volume `idm_conflict_and_health.ethiopia_climate.heat_map_files`:
`build/` (downloaded rows and caches), `boundaries/` (OCHA admin3 shapefile), `app/` (site plus generated data), `reference/` (a frozen copy of Andrew's 11 November outputs; `checks/compare_with_andrew` compares against his latest data from a Git clone of his repo by default).

## Running it

- **Whole pipeline:** notebook `ops/run_daily_refresh` (set `DRY_RUN` to `false`), or the Lakeflow job.
- **One stage:** `ops/run_pipeline_stage`; the map build and the food prices are notebooks of their own, `pipeline/build_map_data` and `pipeline/food_prices`.
- **Checks:** the notebooks in `checks/`.
- **One-off setup:** `setup/create_heat_projects` creates the six `eth-woreda-heat-N-idm` projects in HeatReady.

Stage order: `setup_site`, HeatReady download and forecast, `build_map_data`, `flood_gauges`,
`food_prices`, then `rainfall` and `ethiomet` (the last two only warn on failure).
Publishing is a separate notebook, `ops/publish_pages`: it force-pushes the Volume's `app/` to the `gh-pages` branch as a single commit (run it with `DRY_RUN` true first). `run_daily_refresh` does not publish. In the job, `publish` runs last and only if every earlier stage succeeded. Pages is served from branch `gh-pages`, folder `/` (repo Settings > Pages).

## Daily job

`jobs/job_daily_refresh.json` defines the Lakeflow job "Ethiopia woreda climate map: daily refresh":
one task per stage, then `publish`. It is scheduled for 07:30 UTC but **paused** until switched on, and emails the owner on failure.
Create or update it by running the notebook `ops/create_or_update_job` (dry run first), or from the Jobs UI (Create job > JSON), or with `databricks jobs create --json @jobs/job_daily_refresh.json`,
run it once by hand, then set the schedule to active. If the job file changes, update the job to match.

Publishing refuses data more than 3 days old (set `ALLOW_STALE` on `publish_pages` to override).
`publish_pages` uploads only files that changed since the last publish. The Mapbox token in `config.js` is a public (`pk.`) token
that GitHub's secret scanner flags; it was allowed once through the one-time web bypass and is not re-sent unless it changes. The token cannot be URL-restricted without a payment method on the Mapbox account; it is a free-tier public token, so the worst case is that the basemap stops loading.

## What refreshes and what does not

Every run refreshes: HeatReady heat and 6-day forecast, GloFAS river discharge and forecast (14 gauges), CHIRPS rainfall,
the EthioMet bulletin, and the monthly woreda aggregation. Food prices: each run asks the World Bank catalog for the newest RTFP release and downloads it only if it changed
(the `food_prices` notebook, `COMMAND` = `update`); if the catalog cannot be reached, the current release is kept. Markets are then re-linked to the months.

Updated by hand when a new version is adopted: the OCHA admin3 boundaries, LandScan and WorldPop population layers,
HydroRIVERS/HydroBASINS (`app/data/rivers.js`), and the RP2/RP5 flood thresholds (fitted to 1984-2025 annual peaks).
`setup/prepare_projects.py` is the one-time script that split the woredas into HeatReady projects; it is kept for reference
and is not part of the daily run.

## Notes on the data

- **Month to date.** The current month is shown as soon as it has data, with a "Month to date" badge and a dashed last chart segment. Means compare with full months; day counts and person-days cover only the days so far. Earlier months need 20 days (`HEAT_MIN_DAYS`).
- **Food prices.** World Bank RTFP market data. Months without a survey are World Bank estimates (the monthly close), and prices are shown against the national average. If the release does not reach the current month, the markets show the latest month with prices, labelled "(latest prices)".
- **Rainfall.** CHIRPS v3 dekads; the final product runs 4 to 6 weeks behind, so recent dekads are preliminary and shown lighter.
- **EthioMet.** The newest bulletin is chosen by the date in its title and shown as published; it is not joined to woredas.

These features follow Andrew Schroeder's repo as of 2026-11-17; his README has the full methods and caveats.

## Conventions

- Code stays as plain `.py` scripts. A script becomes a notebook only when that gives something concrete: widgets, printed output, or a `%pip` install (`build_map_data`, `food_prices`).
- Scripts that run directly as job tasks (`setup_site.py`, `heat_api.py`, `flood_gauges.py`, `soft_run.py`) must not use `__file__`: a job runs them without it. Use `config.PIPELINE_DIR` for the pipeline folder.
- `chirps.py` and `ethiomet.py` must stay scripts: `soft_run.py` runs them as subprocesses so a failure warns instead of blocking `publish`.
- The stage scripts and `config.py` stay flat in `pipeline/` so each file maps to one file in Andrew's repo. Our own changes there are the Databricks paths and secrets (`config.py`), the `-idm` project ids (`heat_api.py`), and `keep="last"` de-duplication (`build_map_data`).

## Upkeep

- The GitHub token (`github_token`) is a classic personal access token that expires 90 days after creation. Replace it in time, with the same notebook that stores secrets, then run `check_github_token`.
- `requirements.txt` is not pinned yet: after the first successful job run, pin the versions.
- Notebooks in the Databricks Git folder must be committed and pushed by hand.
- To follow Andrew's repo: pull it in its Git folder, diff the changed files against ours, port what is useful, then run `checks/compare_with_andrew` (it should print PASS). Dates of the last port are in this README's notes above.

## Secrets

Scope `ethiopia_climate`: `heatready_username`, `heatready_key`, `mapbox_token`, `github_token`.
Store them with the utility notebook `12_api_keys_as_secrets` (`idm_databricks_utilities`). Never put them in code, widgets or files.

## Settings

`pipeline/config.py` holds the paths, the secret scope and the publish repo
(`InstituteforDiseaseModeling/eth-woredas-heat-flood-food-idm`). Each can be overridden with an environment variable (for example `ETH_PUBLISH_REPO`).
Other optional variables: `ETH_PROJECT_SUFFIX` (HeatReady project suffix, default `-idm`), `HEAT_RAW` (folder of daily rows) and `HEAT_MIN_DAYS` (days a month needs to count as full, default 20).

*Owner: IDM data management*
