"""Copy the static map site files into the Volume's app/ folder.

The pipeline scripts read and re-stamp app/index.html and write app/data/*.js, so index.html
must exist in the Volume before any other task runs. The generated files (app/data/*.js and
app/config.js) are not copied here; the pipeline writes them.

Source: ../app (index.html, app.js, style.css, .nojekyll). Idempotent: safe to run
every day. Update the files in the source folder to change the site.
"""
import shutil
from pathlib import Path

import config

SRC = Path(__file__).resolve().parent.parent / "app"
FILES = ["index.html", "app.js", "style.css", ".nojekyll"]

config.APP.mkdir(parents=True, exist_ok=True)
(config.APP / "data").mkdir(exist_ok=True)

for name in FILES:
    src = SRC / name
    if not src.exists():
        raise FileNotFoundError(f"Site file not found: {src}")
    shutil.copyfile(src, config.APP / name)
    print(f"copied {name} ({src.stat().st_size:,} bytes) -> {config.APP / name}")
