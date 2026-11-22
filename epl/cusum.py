"""Question 3 - CUSUM: when did a team's underlying performance shift?

Two-sided tabular CUSUM on z_t = (adj_perf_t - mu0) / sigma, run per team and
season. mu0 is the team's rating before its first match of the season. The
decision interval h is calibrated by bootstrap simulation from in-control
residuals so that each side raises a false alarm about once every 76 matches
(two seasons). After an alarm the statistic restarts at zero.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from epl.config import CUSUM_ARL0_ONE_SIDED, CUSUM_K, SEASONS


def _run_length(z: np.ndarray, k: float, h: float) -> int:
    c = 0.0
    for i, x in enumerate(z, 1):
        c = max(0.0, c + x - k)
        if c > h:
            return i
    return len(z)


def calibrate_h(residuals: np.ndarray, k: float = CUSUM_K, target: float = CUSUM_ARL0_ONE_SIDED,
                n_sim: int = 2000, seed: int = 7) -> tuple[float, float]:
    """Find h whose bootstrap in-control ARL (one side) is closest to target."""
    rng = np.random.default_rng(seed)
    z = (residuals - residuals.mean()) / residuals.std(ddof=1)
    horizon = int(target * 12)
    sims = rng.choice(z, size=(n_sim, horizon), replace=True)
    best = None
    for h in np.arange(2.0, 8.01, 0.1):
        arl = np.mean([_run_length(s, k, h) for s in sims[:600]])
        if best is None or abs(arl - target) < abs(best[1] - target):
            best = (round(float(h), 2), float(arl))
        if arl > target * 1.3:
            break
    return best


def run_cusum(tm: pd.DataFrame, sigma: float, h: float, k: float = CUSUM_K) -> pd.DataFrame:
    rows = []
    monitored = tm[tm["season"] != SEASONS[0]]          # 2014/15 = rating burn-in
    for (team, season), g in monitored.groupby(["team_id", "season"], sort=False):
        g = g.sort_values("date")
        mu0 = g["rating_pre"].iloc[0]
        hi = lo = 0.0
        for r in g.itertuples(index=False):
            z = (r.adj_perf - mu0) / sigma
            hi = max(0.0, hi + z - k)
            lo = max(0.0, lo - z - k)
            alarm = "up" if hi > h else ("down" if lo > h else "")
            rows.append({"match_id": r.match_id, "team_id": team, "season": season, "date": r.date,
                         "team_match_no": r.team_match_no, "coach": r.coach, "mu0": mu0, "z": z,
                         "c_plus": hi, "c_minus": lo, "alarm": alarm})
            if hi > h:
                hi = 0.0
            if lo > h:
                lo = 0.0
    out = pd.DataFrame(rows)
    out["h"] = h
    return out


def backtest_sackings(cusum: pd.DataFrame, tm: pd.DataFrame, changes: pd.DataFrame) -> pd.DataFrame:
    """For every in-season sacking: did CUSUM flag a decline first, and how early?

    Compared with a simple form rule used by media and fans: five league
    matches in a row without a win.
    """
    tm = tm.sort_values(["team_id", "date"])
    rows = []
    sacked = changes[changes["departure"].str.contains("Sacked", case=False)
                     & ~changes["pre_season"] & changes["team_id"].notna()
                     & (changes["season"] != SEASONS[0])]
    for c in sacked.itertuples(index=False):
        g = tm[(tm["team_id"] == c.team_id) & (tm["season"] == c.season)
               & (tm["date"] <= c.vacancy_date)].sort_values("date")
        if g.empty:
            continue
        n_before = len(g)
        cs = cusum[(cusum["team_id"] == c.team_id) & (cusum["season"] == c.season)
                   & (cusum["date"] <= c.vacancy_date)].sort_values("date")
        down = cs.index[cs["alarm"] == "down"]
        cusum_first = int(cs.loc[down[0], "team_match_no"]) if len(down) else None
        winless = (g["points"] < 3).astype(int).to_numpy()
        run, form_first = 0, None
        for i, w in enumerate(winless, 1):
            run = run + 1 if w else 0
            if run >= 5:
                form_first = i
                break
        rows.append({"change_id": c.change_id, "team_id": c.team_id, "season": c.season,
                     "coach_out": c.outgoing_coach, "vacancy_date": c.vacancy_date,
                     "matches_before_sacking": n_before,
                     "cusum_first_alarm_match": cusum_first,
                     "cusum_lead_matches": (n_before - cusum_first) if cusum_first else None,
                     "form_rule_first_match": form_first,
                     "form_rule_lead_matches": (n_before - form_first) if form_first else None})
    return pd.DataFrame(rows)


def operating_characteristic(tm: pd.DataFrame, changes: pd.DataFrame, sigma: float,
                             residuals: np.ndarray, h_values=(2.0, 2.6, 3.0, 3.5, 4.0, 4.5, 5.0)) -> pd.DataFrame:
    """Trade-off between catching declines before sackings and false alarms, per h."""
    rng = np.random.default_rng(11)
    z = (residuals - residuals.mean()) / residuals.std(ddof=1)
    sims = rng.choice(z, size=(600, 2000), replace=True)
    rows = []
    for h in h_values:
        cs = run_cusum(tm, sigma, h)
        bt = backtest_sackings(cs, tm, changes)
        fa = false_alarm_rates(cs, tm, changes)
        rows.append({"h": h, "arl0_one_sided": float(np.mean([_run_length(s, CUSUM_K, h) for s in sims])),
                     "sackings": len(bt),
                     "share_sackings_flagged": bt["cusum_first_alarm_match"].notna().mean(),
                     "median_lead_matches": bt["cusum_lead_matches"].median(),
                     "share_stable_seasons_flagged": fa["share_with_cusum_down_alarm"],
                     "rule": "CUSUM"})
    bt = backtest_sackings(run_cusum(tm, sigma, h_values[0]), tm, changes)
    fa = false_alarm_rates(run_cusum(tm, sigma, h_values[0]), tm, changes)
    rows.append({"h": None, "arl0_one_sided": None, "sackings": len(bt),
                 "share_sackings_flagged": bt["form_rule_first_match"].notna().mean(),
                 "median_lead_matches": bt["form_rule_lead_matches"].median(),
                 "share_stable_seasons_flagged": fa["share_with_form_rule_alarm"],
                 "rule": "5 matches without a win"})
    return pd.DataFrame(rows)


def false_alarm_rates(cusum: pd.DataFrame, tm: pd.DataFrame, changes: pd.DataFrame) -> dict:
    """Alarms per team-season among completed team-seasons with no in-season change."""
    in_season = changes[~changes["pre_season"]][["team_id", "season"]].drop_duplicates()
    stable = (tm[tm["season"].isin(SEASONS[1:-1])][["team_id", "season"]].drop_duplicates()
              .merge(in_season, how="left", indicator=True).query("_merge == 'left_only'"))
    keys = set(zip(stable["team_id"], stable["season"]))
    cs = cusum[[k in keys for k in zip(cusum["team_id"], cusum["season"])]]
    down_seasons = cs[cs["alarm"] == "down"].groupby(["team_id", "season"]).size()
    form = 0
    for (t, s), g in tm[[k in keys for k in zip(tm["team_id"], tm["season"])]].groupby(["team_id", "season"]):
        run = 0
        for p in g.sort_values("date")["points"]:
            run = run + 1 if p < 3 else 0
            if run >= 5:
                form += 1
                break
    n = len(keys)
    return {"stable_team_seasons": n,
            "share_with_cusum_down_alarm": len(down_seasons) / n if n else np.nan,
            "share_with_form_rule_alarm": form / n if n else np.nan}
