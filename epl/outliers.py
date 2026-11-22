"""Question 1 - Outlier detection: which team-matches deserve video review?

Univariate: robust z-scores (season median, pooled MAD) for
  perf_vs_level  adjusted performance minus the team's own expected level
  shots_for, fouls, yellow
  result_surprise points minus expected points from closing odds
Multivariate: robust Mahalanobis distance (Minimum Covariance Determinant)
over the five metrics; flagged above the chi-square 99% quantile.
A team-match is flagged when any |z| > 3 or the distance is flagged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.covariance import MinCovDet

from epl.config import OUTLIER_CHI2_Q, OUTLIER_Z

METRICS = {"perf_vs_level": "Performance vs own level", "shots_for": "Shots",
           "fouls": "Fouls", "yellow": "Yellow cards", "result_surprise": "Result vs odds"}


def run_outliers(tm: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    d = tm.copy()
    d["result_surprise"] = d["points"] - d["xpts"]
    zcols = []
    for col in METRICS:
        x = d[col].astype(float)
        # Centre per season (league trends), but use ONE pooled scale: the MAD of a count
        # is an integer and jumps between seasons (e.g. 2 vs 3), which would make the
        # z > 3 cut-off season-dependent.
        med = x.groupby(d["season"]).transform("median")
        mad = float((x - med).abs().median()) * 1.4826
        d[f"z_{col}"] = (x - med) / (mad if mad > 0 else np.nan)
        zcols.append(f"z_{col}")
    X = d[zcols].fillna(0).to_numpy()
    mcd = MinCovDet(random_state=0).fit(X)
    d["mahalanobis_sq"] = mcd.mahalanobis(X)
    cut = float(stats.chi2.ppf(OUTLIER_CHI2_Q, df=len(zcols)))
    d["flag_univariate"] = (d[zcols].abs() > OUTLIER_Z).any(axis=1)
    d["flag_multivariate"] = d["mahalanobis_sq"] > cut
    d["is_outlier"] = d["flag_univariate"] | d["flag_multivariate"]
    absz = d[zcols].abs()
    d["main_driver"] = absz.idxmax(axis=1).str[2:].map(METRICS)
    d["driver_z"] = [d.at[i, c] for i, c in zip(d.index, absz.idxmax(axis=1))]
    keep = ["match_id", "season", "date", "team_id", "opponent_id", "is_home", "coach",
            "goals_for", "goals_against", "shots_for", "sot_for", "sot_against", "fouls", "yellow",
            "points", "xpts", "perf_vs_level", "result_surprise", *zcols,
            "mahalanobis_sq", "flag_univariate", "flag_multivariate", "is_outlier", "main_driver", "driver_z"]
    return d[keep], {"chi2_cut": cut, "z_cut": OUTLIER_Z}
