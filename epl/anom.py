"""Question 2 - ANOM: which referees card or penalise fouls more or less than average?

Analysis of means for Poisson rates, stratified by season. For referee i,
O_i = observed total (yellow cards or fouls, both teams) and E_i = sum over
his matches of that season's league mean per match. The ratio O_i / E_i is
compared with 1; overdispersion phi is estimated from the Pearson statistic.
Decision limits (Bonferroni over k referees, alpha = 0.05):
    1 +/- z_{1 - alpha / (2k)} * sqrt(phi * (1 / E_i - 1 / E_total))
Only referees with at least 30 EPL matches are tested.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from epl.config import ANOM_ALPHA, ANOM_MIN_MATCHES

METRICS = {"yellow": ("home_yellow", "away_yellow", "Yellow cards per match"),
           "fouls": ("home_fouls", "away_fouls", "Fouls per match")}


def run_anom(matches: pd.DataFrame, referees: pd.DataFrame):
    overall, by_season, params = [], [], {}
    for metric, (hcol, acol, label) in METRICS.items():
        m = matches[["season", "referee_id", hcol, acol]].copy()
        m["y"] = (m[hcol] + m[acol]).astype(float)
        m["mu"] = m.groupby("season")["y"].transform("mean")
        phi = float(((m["y"] - m["mu"]) ** 2 / m["mu"]).sum() / (len(m) - m["season"].nunique()))
        elig = referees.loc[referees["n_matches"] >= ANOM_MIN_MATCHES, "referee_id"]
        sub = m[m["referee_id"].isin(elig)]
        g = sub.groupby("referee_id").agg(n=("y", "size"), observed=("y", "sum"), expected=("mu", "sum"))
        k = len(g)
        z = stats.norm.ppf(1 - ANOM_ALPHA / (2 * k))
        e_tot = g["expected"].sum()
        g["ratio"] = g["observed"] / g["expected"]
        half = z * np.sqrt(phi * (1 / g["expected"] - 1 / e_tot))
        g["lower"], g["upper"] = 1 - half, 1 + half
        g["signal"] = np.where(g["ratio"] > g["upper"], "Above", np.where(g["ratio"] < g["lower"], "Below", "Within"))
        g["rate"] = g["observed"] / g["n"]
        g["league_rate"] = g["expected"] / g["n"]
        g["metric"] = metric
        overall.append(g.reset_index())
        params[metric] = {"phi": phi, "k": k, "z": float(z), "label": label}

        # Per referee and season (V5): individual 95% limits, no Bonferroni.
        s = sub.groupby(["referee_id", "season"]).agg(n=("y", "size"), observed=("y", "sum"),
                                                       expected=("mu", "sum")).reset_index()
        s["ratio"] = s["observed"] / s["expected"]
        hs = stats.norm.ppf(0.975) * np.sqrt(phi / s["expected"])
        s["lower"], s["upper"] = 1 - hs, 1 + hs
        s["metric"] = metric
        by_season.append(s)
    out = pd.concat(overall, ignore_index=True).merge(referees[["referee_id", "referee"]], on="referee_id")
    out_s = pd.concat(by_season, ignore_index=True).merge(referees[["referee_id", "referee"]], on="referee_id")
    return out, out_s, params
