"""Performance measure shared by CUSUM, SPRT and outlier detection.

Raw shots-on-target difference (sot_diff) depends on who you play and where.
We remove both effects without looking ahead in time:

  venue-adjusted   v_t   = sot_diff_t - HA_s * (+1 home / -1 away)
  team rating      r_t   = shrunk mean of the team's last 38 v values in its
                           current unbroken EPL spell, computed BEFORE match t
  adjusted perf.   adj_t = v_t + r_opponent,t

HA_s is the league-wide home advantage in shots-on-target difference for the
season (it fell sharply in the no-crowd seasons). A team with no recent EPL
history (promoted, or the 2014/15 burn-in season) starts from a prior and is
updated as matches arrive.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from epl.config import RATING_WINDOW, SEASONS

PRIOR_WEIGHT = 10.0  # pseudo-matches of shrinkage toward the prior


def _chain_ids(tm: pd.DataFrame) -> pd.Series:
    """Number each unbroken run of EPL seasons per team (0, 1, ...)."""
    out = {}
    for team, ss in tm.groupby("team_id")["season"].apply(lambda s: sorted(set(s))).items():
        k = 0
        for i, s in enumerate(ss):
            if i and SEASONS.index(s) != SEASONS.index(ss[i - 1]) + 1:
                k += 1
            out[(team, s)] = k
    return pd.Series([out[(t, s)] for t, s in zip(tm["team_id"], tm["season"])], index=tm.index)


def add_adjusted_performance(tm: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    tm = tm.sort_values(["date", "match_id", "is_home"], ascending=[True, True, False]).reset_index(drop=True)
    home_rows = tm[tm["is_home"]]
    ha = home_rows.groupby("season")["sot_diff"].mean()          # home advantage per season
    tm["home_adv"] = tm["season"].map(ha)
    tm["venue_adj"] = tm["sot_diff"] - tm["home_adv"] * np.where(tm["is_home"], 1, -1)
    tm["chain"] = _chain_ids(tm)

    # Prior for teams starting a spell after promotion: average first-season level of
    # promoted teams (estimated from the data; teams in 2014/15 start at the league mean 0).
    first_season = tm.groupby(["team_id", "chain"])["season"].transform("min")
    promoted = (first_season != SEASONS[0]) & (tm["season"] == first_season)
    promoted_prior = float(tm.loc[promoted, "venue_adj"].mean())

    rating = np.empty(len(tm))
    n_prev = np.empty(len(tm), dtype=int)
    history: dict[tuple, list] = {}
    for i, row in enumerate(tm[["team_id", "chain", "venue_adj"]].itertuples(index=False)):
        key = (row.team_id, row.chain)
        h = history.setdefault(key, [])
        prior = 0.0 if (row.chain == 0 and first_season.iat[i] == SEASONS[0]) else promoted_prior
        window = h[-RATING_WINDOW:]
        rating[i] = (sum(window) + PRIOR_WEIGHT * prior) / (len(window) + PRIOR_WEIGHT)
        n_prev[i] = len(h)
        if not np.isnan(row.venue_adj):
            h.append(row.venue_adj)
    tm["rating_pre"] = rating
    tm["matches_in_spell_pre"] = n_prev

    opp = tm[["match_id", "team_id", "rating_pre"]].rename(
        columns={"team_id": "opponent_id", "rating_pre": "opp_rating_pre"})
    tm = tm.merge(opp, on=["match_id", "opponent_id"], how="left")
    tm["adj_perf"] = tm["venue_adj"] + tm["opp_rating_pre"]
    tm["perf_vs_level"] = tm["adj_perf"] - tm["rating_pre"]   # above / below own expected level

    # Pooled within-team-season SD: the per-match noise used to standardise.
    done = tm[tm["season"] != SEASONS[-1]]
    resid = done["adj_perf"] - done.groupby(["team_id", "season"])["adj_perf"].transform("mean")
    sigma = float(resid.std(ddof=1))
    params = {"promoted_prior": promoted_prior, "sigma": sigma,
              "home_adv": {k: float(v) for k, v in ha.items()}}
    return tm.sort_values(["team_id", "date"]).reset_index(drop=True), params
