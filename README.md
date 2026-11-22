# EPL Performance Monitor

Real change or noise? Outlier detection, ANOM, CUSUM and SPRT on English Premier League data (2014/15 to 2026/27), for club boards, performance analysts and referee assessors. Topic 2 project: see [proposal.md](proposal.md) and the results in [reports/findings.md](reports/findings.md).

## Run it

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and all packages).

```bash
uv sync                                   # install dependencies
uv run python -m epl.pipeline --download  # download all 13 seasons, clean, store, QA, analyse
uv run streamlit run app/dashboard.py     # open the dashboard at http://localhost:8501
```

Weekly during the season:

```bash
uv run python -m epl.pipeline --refresh   # re-download the current season only
```

The pipeline builds `data/epl_staging.duckdb`, runs 21 quality checks, and replaces `data/epl.duckdb` (the file the dashboard reads) only if no check fails. Without a flag it rebuilds from the raw files already downloaded.

## Project layout

| Path | Content |
| --- | --- |
| `epl/collect.py` | Stage 1: download raw files and record the manifest |
| `epl/clean.py` | Stage 2: cleaning rules and cleaning log |
| `epl/store.py` | Stages 3–4: team and referee IDs, team-match reshape, coach assignment, DuckDB star schema |
| `epl/qa.py` | Stage 5: quality checks and `reports/data_quality.md` |
| `epl/metrics.py` | Venue- and opponent-adjusted shots-on-target difference |
| `epl/outliers.py`, `anom.py`, `cusum.py`, `sprt.py` | The four Topic 2 methods |
| `epl/pipeline.py` | End-to-end run with the QA gate |
| `app/dashboard.py` | Streamlit dashboard: Team monitor (V1, V2), Match review (V3), Referee consistency (V4, V5), Coaching change (V6, V7), Data quality (V8) |
| `data/raw/` | Unmodified source files and `manifest.csv` |
| `docs/data_dictionary.md` | Tables, columns and lineage |
| `reports/` | `findings.md`, `data_quality.md` |

## Sources

- [football-data.co.uk](https://www.football-data.co.uk/englandm.php): match results, statistics, referees and closing odds ([column notes](https://www.football-data.co.uk/notes.txt)).
- Wikipedia season pages, "Managerial changes" tables, for example [2025–26 Premier League](https://en.wikipedia.org/wiki/2025%E2%80%9326_Premier_League).
