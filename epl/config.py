"""Project-wide paths and constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW_FD = DATA / "raw" / "football-data"
RAW_WIKI = DATA / "raw" / "wikipedia"
MANIFEST = DATA / "raw" / "manifest.csv"
DB_PATH = DATA / "epl.duckdb"
REPORTS = ROOT / "reports"

# Season codes as used by football-data.co.uk ("1415" = 2014/15).
SEASONS = ["1415", "1516", "1617", "1718", "1819", "1920", "2021",
           "2122", "2223", "2324", "2425", "2526", "2627"]
CURRENT_SEASON = "2627"
COMPLETED_SEASONS = [s for s in SEASONS if s != CURRENT_SEASON]

FD_URL = "https://www.football-data.co.uk/mmz4281/{season}/E0.csv"
WIKI_URL = "https://en.wikipedia.org/wiki/{start}%E2%80%93{end}_Premier_League"

# Generic client name (no personal details sent to external services).
USER_AGENT = "epl-monitor/0.1 (educational data-management project)"


def season_label(code: str) -> str:
    """'1415' -> '2014/15'."""
    return f"20{code[:2]}/{code[2:]}"


def season_start_year(code: str) -> int:
    return 2000 + int(code[:2])


# Analysis parameters (see proposal section 5).
CUSUM_K = 0.5            # reference value, in standard deviations
CUSUM_ARL0_ONE_SIDED = 76  # in-control run length per side (two seasons); two-sided ~38
SPRT_ALPHA = 0.05
SPRT_BETA = 0.20
SPRT_DELTA_SD = 0.5      # improvement to detect, in per-match standard deviations
SPRT_BASELINE_MATCHES = 19
SPRT_MIN_BASELINE = 5
SPRT_MAX_MATCHES = 38
ANOM_ALPHA = 0.05
ANOM_MIN_MATCHES = 30
OUTLIER_Z = 3.0
OUTLIER_CHI2_Q = 0.99
RATING_WINDOW = 38       # matches used for a team's rolling strength rating
