"""Runs the four methods on a database and writes their result tables."""
from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd

from epl import anom, cusum, outliers, sprt
from epl.config import CUSUM_K, SEASONS
from epl.metrics import add_adjusted_performance


def _write(con, name, df):
    con.register("tmp_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")


def run(db_path) -> dict:
    con = duckdb.connect(str(db_path))
    tm = con.sql("SELECT * FROM fact_team_match").df()
    matches = con.sql("SELECT * FROM fact_match").df()
    refs = con.sql("SELECT * FROM dim_referee").df()
    changes = con.sql("SELECT * FROM dim_coaching_change").df()

    tm, mparams = add_adjusted_performance(tm)
    sigma = mparams["sigma"]
    _write(con, "team_match_metrics", tm)

    # CUSUM: calibrate h on in-control residuals of completed seasons.
    done = tm[(tm["season"] != SEASONS[-1])]
    resid = (done["adj_perf"] - done.groupby(["team_id", "season"])["adj_perf"].transform("mean")).to_numpy()
    h, arl = cusum.calibrate_h(resid)
    cs = cusum.run_cusum(tm, sigma, h)
    bt = cusum.backtest_sackings(cs, tm, changes)
    fa = cusum.false_alarm_rates(cs, tm, changes)
    _write(con, "cusum_path", cs)
    _write(con, "cusum_backtest", bt)
    _write(con, "cusum_operating", cusum.operating_characteristic(tm, changes, sigma, resid))

    tests, paths, sparams = sprt.run_sprt(tm, changes, sigma)
    _write(con, "sprt_test", tests)
    _write(con, "sprt_path", paths)

    a, a_s, aparams = anom.run_anom(matches, refs)
    _write(con, "anom_referee", a)
    _write(con, "anom_referee_season", a_s)

    out, oparams = outliers.run_outliers(tm)
    _write(con, "outlier_team_match", out)

    # xG cross-check for the season where xG exists.
    xg = tm.dropna(subset=["xg_for"])
    xg_corr = float(np.corrcoef(xg["sot_diff"], xg["xg_for"] - xg["xg_against"])[0, 1]) if len(xg) > 2 else None

    params = {"metric": mparams, "cusum": {"k": CUSUM_K, "h": h, "arl0_one_sided_sim": arl, **fa},
              "sprt": sparams, "anom": aparams, "outliers": oparams,
              "xg_crosscheck": {"season": SEASONS[-1], "n_team_matches": len(xg),
                                "corr_sot_diff_xg_diff": xg_corr}}
    _write(con, "analysis_params", pd.DataFrame([{"params_json": json.dumps(params, default=str)}]))
    con.close()
    return params
