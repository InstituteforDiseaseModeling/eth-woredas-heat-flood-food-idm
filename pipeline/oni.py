"""Download NOAA CPC's Oceanic Nino Index (ONI) to build/oni.ascii.txt, used for the map's El Nino flags.

NOAA adds one 3-month season early each month. The file is replaced only if the download looks like a
valid ONI table (header, one season per row, at least as many rows as the current file), so a bad or
partial download never overwrites a good file. Run by the job as a soft stage through soft_run.py:
a failure only warns and the previous file stays.

Standard library only; no secrets.

    python oni.py
"""
import time
import urllib.request

import config

URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
OUT = config.BUILD / "oni.ascii.txt"
HEADER = ["SEAS", "YR", "TOTAL", "ANOM"]
SEASONS = "DJF JFM FMA MAM AMJ MJJ JJA JAS ASO SON OND NDJ".split()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def valid_rows(text):
    """Return the data rows if text is an ONI table, else raise ValueError."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or lines[0].split() != HEADER:
        raise ValueError(f"unexpected header: {lines[0][:60] if lines else 'empty file'!r}")
    rows = [ln.split() for ln in lines[1:]]
    for p in rows:
        if len(p) != 4 or p[0] not in SEASONS:
            raise ValueError(f"unexpected row: {' '.join(p)!r}")
        int(p[1])
        float(p[3])
    if len(rows) < 900:   # 1950 to now is more than 900 seasons
        raise ValueError(f"only {len(rows)} rows")
    return rows


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "eth-woreda-heat-map/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8")
    rows = valid_rows(text)
    have = valid_rows(OUT.read_text()) if OUT.exists() else []
    if len(rows) < len(have):
        raise ValueError(f"download has {len(rows)} seasons, current file has {len(have)}; keeping the current file")
    last = f"{rows[-1][0]} {rows[-1][1]} (ONI {rows[-1][3]})"
    if OUT.exists() and OUT.read_text() == text:
        log("ONI up to date, last season", last)
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(text)
    tmp.replace(OUT)
    log(f"ONI updated: {len(have)} -> {len(rows)} seasons, last season {last}")


if __name__ == "__main__":
    main()
