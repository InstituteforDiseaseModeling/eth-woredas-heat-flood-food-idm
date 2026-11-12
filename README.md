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
The publish step (force-push of `app/` to `gh-pages`) is not built yet.

## Secrets

Scope `ethiopia_climate`: `heatready_username`, `heatready_key`, `mapbox_token`, `github_token`.
Store them with the utility notebook `12_api_keys_as_secrets` (`idm_databricks_utilities`). Never put them in code, widgets or files.

## Settings

`pipeline/config.py` holds the paths, the secret scope and the publish repo
(`InstituteforDiseaseModeling/eth-woredas-heat-flood-food-idm`). Each can be overridden with an environment variable.

*Owner: IDM data management*
