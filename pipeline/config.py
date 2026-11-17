"""Shared paths and credentials for the Ethiopia woreda heat / flood / rain / food pipeline.

Everything the scripts used to find relative to their own folder (build/, app/, ../Boundaries/,
../heat_api_key.txt, ../Mapbox_Public_Token.txt) now comes from here.

Paths
    ETH_BASE (env var) overrides the default Volume:
    /Volumes/idm_conflict_and_health/ethiopia_climate/heat_map_files
    BUILD = BASE/build      raw downloads, caches, intermediate files
    APP   = BASE/app        site files published to GitHub Pages (app/data/*.js are generated)
    SHP   = BASE/boundaries/eth_admin3.shp   OCHA COD-AB admin-3 woredas

Credentials (never stored in files)
    Each secret is read from an environment variable first, then from the Databricks secret scope
    ETH_SECRET_SCOPE (default "ethiopia_climate"):

        secret key           environment variable    used by
        heatready_username   HEATREADY_USERNAME      heat_api.py
        heatready_key        HEATREADY_KEY           heat_api.py
        mapbox_token         MAPBOX_TOKEN            build_map_data.py (public token, written to config.js)
        github_token         GITHUB_TOKEN            publish step (push to gh-pages)
"""
import os
from pathlib import Path

# This folder. Scripts run as Lakeflow job tasks have no __file__ of their own, so they use this instead.
PIPELINE_DIR = Path(__file__).resolve().parent
BASE = Path(os.environ.get("ETH_BASE", "/Volumes/idm_conflict_and_health/ethiopia_climate/heat_map_files"))
BUILD = BASE / "build"
APP = BASE / "app"
SHP = BASE / "boundaries" / "OCHA_COD_AB" / "OCHA_COD_AB" / "eth_admin3.shp"
SCOPE = os.environ.get("ETH_SECRET_SCOPE", "ethiopia_climate")
PUBLISH_REPO = os.environ.get("ETH_PUBLISH_REPO", "InstituteforDiseaseModeling/eth-woredas-heat-flood-food-idm")  # GitHub Pages repo (owner/name); branch gh-pages


def secret(key, env=None):
    """Return a credential from an environment variable, else from the Databricks secret scope."""
    if env and os.environ.get(env):
        return os.environ[env]
    try:
        from databricks.sdk.runtime import dbutils
        return dbutils.secrets.get(SCOPE, key)
    except Exception as e:
        raise RuntimeError(
            f"Secret '{key}' not available: set environment variable {env} or create secret {SCOPE}/{key}"
        ) from e
