"""Stages 3 and 4 - Integration and storage.

Builds a DuckDB star schema from the cleaned tables:

  dim_season, dim_team, dim_referee, dim_coaching_change
  fact_match       one row per match
  fact_team_match  two rows per match (one per team), the unit of analysis
  cleaning_log     carried over from the cleaning stage
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from epl.config import COMPLETED_SEASONS, CURRENT_SEASON, DB_PATH, SEASONS, season_label

# football-data short name -> (team_id, Wikipedia / full name)
TEAMS = {
    "Arsenal": ("ARS", "Arsenal"), "Aston Villa": ("AVL", "Aston Villa"),
    "Bournemouth": ("BOU", "Bournemouth"), "Brentford": ("BRE", "Brentford"),
    "Brighton": ("BHA", "Brighton & Hove Albion"), "Burnley": ("BUR", "Burnley"),
    "Cardiff": ("CAR", "Cardiff City"), "Chelsea": ("CHE", "Chelsea"),
    "Coventry": ("COV", "Coventry City"), "Crystal Palace": ("CRY", "Crystal Palace"),
    "Everton": ("EVE", "Everton"), "Fulham": ("FUL", "Fulham"),
    "Huddersfield": ("HUD", "Huddersfield Town"), "Hull": ("HUL", "Hull City"),
    "Ipswich": ("IPS", "Ipswich Town"), "Leeds": ("LEE", "Leeds United"),
    "Leicester": ("LEI", "Leicester City"), "Liverpool": ("LIV", "Liverpool"),
    "Luton": ("LUT", "Luton Town"), "Man City": ("MCI", "Manchester City"),
    "Man United": ("MUN", "Manchester United"), "Middlesbrough": ("MID", "Middlesbrough"),
    "Newcastle": ("NEW", "Newcastle United"), "Norwich": ("NOR", "Norwich City"),
    "Nott'm Forest": ("NFO", "Nottingham Forest"), "QPR": ("QPR", "Queens Park Rangers"),
    "Sheffield United": ("SHU", "Sheffield United"), "Southampton": ("SOU", "Southampton"),
    "Stoke": ("STK", "Stoke City"), "Sunderland": ("SUN", "Sunderland"),
    "Swansea": ("SWA", "Swansea City"), "Tottenham": ("TOT", "Tottenham Hotspur"),
    "Watford": ("WAT", "Watford"), "West Brom": ("WBA", "West Bromwich Albion"),
    "West Ham": ("WHU", "West Ham United"), "Wolves": ("WOL", "Wolverhampton Wanderers"),
}


def build_dim_team() -> pd.DataFrame:
    return pd.DataFrame([{"team_id": tid, "fd_name": fd, "team_name": full}
                         for fd, (tid, full) in TEAMS.items()]).sort_values("team_name")


def build_dim_referee(matches: pd.DataFrame) -> pd.DataFrame:
    g = matches.groupby("referee").agg(n_matches=("match_id", "size"),
                                       first_season=("season", "min"),
                                       last_season=("season", "max")).reset_index()
    g["surname"] = g["referee"].str.split().str[-1]
    regular = g[g["n_matches"] >= 30]
    # One-match names sharing a surname with a regular referee: probable typos.
    # They are kept as recorded and only flagged (no guessing of the true name).
    g["suspected_typo_of"] = g.apply(
        lambda r: ", ".join(regular.loc[(regular["surname"] == r["surname"])
                                        & (regular["referee"] != r["referee"]), "referee"])
        if r["n_matches"] <= 2 else "", axis=1)
    g["referee_id"] = ["R%02d" % i for i in range(1, len(g) + 1)]
    return g[["referee_id", "referee", "n_matches", "first_season", "last_season", "suspected_typo_of"]]


def add_market_probabilities(m: pd.DataFrame) -> pd.DataFrame:
    inv = 1 / m[["close_home", "close_draw", "close_away"]]
    m["overround"] = inv.sum(axis=1)
    m["p_home"] = inv["close_home"] / m["overround"]
    m["p_draw"] = inv["close_draw"] / m["overround"]
    m["p_away"] = inv["close_away"] / m["overround"]
    return m


def build_team_match(m: pd.DataFrame) -> pd.DataFrame:
    """Reshape each match into two rows: one from each team's point of view."""
    sides = []
    for side, opp, sign in (("home", "away", 1), ("away", "home", 0)):
        t = pd.DataFrame({
            "match_id": m["match_id"], "season": m["season"], "date": m["date"],
            "team_id": m[f"{side}_team_id"], "opponent_id": m[f"{opp}_team_id"],
            "is_home": bool(sign), "referee_id": m["referee_id"],
            "goals_for": m[f"{side}_goals"], "goals_against": m[f"{opp}_goals"],
            "shots_for": m[f"{side}_shots"], "shots_against": m[f"{opp}_shots"],
            "sot_for": m[f"{side}_sot"], "sot_against": m[f"{opp}_sot"],
            "fouls": m[f"{side}_fouls"], "yellow": m[f"{side}_yellow"], "red": m[f"{side}_red"],
            "corners_for": m[f"{side}_corners"],
            "xg_for": m[f"{side}_xg"], "xg_against": m[f"{opp}_xg"],
            "p_win": m[f"p_{side}"], "p_draw": m["p_draw"], "p_loss": m[f"p_{opp}"],
        })
        sides.append(t)
    tm = pd.concat(sides, ignore_index=True)
    tm["points"] = np.select([tm["goals_for"] > tm["goals_against"],
                              tm["goals_for"] == tm["goals_against"]], [3, 1], 0)
    tm["xpts"] = 3 * tm["p_win"] + tm["p_draw"]
    tm["sot_diff"] = tm["sot_for"] - tm["sot_against"]
    tm["goal_diff"] = tm["goals_for"] - tm["goals_against"]
    tm = tm.sort_values(["team_id", "date", "match_id"]).reset_index(drop=True)
    tm["team_match_no"] = tm.groupby(["team_id", "season"]).cumcount() + 1
    return tm


def assign_coaches(tm: pd.DataFrame, changes: pd.DataFrame) -> pd.Series:
    """Coach in charge for each team-match.

    Latest appointment on or before the match date; between a vacancy and the
    next appointment the team is under a caretaker. Changes made while a club
    was outside the EPL are not on the EPL season pages, so an appointment is
    only carried forward within an unbroken run of EPL seasons.
    """
    seasons_in = tm.groupby("team_id")["season"].apply(lambda s: sorted(set(s)))
    chain = {}
    for team, ss in seasons_in.items():
        k = 0
        for i, s in enumerate(ss):
            if i and SEASONS.index(s) != SEASONS.index(ss[i - 1]) + 1:
                k += 1
            chain[(team, s)] = k
    ch = changes.dropna(subset=["team_id"]).copy()
    ch["chain"] = [chain.get((t, s), -1) for t, s in zip(ch["team_id"], ch["season"])]
    coach = pd.Series("Not recorded", index=tm.index, dtype=object)
    for team, rows in tm.groupby("team_id"):
        ev = ch[ch["team_id"] == team].sort_values("appointment_date")
        for idx, r in rows.iterrows():
            c = chain[(team, r["season"])]
            e = ev[ev["chain"] == c]
            d = pd.Timestamp(r["date"])
            past = e[e["appointment_date"] <= d]
            # A coach who leaves on a match day is still in charge of that match.
            vac = e[(e["vacancy_date"] < d) & (e["appointment_date"] > d)]
            if len(vac):
                coach[idx] = "Caretaker"
            elif len(past):
                last = past.iloc[-1]
                coach[idx] = last["incoming_coach"] + (" (interim)" if last["incoming_interim"] else "")
            elif len(e):
                coach[idx] = e.iloc[0]["outgoing_coach"]
    return coach


def build_database(matches: pd.DataFrame, changes: pd.DataFrame, log: pd.DataFrame,
                   db_path=DB_PATH) -> None:
    dim_team = build_dim_team()
    fd_to_id = {fd: tid for fd, (tid, _) in TEAMS.items()}
    wiki_to_id = {full: tid for _, (tid, full) in TEAMS.items()}

    unknown = sorted((set(matches["home_team"]) | set(matches["away_team"])) - set(fd_to_id))
    if unknown:
        raise ValueError(f"Unmapped football-data team names: {unknown}")
    m = matches.copy()
    m["home_team_id"] = m["home_team"].map(fd_to_id)
    m["away_team_id"] = m["away_team"].map(fd_to_id)

    dim_ref = build_dim_referee(m)
    m = m.merge(dim_ref[["referee", "referee_id"]], on="referee", how="left")
    m = add_market_probabilities(m)

    ch = changes.copy()
    ch["team_id"] = ch["team_wiki"].map(wiki_to_id)
    log = pd.concat([log, pd.DataFrame([{
        "source": "integration", "season": None, "rule": "unmapped Wikipedia team names",
        "rows_affected": int(ch["team_id"].isna().sum()),
        "detail": ", ".join(sorted(ch.loc[ch["team_id"].isna(), "team_wiki"].unique()))}])])
    ch = ch.sort_values(["team_id", "appointment_date"]).reset_index(drop=True)
    ch.insert(0, "change_id", ["C%03d" % i for i in range(1, len(ch) + 1)])

    tm = build_team_match(m)
    tm["coach"] = assign_coaches(tm, ch)

    dim_season = pd.DataFrame({"season": SEASONS, "season_label": [season_label(s) for s in SEASONS],
                               "completed": [s in COMPLETED_SEASONS for s in SEASONS],
                               "no_crowd_matches": [s in ("1920", "2021") for s in SEASONS]})
    fact_match = m.drop(columns=["home_team", "away_team", "referee"])

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    for name, df in {"dim_season": dim_season, "dim_team": dim_team, "dim_referee": dim_ref,
                     "dim_coaching_change": ch, "fact_match": fact_match,
                     "fact_team_match": tm, "cleaning_log": log}.items():
        con.register("tmp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    con.close()


if __name__ == "__main__":
    from epl.clean import clean_all
    mt, chg, lg = clean_all()
    build_database(mt, chg, lg)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    print(con.sql("SELECT table_name, estimated_size FROM duckdb_tables()"))
    print(con.sql("SELECT coach, count(*) n FROM fact_team_match WHERE team_id='ARS' GROUP BY coach ORDER BY min(date)"))
    print(con.sql("SELECT coach, count(*) n FROM fact_team_match GROUP BY coach ORDER BY n DESC LIMIT 5"))
    print(con.sql("SELECT team_id, count(*) FROM fact_team_match WHERE coach='Not recorded' GROUP BY 1 ORDER BY 2 DESC"))
