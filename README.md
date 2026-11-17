# Ethiopia woreda heat, flood, rain and food-price map

Daily-refreshed map of 1,148 Ethiopian woredas: heat metrics (HeatReady), river flood forecasts
(GloFAS via Open-Meteo), rainfall (CHIRPS), food prices (World Bank RTFP) and the EthioMet bulletin.
The pipeline runs on Databricks; the site is published to GitHub Pages from this repo's `gh-pages` branch.

Originally built by Andrew Schroeder (`ASchroederCR/eth-woredas-heat-flood-food`) and migrated to Databricks.

## Layout

| Path | What it is |
|---|---|
| `pipeline/` | Scripts and notebooks that make the data files (see below) |
| `app/` | The static site: `index.html`, `app.js`, `style.css`, `.nojekyll`. Generated files (`app/data/*.js`, `app/config.js`) are written to the Databricks Volume, not stored here |
| `pipeline/job_daily_refresh.json` | Lakeflow job definition (paused until switched on) |

## Where the data lives

Unity Catalog Volume `idm_conflict_and_health.ethiopia_climate.heat_map_files`:
`build/` (downloaded rows and caches), `boundaries/` (OCHA admin3 shapefile), `app/` (site plus generated data), `reference/` (Andrew's outputs, for comparison).

## Running it

- **Whole pipeline:** notebook `pipeline/run_daily_refresh` (set `DRY_RUN` to `false`), or the Lakeflow job.
- **One stage:** `pipeline/run_pipeline_stage`; the map build is the notebook `pipeline/build_map_data`.
- **Checks:** `check_boundary`, `check_github_token`, `test_heatready_api`, `compare_with_andrew`.
- **One-off setup:** `create_heat_projects` creates the six `eth-woreda-heat-N-idm` projects in HeatReady.

Stage order: `setup_site`, HeatReady download and forecast, `build_map_data`, `flood_gauges`,
`food_prices`, then `rainfall` and `ethiomet` (the last two only warn on failure).
Publishing is a separate notebook, `pipeline/publish_pages`: it force-pushes the Volume's `app/` to the `gh-pages` branch as a single commit (run it with `DRY_RUN` true first). `run_daily_refresh` does not publish. In the job, `publish` runs last and only if every earlier stage succeeded. After the first publish, turn on Pages in the repo settings (branch `gh-pages`, folder `/`).

## Daily job

`pipeline/job_daily_refresh.json` defines the Lakeflow job "Ethiopia woreda climate map: daily refresh":
one task per stage, then `publish`. It is scheduled for 07:30 UTC but **paused** until switched on, and emails the owner on failure.
Create it from the Jobs UI (Create job > JSON) or with `databricks jobs create --json @pipeline/job_daily_refresh.json`,
run it once by hand, then set the schedule to active. If the job file changes, update the job to match.

Publishing refuses data more than 3 days old (set `ALLOW_STALE` on `publish_pages` to override).
`publish_pages` uploads only files that changed since the last publish. The Mapbox token in `config.js` is a public (`pk.`) token
that GitHub's secret scanner flags; it was allowed once through the one-time web bypass and is not re-sent unless it changes.

## What refreshes and what does not

Every run refreshes: HeatReady heat and 6-day forecast, GloFAS river discharge and forecast (14 gauges), CHIRPS rainfall,
the EthioMet bulletin, and the monthly woreda aggregation. Food prices are re-linked to new months on every run, but new World Bank
prices appear only when the World Bank publishes a new RTFP release.

Updated by hand when a new version is adopted: the OCHA admin3 boundaries, LandScan and WorldPop population layers,
HydroRIVERS/HydroBASINS (`app/data/rivers.js`), and the RP2/RP5 flood thresholds (fitted to 1984-2025 annual peaks).
`pipeline/prepare_projects.py` is the one-time script that split the woredas into HeatReady projects; it is kept for reference
and is not part of the daily run.

## Upkeep

- The GitHub token (`github_token`) is a classic personal access token that expires 90 days after creation. Replace it in time, with the same notebook that stores secrets, then run `check_github_token`.
- `requirements.txt` is not pinned yet: after the first successful job run, pin the versions.
- Notebooks in the Databricks Git folder must be committed and pushed by hand.

## Secrets

Scope `ethiopia_climate`: `heatready_username`, `heatready_key`, `mapbox_token`, `github_token`.
Store them with the utility notebook `12_api_keys_as_secrets` (`idm_databricks_utilities`). Never put them in code, widgets or files.

## Settings

`pipeline/config.py` holds the paths, the secret scope and the publish repo
(`InstituteforDiseaseModeling/eth-woredas-heat-flood-food-idm`). Each can be overridden with an environment variable.

*Owner: IDM data management*
