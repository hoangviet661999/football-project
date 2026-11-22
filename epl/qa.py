"""Stage 5 - Quality assurance.

Runs automated checks on a freshly built database. Each check returns
PASS, WARN or FAIL. Any FAIL blocks publication of the database to the
dashboard (see pipeline.py). Results are written to the qa_results and
qa_completeness tables and to reports/data_quality.md.
"""
from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pandas as pd

from epl.config import COMPLETED_SEASONS, CURRENT_SEASON, REPORTS, SEASONS, season_label

KEY_COLUMNS = ["referee_id", "home_shots", "away_shots", "home_sot", "away_sot", "home_fouls",
               "away_fouls", "home_yellow", "away_yellow", "home_red", "away_red",
               "close_home", "close_draw", "close_away", "home_xg", "away_xg"]


def _check(results, name, status, value, expectation):
    results.append({"check": name, "status": status, "value": str(value), "expectation": expectation})


def run_checks(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    r: list[dict] = []
    q = lambda sql: con.sql(sql).df()

    # Completeness of the season files.
    per_season = q("SELECT season, count(*) n FROM fact_match GROUP BY season ORDER BY season")
    bad = per_season[per_season.season.isin(COMPLETED_SEASONS) & (per_season.n != 380)]
    _check(r, "380 matches in every completed season", "PASS" if bad.empty else "FAIL",
           f"{len(COMPLETED_SEASONS) - len(bad)}/{len(COMPLETED_SEASONS)} seasons", "12/12 seasons")
    missing_seasons = sorted(set(SEASONS) - set(per_season.season))
    _check(r, "all 13 seasons loaded", "PASS" if not missing_seasons else "FAIL",
           f"{len(per_season)} seasons", "13 seasons")

    tm = q("SELECT season, team_id, count(*) n FROM fact_team_match GROUP BY 1, 2")
    done = tm[tm.season.isin(COMPLETED_SEASONS)]
    _check(r, "38 matches per team in completed seasons", "PASS" if (done.n == 38).all() else "FAIL",
           f"{(done.n == 38).sum()}/{len(done)} team-seasons", "all team-seasons = 38")
    teams = tm.groupby("season").team_id.nunique()
    _check(r, "20 teams in every season", "PASS" if (teams == 20).all() else "FAIL",
           f"{(teams == 20).sum()}/{len(teams)} seasons", "20 teams each season")
    cur = tm[tm.season == CURRENT_SEASON].n
    _check(r, "current season: teams within 2 matches of each other",
           "PASS" if cur.max() - cur.min() <= 2 else "WARN", f"{cur.min()} to {cur.max()} matches",
           "spread <= 2 matches")

    two = q("SELECT count(*) bad FROM (SELECT match_id, sum(is_home::int) h, count(*) n "
            "FROM fact_team_match GROUP BY 1) WHERE n <> 2 OR h <> 1").bad[0]
    _check(r, "each match once as home and once as away", "PASS" if two == 0 else "FAIL",
           f"{two} matches violate", "0 matches violate")

    # Validity.
    flags = q("SELECT sum(flag_sot_gt_shots::int) sot, sum(flag_result_mismatch::int) res, "
              "sum(flag_negative::int) neg, sum(flag_duplicate::int) dup FROM fact_match").iloc[0]
    _check(r, "result matches the goals", "PASS" if flags.res == 0 else "FAIL", f"{flags.res} matches", "0")
    _check(r, "no negative counts", "PASS" if flags.neg == 0 else "FAIL", f"{flags.neg} matches", "0")
    _check(r, "no duplicate fixtures", "PASS" if flags.dup == 0 else "FAIL", f"{flags.dup} matches", "0")
    sot_rows = q("SELECT season, date, home_team_id, away_team_id, home_shots, home_sot, away_shots, away_sot "
                 "FROM fact_match WHERE flag_sot_gt_shots")
    detail = "; ".join(f"{x.home_team_id}-{x.away_team_id} {str(x.date)[:10]} (H {x.home_sot}/{x.home_shots}, "
                       f"A {x.away_sot}/{x.away_shots})" for x in sot_rows.itertuples())
    _check(r, "shots on target <= shots", "PASS" if sot_rows.empty else "WARN",
           f"{len(sot_rows)} matches" + (f": {detail}" if detail else ""), "0 (WARN: kept, source value)")

    # Odds.
    odds = q("SELECT season, count(*) FILTER (WHERE close_home IS NULL) miss, min(overround) lo, "
             "max(overround) hi FROM fact_match GROUP BY season")
    _check(r, "closing odds present for every match", "PASS" if odds.miss.sum() == 0 else "FAIL",
           f"{odds.miss.sum()} missing", "0 missing")
    lo, hi = odds.lo.min(), odds.hi.max()
    _check(r, "implied probabilities sum slightly above 1", "PASS" if 1.0 <= lo and hi <= 1.15 else "WARN",
           f"{lo:.3f} to {hi:.3f}", "1.000 to 1.150")
    ov = q("SELECT 1/psc_home / (1/psc_home + 1/psc_draw + 1/psc_away) a, "
           "1/avgc_home / (1/avgc_home + 1/avgc_draw + 1/avgc_away) b FROM fact_match "
           "WHERE psc_home IS NOT NULL AND avgc_home IS NOT NULL")
    corr, mad = ov.a.corr(ov.b), (ov.a - ov.b).abs().mean()
    _check(r, "Pinnacle vs market-average odds agree on overlap seasons",
           "PASS" if corr > 0.98 and mad < 0.03 else "WARN",
           f"r = {corr:.4f}, mean |diff| = {mad:.4f} over {len(ov)} matches", "r > 0.98, mean |diff| < 0.03")

    # Key statistics completeness.
    miss = q("SELECT " + ", ".join(f"count(*) FILTER (WHERE {c} IS NULL) AS {c}" for c in KEY_COLUMNS[:-2])
             + " FROM fact_match").iloc[0]
    _check(r, "no missing referee, shots, fouls or cards", "PASS" if miss.sum() == 0 else "FAIL",
           f"{int(miss.sum())} missing cells", "0")
    xg = q("SELECT season, count(*) FILTER (WHERE home_xg IS NOT NULL) n FROM fact_match GROUP BY 1")
    _check(r, "xG coverage (optional)", "WARN" if (xg.n == 0).any() else "PASS",
           ", ".join(f"{season_label(s)}" for s in xg[xg.n > 0].season) or "none", "optional; used only as cross-check")

    # Integration.
    unm = q("SELECT rows_affected, detail FROM cleaning_log WHERE rule = 'unmapped Wikipedia team names'").iloc[0]
    _check(r, "every Wikipedia team mapped to a team ID", "PASS" if unm.rows_affected == 0 else "FAIL",
           f"{unm.rows_affected} rows {unm.detail}", "0 unmapped")
    dates = q("SELECT count(*) FILTER (WHERE vacancy_date IS NULL OR appointment_date IS NULL) miss, "
              "count(*) FILTER (WHERE date_diff('day', vacancy_date, appointment_date) NOT BETWEEN -60 AND 200) odd, "
              "count(*) n FROM dim_coaching_change").iloc[0]
    _check(r, "coaching-change dates parsed", "PASS" if dates.miss == 0 else "FAIL",
           f"{dates.miss} of {dates.n} missing", "0 missing")
    _check(r, "coaching-change gap between vacancy and appointment plausible",
           "PASS" if dates.odd == 0 else "WARN", f"{dates.odd} outside -60..200 days", "0")
    nr = q("SELECT avg((coach = 'Not recorded')::int) s FROM fact_team_match").s[0]
    _check(r, "coach known for team-matches", "PASS" if nr < 0.1 else "WARN",
           f"{1 - nr:.1%} known", ">= 90% (unknown = change made outside the EPL)")
    typo = q("SELECT referee, n_matches, suspected_typo_of FROM dim_referee WHERE suspected_typo_of <> ''")
    _check(r, "referee names consistent", "PASS" if typo.empty else "WARN",
           "; ".join(f"'{x.referee}' ({x.n_matches} match) may be {x.suspected_typo_of}" for x in typo.itertuples())
           or "none", "0 suspected typos (kept as recorded)")

    # Freshness of the live season.
    last = pd.Timestamp(q(f"SELECT max(date) d FROM fact_match WHERE season = '{CURRENT_SEASON}'").d[0])
    age = (pd.Timestamp(datetime.now(timezone.utc).date()) - last).days
    _check(r, "current season data is fresh", "PASS" if age <= 14 else "WARN",
           f"last match {last.date()} ({age} days ago)", "<= 14 days")

    results = pd.DataFrame(r)
    results.insert(0, "checked_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))

    # Completeness matrix (season x column) for the data-quality panel (V8).
    comp = q("SELECT season, " + ", ".join(f"avg(({c} IS NOT NULL)::int) AS {c}" for c in KEY_COLUMNS)
             + " FROM fact_match GROUP BY season ORDER BY season")
    comp = comp.melt(id_vars="season", var_name="column", value_name="completeness")
    return results, comp


def write_report(results: pd.DataFrame, comp: pd.DataFrame, log: pd.DataFrame) -> None:
    REPORTS.mkdir(exist_ok=True)
    counts = results.status.value_counts().to_dict()
    lines = ["# Data quality report", "",
             f"Checked at {results.checked_at.iloc[0]} UTC. "
             f"Result: {counts.get('PASS', 0)} PASS, {counts.get('WARN', 0)} WARN, {counts.get('FAIL', 0)} FAIL. "
             + ("Published to the dashboard." if counts.get("FAIL", 0) == 0 else "**Blocked: not published.**"),
             "", "## Checks", "", "| Status | Check | Value | Expectation |", "| --- | --- | --- | --- |"]
    lines += [f"| {x.status} | {x.check} | {x.value} | {x.expectation} |" for x in results.itertuples()]
    piv = comp.pivot(index="season", columns="column", values="completeness")
    lines += ["", "## Completeness by season (share of matches with a value)", "",
              "| Season | " + " | ".join(piv.columns) + " |", "| --- |" + " --- |" * len(piv.columns)]
    lines += [f"| {season_label(s)} | " + " | ".join(f"{v:.0%}" for v in row) + " |" for s, row in piv.iterrows()]
    lines += ["", "## Cleaning log", "", "| Source | Season | Rule | Rows | Detail |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {x.source} | {season_label(x.season) if isinstance(x.season, str) else 'all'} | {x.rule} | "
              f"{x.rows_affected} | {x.detail} |" for x in log.itertuples()]
    (REPORTS / "data_quality.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(db_path) -> bool:
    """Run QA on the database at db_path; return True if no check failed."""
    con = duckdb.connect(str(db_path))
    results, comp = run_checks(con)
    for name, df in {"qa_results": results, "qa_completeness": comp}.items():
        con.register("tmp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    log = con.sql("SELECT * FROM cleaning_log").df()
    con.close()
    write_report(results, comp, log)
    print(results[["status", "check", "value"]].to_string(index=False))
    return not (results.status == "FAIL").any()
