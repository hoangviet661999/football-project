"""End-to-end pipeline with a quality gate.

    uv run python -m epl.pipeline              # full rebuild from existing raw files
    uv run python -m epl.pipeline --download   # re-download all 13 seasons first
    uv run python -m epl.pipeline --refresh    # weekly: re-download the current season only

The database is built into data/epl_staging.duckdb. Only if every QA check
passes (no FAIL) is it analysed and copied over data/epl.duckdb, the file the
dashboard reads. A failed load leaves the published database untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from epl import analysis, qa
from epl.clean import clean_all
from epl.collect import collect
from epl.config import DATA, DB_PATH
from epl.store import build_database

STAGING = DATA / "epl_staging.duckdb"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true", help="re-download all seasons")
    ap.add_argument("--refresh", action="store_true", help="re-download the current season only")
    args = ap.parse_args(argv)

    if args.download or args.refresh:
        print("1/5 Collecting raw files")
        collect(refresh_current_only=args.refresh)
    print("2/5 Cleaning")
    matches, changes, log = clean_all()
    print("3/5 Integrating and storing (staging)")
    STAGING.unlink(missing_ok=True)
    build_database(matches, changes, log, STAGING)
    print("4/5 Quality assurance")
    if not qa.run(STAGING):
        print("\nQA FAILED: the published database was not changed. See reports/data_quality.md")
        return 1
    print("5/5 Analysis and publication")
    params = analysis.run(STAGING)
    tmp = DB_PATH.with_suffix(".tmp")
    shutil.copyfile(STAGING, tmp)
    os.replace(tmp, DB_PATH)
    print(json.dumps(params, indent=2, default=str))
    print(f"\nPublished {DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
