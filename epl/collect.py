"""Stage 1 - Collection.

Downloads every season CSV from football-data.co.uk and every season page
from Wikipedia, stores them unchanged under data/raw/, and appends a line to
data/raw/manifest.csv (source, url, file, download time, size, sha256) so each
result can be traced back to the exact file it came from.
"""
from __future__ import annotations

import csv
import hashlib
import time
from datetime import datetime, timezone

import requests

from epl.config import (FD_URL, MANIFEST, RAW_FD, RAW_WIKI, SEASONS,
                        USER_AGENT, WIKI_URL, season_start_year)


def _download(url: str, dest, session: requests.Session) -> dict:
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return {
        "url": url,
        "file": dest.relative_to(MANIFEST.parent).as_posix(),
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": len(resp.content),
        "sha256": hashlib.sha256(resp.content).hexdigest(),
    }


def collect(seasons: list[str] | None = None, refresh_current_only: bool = False) -> list[dict]:
    """Download raw files. With refresh_current_only, only the last season is fetched."""
    seasons = seasons or SEASONS
    if refresh_current_only:
        seasons = seasons[-1:]
    RAW_FD.mkdir(parents=True, exist_ok=True)
    RAW_WIKI.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    records = []
    for code in seasons:
        rec = _download(FD_URL.format(season=code), RAW_FD / f"E0_{code}.csv", session)
        records.append({"source": "football-data", "season": code, **rec})
        y = season_start_year(code)
        rec = _download(WIKI_URL.format(start=y, end=str(y + 1)[2:]),
                        RAW_WIKI / f"{y}-{str(y + 1)[2:]}.html", session)
        records.append({"source": "wikipedia", "season": code, **rec})
        print(f"  {code}: football-data + wikipedia downloaded")
        time.sleep(0.5)  # be polite to both servers

    new_file = not MANIFEST.exists()
    with MANIFEST.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(records[0].keys()))
        if new_file:
            writer.writeheader()
        writer.writerows(records)
    return records


if __name__ == "__main__":
    collect()
