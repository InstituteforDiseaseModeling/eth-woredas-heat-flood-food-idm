# Ethiopia woreda heat, flood, rain and food-price map

Map of 1,148 Ethiopian woredas, refreshed every other day by a Databricks job (see Scheduled job): heat metrics (HeatReady), river flood forecasts
(GloFAS via Open-Meteo), rainfall (CHIRPS), food prices (World Bank RTFP) and the EthioMet bulletin.
The pipeline runs on Databricks; the site is published to GitHub Pages from this repo's `gh-pages` branch.
The site is at https://institutefordiseasemodeling.github.io/eth-woredas-heat-flood-food-idm/ (the organization also serves it under docs.idmod.org).

Originally built by Andrew Schroeder (`ASchroederCR/eth-woredas-heat-flood-food`) and migrated to Databricks.

## Layout

| Path | What it is |
|---|---|
| `pipeline/` | The refresh stages and shared code: `config.py`, `heat_api.py`, `flood_gauges.py`, `chirps.py`, `ethiomet.py`, `oni.py`, `rivers.py`, `setup_site.py`, `soft_run.py`, `requirements.txt`, and the notebooks `build_map_data`, `food_prices` and `write_delta_tables`. Kept flat so each file maps one-to-one to Andrew's repo |
| `ops/` | Notebooks you run: `run_daily_refresh`, `run_pipeline_stage`, `run_heat_download`, `publish_pages`, `create_or_update_job` |
| `checks/` | Read-only checks: `check_boundary`, `check_github_token`, `test_heatready_api`, `compare_with_andrew` |
| `setup/` | One-off setup: `create_heat_projects` (notebook) and `prepare_projects.py` |
| `jobs/` | `job_daily_refresh.json`, the Lakeflow job definition |
| `app/` | The static site: `index.html`, `app.js`, `style.css`, `.nojekyll`. Generated files (`app/data/*.js`, `app/config.js`) are written to the Databricks Volume, not stored here |

## Where the data lives

Unity Catalog Volume `idm_conflict_and_health.ethiopia_climate.heat_map_files`:
`build/` (downloaded rows and caches), `boundaries/` (OCHA admin3 shapefile), `app/` (site plus generated data), `reference/` (a frozen copy of Andrew's 11 November outputs; `checks/compare_with_andrew` compares against his latest data from a Git clone of his repo by default).

## Running it

- **Whole pipeline:** notebook `ops/run_daily_refresh` (set `DRY_RUN` to `false`), or the Lakeflow job.
- **One stage:** `ops/run_pipeline_stage`; the map build and the food prices are notebooks of their own, `pipeline/build_map_data` and `pipeline/food_prices`.
- **Checks:** the notebooks in `checks/`.
- **One-off setup:** `setup/create_heat_projects` creates the six `eth-woreda-heat-N-idm` projects in HeatReady.

Stage order: `setup_site`, `oni`, HeatReady download and forecast, `build_map_data`, `flood_gauges`,
`food_prices`, then `rainfall` and `ethiomet` (`oni`, `rainfall` and `ethiomet` only warn on failure), then `delta_tables` (see Delta tables).
Publishing is a separate notebook, `ops/publish_pages`: it force-pushes the Volume's `app/` to the `gh-pages` branch as a single commit (run it with `DRY_RUN` true first). `run_daily_refresh` does not publish. In the job, `publish` runs last and only if every earlier stage succeeded. Pages is served from branch `gh-pages`, folder `/` (repo Settings > Pages).

## Scheduled job

`jobs/job_daily_refresh.json` defines the Lakeflow job "Ethiopia woreda climate map: daily refresh":
one task per stage, then `publish`. It runs every other day at 07:30 UTC, on the odd days of the month (cron `0 30 7 1/2 * ?`, so the 31st and the 1st are consecutive), and emails the owner on failure. The schedule has been active since 2026-11-17. The file and job names still say "daily" for historical reasons.
Create or update it by running the notebook `ops/create_or_update_job` (dry run first), or from the Jobs UI (Create job > JSON), or with `databricks jobs create --json @jobs/job_daily_refresh.json`,
and set `SCHEDULE` to `paused` or `active` to switch the schedule. If the job file changes, update the job to match.

Publishing refuses data more than 3 days old (set `ALLOW_STALE` on `publish_pages` to override). With a run every other day, one missed run is enough to reach that limit.
`publish_pages` uploads only files that changed since the last publish. The Mapbox token in `config.js` is a public (`pk.`) token
that GitHub's secret scanner flags; it was allowed once through the one-time web bypass and is not re-sent unless it changes. The token cannot be URL-restricted without a payment method on the Mapbox account; it is a free-tier public token, so the worst case is that the basemap stops loading.

## Delta tables

The notebook `pipeline/write_delta_tables` (job task `delta_tables`, between the data stages and `publish`) stores every import as a Delta table in `idm_conflict_and_health.ethiopia_climate`, for analyses beyond the map:

| Table | One row per | Update rule |
|---|---|---|
| `heat_daily` | woreda and day | upsert |
| `heat_forecast` | woreda, day and forecast issue time | append, past forecasts kept |
| `flood_discharge` | gauge and day, 1997 to now | upsert |
| `flood_forecast` | gauge, day and fetch time | append, past forecasts kept |
| `flood_gauges` | gauge | upsert |
| `rainfall_dekad` | woreda and dekad | upsert (preliminary values replaced by final ones) |
| `rainfall_dekad_catchment` | gauge catchment and dekad | upsert |
| `food_prices` | market and month (RTFP file) | replaced when a new release arrives; older releases in Delta history |
| `ethiomet_bulletin` | bulletin, product and day | upsert |
| `woreda_monthly_metrics` | woreda and month | upsert |
| `woreda_attributes` | woreda | upsert |
| `woreda_metric_definitions` | metric | upsert |

Woredas are keyed by `adm3_pcode`. Every table has `loaded_at` and `row_hash`. Known gaps in the sources: `heat_daily` is missing one HeatReady project (287 woredas) on 2023-09-10, 2023-09-11, 2026-03-24 and 2026-03-25; `flood_discharge` has no values before 1997. The first run is a dry run (`DRY_RUN` true prints counts and writes nothing); a table that fails prints a WARNING and the run carries on, so a table problem never blocks `publish`. Check the task log after each run for `WARNING`. The Volume files remain the source for the site; the tables are written from them.

## Data inputs and refresh

Every input, where it comes from and how it is kept current. "Every run" means every other day (see Scheduled job).

| Input | Source | Used for | Refreshed by | Cadence |
|---|---|---|---|---|
| Daily heat metrics (observed) | CrisisReady HeatReady API: ERA5-Land, with Open-Meteo for the latest days | Heat layers; table `heat_daily` | Job task `heat_download` (re-pulls the two latest months) | Every run. ERA5 values arrive about a week late; the newest days are provisional (Open-Meteo) until ERA5 replaces them |
| Heat forecast, 6 days | HeatReady API (Open-Meteo) | Forecast layers; table `heat_forecast` | Job task `heat_forecast` | Every run; the API itself refreshes about 06:00 UTC daily |
| Population and age structure | LandScan Global 2024 (population); WorldPop R2025A (age), both through HeatReady | Population and exposure layers; table `woreda_attributes` | Manual: `heat_api.py vuln` | Only when a new version is adopted |
| Heat reference climatology (2016-2025) | HeatReady (computed once per project) | Anomaly layers, `ref_*` columns | Manual, one-off per HeatReady project | Static |
| El Nino index (ONI) | NOAA Climate Prediction Center, `oni.ascii.txt` | El Nino flags on the charts | Job task `oni` (soft) | Every run; NOAA adds one season early each month |
| River discharge and 30-day forecast | GloFAS v4 (Copernicus EMS) through the Open-Meteo Flood API | Flood layer; tables `flood_discharge`, `flood_forecast` | Job task `flood_gauges` | Every run. History starts in 1997 |
| Flood gauges and trigger levels | OCHA-DAP ds-aa-eth-flooding dashboard | Gauge list, trigger levels; table `flood_gauges` | Job task `flood_gauges` (re-reads the dashboard) | Every run. A gauge OCHA adds later also needs `flood_gauges.py cells` once, by hand |
| Flood return levels (RP2, RP5, RP10) | Derived: Gumbel fit to annual peaks of the GloFAS series | Flood thresholds | Job task `flood_gauges` (recomputed) | Every run |
| Rainfall, 10-day dekads | CHIRPS v3 (Climate Hazards Center, UC Santa Barbara) | Rain layer; tables `rainfall_dekad`, `rainfall_dekad_catchment` | Job task `rainfall` (soft) | Every run. Final data run 4 to 6 weeks behind; newer dekads are preliminary |
| Rainfall baseline 1991-2020 | CHIRPS v3 yearly files | Percent of normal and percentile | Manual, cached once: `chirps.py baseline` | Static |
| Food prices | World Bank Real-Time Food Prices, market level (microdata catalog 4483) | Food layer; table `food_prices` | Job task `food_prices` (`COMMAND` = `update`) | Every run checks for a new release and downloads it only if there is one |
| Weather bulletin | Ethiopian Meteorology Institute (EthioMet) | Bulletin panel; table `ethiomet_bulletin` | Job task `ethiomet_bulletin` (soft) | Every run; shows the newest bulletin only, and the table keeps each one from now on |
| Woreda boundaries | OCHA COD-AB admin 3 (shapefile in the Volume) | Map polygons, woreda names | Manual | Only when OCHA publishes a new version |
| River network and basins | HydroRIVERS and HydroBASINS (HydroSHEDS) | Gauge snapping, catchments (`rivers.js`) | Manual: `rivers.py` | Static |
| Basemap | Mapbox with OpenStreetMap data | Map background in the browser | Live service; the public token is a secret in the scope | Not part of the pipeline |

Soft stages (`oni`, `rainfall`, `ethiomet_bulletin`) only warn on failure and keep the previous file, so check the task log if one looks stale. After each run, `delta_tables` writes the imports and the monthly metrics to the Delta tables (see Delta tables).

## Refresh details

Every run (every other day) refreshes: HeatReady heat and 6-day forecast, GloFAS river discharge and forecast (14 gauges), CHIRPS rainfall,
the EthioMet bulletin, the NOAA ONI index (El Nino flags), and the monthly woreda aggregation. Food prices: each run asks the World Bank catalog for the newest RTFP release and downloads it only if it changed
(the `food_prices` notebook, `COMMAND` = `update`); if the catalog cannot be reached, the current release is kept. Markets are then re-linked to the months.

Updated by hand when a new version is adopted: the OCHA admin3 boundaries, LandScan and WorldPop population layers,
and HydroRIVERS/HydroBASINS (`app/data/rivers.js`). The RP2/RP5 flood thresholds are not manual: `flood_gauges` refits them from the discharge series on every run (Gumbel fit to annual peaks; the series starts in 1997).
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
- `chirps.py`, `ethiomet.py` and `oni.py` must stay scripts: `soft_run.py` runs them as subprocesses so a failure warns instead of blocking `publish`.
- The stage scripts and `config.py` stay flat in `pipeline/` so each file maps to one file in Andrew's repo. Our own changes there are the Databricks paths and secrets (`config.py`), the `-idm` project ids (`heat_api.py`), and `keep="last"` de-duplication (`build_map_data`).

## Upkeep

- The GitHub token (`github_token`) is a classic personal access token that expires 90 days after creation. Replace it in time, with the same notebook that stores secrets, then run `check_github_token`.
- Package versions are pinned in `pipeline/requirements.txt` and in `jobs/job_daily_refresh.json` (the job installs from the JSON). To upgrade, change both, update the job, and run it once by hand.
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
