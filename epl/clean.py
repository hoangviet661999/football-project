"""Stage 2 - Cleaning.

Turns the raw files into two tidy tables and a cleaning log:

* matches            one row per EPL match, harmonised columns and types
* coaching_changes   one row per coaching change from the Wikipedia tables
* cleaning_log       every rule applied, with the number of rows affected

Rule violations are flagged, never silently dropped, so that the QA stage
can report them.
"""
from __future__ import annotations

import re
from datetime import datetime
from io import StringIO

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from epl.config import RAW_FD, RAW_WIKI, SEASONS, season_label, season_start_year

# Columns kept from football-data (renamed to readable snake_case).
FD_COLUMNS = {
    "Date": "date_raw", "Time": "kickoff", "HomeTeam": "home_team", "AwayTeam": "away_team",
    "FTHG": "home_goals", "FTAG": "away_goals", "FTR": "result",
    "HTHG": "home_goals_ht", "HTAG": "away_goals_ht", "Referee": "referee",
    "HS": "home_shots", "AS": "away_shots", "HST": "home_sot", "AST": "away_sot",
    "HF": "home_fouls", "AF": "away_fouls", "HC": "home_corners", "AC": "away_corners",
    "HY": "home_yellow", "AY": "away_yellow", "HR": "home_red", "AR": "away_red",
    "HxG": "home_xg", "AxG": "away_xg",
    "PSCH": "psc_home", "PSCD": "psc_draw", "PSCA": "psc_away",
    "AvgCH": "avgc_home", "AvgCD": "avgc_draw", "AvgCA": "avgc_away",
}
INT_COLUMNS = ["home_goals", "away_goals", "home_goals_ht", "away_goals_ht",
               "home_shots", "away_shots", "home_sot", "away_sot",
               "home_fouls", "away_fouls", "home_corners", "away_corners",
               "home_yellow", "away_yellow", "home_red", "away_red"]
FOOTNOTE = re.compile(r"\[[^\]]*\]")


class Log:
    """Collects cleaning actions for the cleaning_log table."""

    def __init__(self):
        self.rows: list[dict] = []

    def add(self, source: str, season: str | None, rule: str, n: int, detail: str = ""):
        self.rows.append({"source": source, "season": season, "rule": rule,
                          "rows_affected": int(n), "detail": detail})

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["source", "season", "rule", "rows_affected", "detail"])


def _parse_fd_date(s: str):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _normalise_referee(name):
    if not isinstance(name, str):
        return name
    name = " ".join(name.split())          # trims and collapses spaces
    return name[:1].upper() + name[1:]      # 'l Mason' -> 'L Mason'


def clean_matches(log: Log) -> pd.DataFrame:
    frames = []
    for code in SEASONS:
        raw = pd.read_csv(RAW_FD / f"E0_{code}.csv", encoding="utf-8-sig", dtype=str)
        blank = raw["HomeTeam"].isna() | (raw["HomeTeam"].str.strip() == "")
        if blank.any():
            log.add("football-data", code, "drop blank trailing rows", blank.sum())
        raw = raw[~blank]
        df = pd.DataFrame({new: raw[old] if old in raw else np.nan
                           for old, new in FD_COLUMNS.items()})
        df.insert(0, "season", code)

        # Dates: two formats are used across seasons (dd/mm/yy and dd/mm/yyyy).
        short = df["date_raw"].str.len() == 8
        if short.any():
            log.add("football-data", code, "parse 2-digit-year dates", short.sum(), "dd/mm/yy -> date")
        df["date"] = df["date_raw"].map(_parse_fd_date)
        bad = df["date"].isna().sum()
        if bad:
            log.add("football-data", code, "unparseable date (kept, flagged)", bad)

        # Text fields.
        for col in ("home_team", "away_team", "result"):
            df[col] = df[col].str.strip()
        before = df["referee"].copy()
        df["referee"] = df["referee"].map(_normalise_referee)
        changed = (before.fillna("") != df["referee"].fillna("")).sum()
        if changed:
            fixed = sorted(set(before[before != df["referee"]].dropna()))
            log.add("football-data", code, "normalise referee name (spaces, case)", changed,
                    ", ".join(repr(x) for x in fixed))

        for col in INT_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        for col in ("home_xg", "away_xg", "psc_home", "psc_draw", "psc_away",
                    "avgc_home", "avgc_draw", "avgc_away"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        frames.append(df.drop(columns=["date_raw"]))

    m = pd.concat(frames, ignore_index=True)

    # Closing odds: Pinnacle up to 2018/19, market average from 2019/20 (see proposal s.3).
    use_psc = m["season"] <= "1819"
    m["odds_source"] = np.where(use_psc, "Pinnacle closing", "Market average closing")
    for side in ("home", "draw", "away"):
        m[f"close_{side}"] = np.where(use_psc, m[f"psc_{side}"], m[f"avgc_{side}"])
    log.add("football-data", None, "select closing odds source", len(m),
            "Pinnacle (PSC*) for 2014/15-2018/19, market average (AvgC*) from 2019/20")

    # Validity rules (flag only).
    m["flag_sot_gt_shots"] = (m["home_sot"] > m["home_shots"]) | (m["away_sot"] > m["away_shots"])
    expected = np.select([m["home_goals"] > m["away_goals"], m["home_goals"] < m["away_goals"]],
                         ["H", "A"], "D")
    m["flag_result_mismatch"] = m["result"] != expected
    m["flag_negative"] = (m[INT_COLUMNS] < 0).any(axis=1)
    m["flag_duplicate"] = m.duplicated(["season", "home_team", "away_team"], keep=False)
    for flag in ("flag_sot_gt_shots", "flag_result_mismatch", "flag_negative", "flag_duplicate"):
        log.add("football-data", None, f"rule check: {flag[5:]}", m[flag].sum(), "flagged, not dropped")
    m["match_id"] = (m["season"] + "_" + pd.to_datetime(m["date"]).dt.strftime("%Y%m%d") + "_"
                     + m["home_team"].str.replace(r"\W", "", regex=True) + "_"
                     + m["away_team"].str.replace(r"\W", "", regex=True))
    return m


def _strip(value) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(FOOTNOTE.sub("", value).split())


def clean_coaching_changes(log: Log) -> pd.DataFrame:
    frames = []
    for code in SEASONS:
        y = season_start_year(code)
        html = (RAW_WIKI / f"{y}-{str(y + 1)[2:]}.html").read_text(encoding="utf-8")
        heading = BeautifulSoup(html, "lxml").find(id="Managerial_changes")
        if heading is None:
            log.add("wikipedia", code, "managerial changes table missing", 1)
            continue
        table = pd.read_html(StringIO(str(heading.find_next("table"))))[0]
        # The position column has three names across seasons.
        pos_col = next(c for c in table.columns if "osition" in c)
        if pos_col != "Position in table":
            log.add("wikipedia", code, "rename position column", len(table), f"'{pos_col}' -> table_position")
        table = table.rename(columns={pos_col: "table_position"})
        n_notes = table.astype(str).apply(lambda c: c.str.contains(r"\[", regex=True)).to_numpy().sum()
        log.add("wikipedia", code, "remove footnote markers", n_notes, "e.g. '[61]'")
        df = pd.DataFrame({
            "season": code,
            "team_wiki": table["Team"].map(_strip),
            "outgoing_raw": table["Outgoing manager"].map(_strip),
            "departure": table["Manner of departure"].map(_strip),
            "vacancy_date": pd.to_datetime(table["Date of vacancy"].map(_strip), format="%d %B %Y", errors="coerce"),
            "table_position": table["table_position"].map(_strip),
            "incoming_raw": table["Incoming manager"].map(_strip),
            "appointment_date": pd.to_datetime(table["Date of appointment"].map(_strip), format="%d %B %Y", errors="coerce"),
        })
        frames.append(df)
    c = pd.concat(frames, ignore_index=True)

    interim_pat = r"\s*\((?:interim|caretaker)[^)]*\)"
    c["incoming_interim"] = c["incoming_raw"].str.contains(interim_pat, case=False, regex=True)
    c["outgoing_interim"] = c["outgoing_raw"].str.contains(interim_pat, case=False, regex=True) | \
        c["departure"].str.contains("interim|caretaker", case=False)
    c["incoming_coach"] = c["incoming_raw"].str.replace(interim_pat, "", case=False, regex=True).str.strip()
    c["outgoing_coach"] = c["outgoing_raw"].str.replace(interim_pat, "", case=False, regex=True).str.strip()
    log.add("wikipedia", None, "flag interim / caretaker appointments", c["incoming_interim"].sum())
    bad = c["vacancy_date"].isna() | c["appointment_date"].isna()
    if bad.any():
        log.add("wikipedia", None, "unparseable change date (kept, flagged)", bad.sum())
    c["pre_season"] = c["table_position"].str.lower().eq("pre-season")
    c["season_label"] = c["season"].map(season_label)
    return c.drop(columns=["incoming_raw", "outgoing_raw"])


def clean_all():
    log = Log()
    matches = clean_matches(log)
    changes = clean_coaching_changes(log)
    return matches, changes, log.frame()


if __name__ == "__main__":
    m, c, lg = clean_all()
    print(m.shape, c.shape)
    print(lg.to_string())
