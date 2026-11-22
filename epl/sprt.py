"""Question 4 - SPRT: has the new coach genuinely improved the team?

For each in-season permanent appointment:
  baseline mu_b = mean adjusted performance over the previous permanent
                  coach's last (up to) 19 matches
  H0: mu = mu_b            (no improvement)
  H1: mu = mu_b + delta    (improvement of delta = 0.5 sigma per match)
Observations are the new coach's matches. With normal observations the
log-likelihood ratio grows by (delta / sigma^2) * (x - mu_b - delta / 2).
Wald's boundaries: accept H1 above ln((1 - beta) / alpha), accept H0 below
ln(beta / (1 - alpha)). Matches left caretakers are excluded.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from epl.config import (SPRT_ALPHA, SPRT_BASELINE_MATCHES, SPRT_BETA, SPRT_DELTA_SD,
                        SPRT_MAX_MATCHES, SPRT_MIN_BASELINE)

UPPER = float(np.log((1 - SPRT_BETA) / SPRT_ALPHA))
LOWER = float(np.log(SPRT_BETA / (1 - SPRT_ALPHA)))


def run_sprt(tm: pd.DataFrame, changes: pd.DataFrame, sigma: float):
    delta = SPRT_DELTA_SD * sigma
    tests, paths = [], []
    ch = changes.dropna(subset=["team_id"]).sort_values(["team_id", "appointment_date"])
    for team, ev in ch.groupby("team_id"):
        ev = ev.reset_index(drop=True)
        team_tm = tm[tm["team_id"] == team].sort_values("date")
        for i, c in ev.iterrows():
            base = {"change_id": c.change_id, "team_id": team, "season": c.season,
                    "coach_in": c.incoming_coach, "coach_out": c.outgoing_coach,
                    "appointment_date": c.appointment_date}
            if c.incoming_interim:
                continue
            season_tm = team_tm[team_tm["season"] == c.season]
            if c.pre_season or season_tm.empty or c.appointment_date <= season_tm["date"].min():
                tests.append({**base, "status": "Excluded: pre-season appointment"})
                continue
            # Walk back over interim spells to the last permanent coach's vacancy.
            j, end = i, c.vacancy_date
            while j > 0 and ev.loc[j - 1, "incoming_interim"] and ev.loc[j - 1, "incoming_coach"] == ev.loc[j, "outgoing_coach"]:
                j -= 1
                end = ev.loc[j, "vacancy_date"]
            chain = season_tm["chain"].iloc[0]
            before = team_tm[(team_tm["date"] <= end) & (team_tm["chain"] == chain)].tail(SPRT_BASELINE_MATCHES)
            after = team_tm[team_tm["date"] >= c.appointment_date]
            nxt = ev[ev["appointment_date"] > c.appointment_date]
            if len(nxt):
                after = after[after["date"] <= nxt["vacancy_date"].iloc[0]]
            after = after[after["chain"] == chain].head(SPRT_MAX_MATCHES)
            if len(before) < SPRT_MIN_BASELINE:
                tests.append({**base, "status": "Excluded: baseline under 5 matches"})
                continue
            mu_b = float(before["adj_perf"].mean())
            llr, decision, n_dec = 0.0, None, None
            for n, r in enumerate(after.itertuples(index=False), 1):
                llr += (delta / sigma ** 2) * (r.adj_perf - mu_b - delta / 2)
                paths.append({"change_id": c.change_id, "match_no": n, "date": r.date,
                              "opponent_id": r.opponent_id, "adj_perf": r.adj_perf, "llr": llr})
                if decision is None and llr >= UPPER:
                    decision, n_dec = "Improved", n
                elif decision is None and llr <= LOWER:
                    decision, n_dec = "No improvement", n
            if decision is None:
                decision = "Undecided (ongoing)" if len(after) < SPRT_MAX_MATCHES and nxt.empty else "Undecided"
            tests.append({**base, "status": "Tested", "baseline_matches": len(before),
                          "baseline_mean": mu_b, "baseline_points_pg": float(before["points"].mean()),
                          "matches_observed": len(after),
                          "after_mean": float(after["adj_perf"].mean()) if len(after) else np.nan,
                          "after_points_pg": float(after["points"].mean()) if len(after) else np.nan,
                          "decision": decision, "matches_to_decision": n_dec})
    params = {"delta": delta, "upper": UPPER, "lower": LOWER, "alpha": SPRT_ALPHA, "beta": SPRT_BETA}
    return pd.DataFrame(tests), pd.DataFrame(paths), params
