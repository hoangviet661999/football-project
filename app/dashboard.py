"""EPL Performance Monitor - Streamlit dashboard.

    uv run streamlit run app/dashboard.py

Reads the published database (data/epl.duckdb) only; the pipeline replaces it
after every load that passes QA.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from epl.config import CUSUM_K, DB_PATH, season_label  # noqa: E402

# ---------------------------------------------------------------- palette
# Reference palette (dataviz skill, references/palette.md), light mode.
SURFACE, GRID, AXIS = "#fcfcfb", "#e1e0d9", "#c3c2b7"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"   # slots 1, 2, 3, 8
NEUTRAL = "#c3c2b7"
GOOD, CRITICAL, WARNING = "#0ca30c", "#d03b3b", "#fab219"              # status, with icon + label
DIVERGING = [[0, "#c22f2f"], [0.25, "#e98a89"], [0.5, "#f0efec"], [0.75, "#86b6ef"], [1, "#1c5cab"]]
SEQUENTIAL = [[0, "#cde2fb"], [1, "#104281"]]
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def style(fig: go.Figure, height: int = 360, legend: bool = True, title: str | None = None,
          extra_top: int = 0) -> go.Figure:
    """House style: hairline grid, recessive axes, title and legend in a top band (never over the plot)."""
    fig.update_layout(
        height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=16, r=24, t=(92 if title else 56) + extra_top, b=16),
        font=dict(family=FONT, size=13, color=INK2),
        title=dict(text=title, x=0, xanchor="left", y=1, yref="container", yanchor="top", pad=dict(t=12, l=4),
                   font=dict(size=15, color=INK)) if title else None,
        hoverlabel=dict(bgcolor="white", bordercolor=AXIS, font=dict(family=FONT, color=INK)),
        showlegend=legend, legend=dict(orientation="h", yref="container", yanchor="top", x=0, title=None,
                                       y=1 - (44 if title else 12) / height),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, showline=True, ticks="", automargin=True)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, showline=False, ticks="", automargin=True)
    return fig


# ---------------------------------------------------------------- data
@st.cache_data(ttl=600)
def load() -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    names = ["dim_team", "dim_season", "dim_referee", "dim_coaching_change", "team_match_metrics",
             "cusum_path", "cusum_backtest", "cusum_operating", "sprt_test", "sprt_path",
             "anom_referee", "anom_referee_season", "outlier_team_match", "qa_results",
             "qa_completeness", "cleaning_log", "analysis_params"]
    data = {n: con.sql(f"SELECT * FROM {n}").df() for n in names}
    con.close()
    data["params"] = json.loads(data.pop("analysis_params")["params_json"].iloc[0])
    return data


def team_name(d, tid):
    return d["dim_team"].set_index("team_id")["team_name"].get(tid, tid)


def cusum_for(g: pd.DataFrame, sigma: float, h: float, k: float = CUSUM_K) -> pd.DataFrame:
    """Recompute one team-season's CUSUM for a user-chosen h."""
    g = g.sort_values("date").copy()
    mu0 = g["rating_pre"].iloc[0]
    hi = lo = 0.0
    cp, cm, al = [], [], []
    for x in g["adj_perf"]:
        z = (x - mu0) / sigma
        hi, lo = max(0.0, hi + z - k), max(0.0, lo - z - k)
        cp.append(hi)
        cm.append(lo)
        al.append("up" if hi > h else ("down" if lo > h else ""))
        hi = 0.0 if hi > h else hi
        lo = 0.0 if lo > h else lo
    g["z"] = (g["adj_perf"] - mu0) / sigma
    g["c_plus"], g["c_minus"], g["alarm"], g["mu0"] = cp, cm, al, mu0
    return g


def header(title: str, user: str, question: str, decision: str):
    st.markdown(f"## {title}")
    st.caption(f"**For:** {user} · **Question:** {question} · **Supports:** {decision}")


def tile(col, label, value, note=""):
    col.metric(label, value, help=note or None)


# ---------------------------------------------------------------- pages
def page_team(d):
    header("Team monitor", "Sporting director, performance analyst",
           "Has our underlying performance shifted, and since which match?",
           "open a formal coach review, or hold steady")
    p = d["params"]
    sigma, h_default = p["metric"]["sigma"], p["cusum"]["h"]
    tmm = d["team_match_metrics"]
    seasons = sorted(tmm["season"].unique())[1:]           # 2014/15 is the rating burn-in
    teams = d["dim_team"].sort_values("team_name")

    c1, c2, c3 = st.columns([2, 3, 3])
    season = c1.selectbox("Season", seasons[::-1], format_func=season_label)
    avail = teams[teams["team_id"].isin(tmm.loc[tmm["season"] == season, "team_id"])]
    tid = c2.selectbox("Team", avail["team_id"], format_func=lambda t: team_name(d, t),
                       index=int(np.flatnonzero(avail["team_id"].to_numpy() == "MUN")[0])
                       if "MUN" in set(avail["team_id"]) else 0)
    h = c3.slider("Decision interval h (higher = fewer false alarms, slower detection)",
                  2.0, 5.0, float(h_default), 0.1)

    g = cusum_for(tmm[(tmm["team_id"] == tid) & (tmm["season"] == season)], sigma, h)
    g["opp"] = g["opponent_id"].map(lambda t: team_name(d, t))
    last = g.iloc[-1]
    downs, ups = g[g["alarm"] == "down"], g[g["alarm"] == "up"]
    t1, t2, t3, t4 = st.columns(4)
    status = ("▼ Decline alarm" if last["alarm"] == "down" else "▲ Improvement alarm" if last["alarm"] == "up"
              else "▼ Decline building" if last["c_minus"] > h / 2 else "● In control")
    tile(t1, "Status after last match", status)
    tile(t2, "First decline alarm", f"Match {int(downs['team_match_no'].iloc[0])}" if len(downs) else "None")
    tile(t3, "Points per match", f"{g['points'].mean():.2f}", "Actual league points per match this season")
    tile(t4, "Coach now", last["coach"])

    changes = d["dim_coaching_change"]
    ch = changes[(changes["team_id"] == tid) & (changes["season"] == season) & ~changes["pre_season"]]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.62, 0.38], vertical_spacing=0.08,
                        subplot_titles=("CUSUM evidence of a shift (decline plotted below zero)",
                                        "Match performance vs season-start level (standardised)"))
    x = g["team_match_no"]
    hover = [f"Match {m} · {'H' if hm else 'A'} vs {o}<br>{gf}-{ga} · SoT {sf}-{sa}<br>Coach: {c}"
             for m, hm, o, gf, ga, sf, sa, c in zip(x, g["is_home"], g["opp"], g["goals_for"],
                                                     g["goals_against"], g["sot_for"], g["sot_against"], g["coach"])]
    fig.add_trace(go.Scatter(x=x, y=g["c_plus"], name="Evidence of improvement (C+)", mode="lines",
                             line=dict(color=BLUE, width=2), text=hover,
                             hovertemplate="%{text}<br>C+ = %{y:.2f}<extra></extra>"), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=-g["c_minus"], name="Evidence of decline (C−)", mode="lines",
                             line=dict(color=RED, width=2), text=hover,
                             hovertemplate="%{text}<br>C− = %{customdata:.2f}<extra></extra>",
                             customdata=g["c_minus"]), 1, 1)
    for lvl, lab in ((h, "Improvement alarm"), (-h, "Decline alarm")):
        fig.add_hline(y=lvl, line=dict(color=MUTED, width=1, dash="dash"), row=1, col=1,
                      annotation_text=f"{lab} (±h = {h:.1f})", annotation_position="top left" if lvl > 0 else "bottom left",
                      annotation_font=dict(size=11, color=INK2))
    if len(downs):
        fig.add_trace(go.Scatter(x=downs["team_match_no"], y=-downs["c_minus"], mode="markers", name="▼ Decline alarm",
                                 marker=dict(color=CRITICAL, size=11, symbol="triangle-down", line=dict(color=SURFACE, width=2)),
                                 hovertemplate="Decline alarm at match %{x}<extra></extra>"), 1, 1)
    if len(ups):
        fig.add_trace(go.Scatter(x=ups["team_match_no"], y=ups["c_plus"], mode="markers", name="▲ Improvement alarm",
                                 marker=dict(color=GOOD, size=11, symbol="triangle-up", line=dict(color=SURFACE, width=2)),
                                 hovertemplate="Improvement alarm at match %{x}<extra></extra>"), 1, 1)
    fig.add_trace(go.Bar(x=x, y=g["z"], marker_color=np.where(g["z"] >= 0, BLUE, RED), name="Match z",
                         showlegend=False, hovertext=hover, hovertemplate="%{hovertext}<br>z = %{y:.2f}<extra></extra>"), 2, 1)
    for c in ch.itertuples():
        after = g[g["date"] >= c.appointment_date]
        if len(after):
            m = int(after["team_match_no"].iloc[0]) - 0.5
            for r in (1, 2):
                fig.add_vline(x=m, line=dict(color=INK2, width=1), row=r, col=1)
            fig.add_annotation(x=m, y=1, yref="y domain", text=f"{c.incoming_coach}", showarrow=False,
                               xanchor="left", font=dict(size=11, color=INK), row=1, col=1)
    fig.update_xaxes(title_text="League match of the season", row=2, col=1, dtick=2)
    fig.update_layout(bargap=0.25)
    st.plotly_chart(style(fig, 600, extra_top=16), width="stretch")
    st.caption("Performance = shots-on-target difference adjusted for venue and opponent strength. "
               f"Season-start level μ0 = {g['mu0'].iloc[0]:+.2f}; one match SD σ = {sigma:.2f}. "
               "Vertical lines mark a new coach's first match.")

    with st.expander("Table view"):
        st.dataframe(g[["team_match_no", "date", "opp", "is_home", "goals_for", "goals_against", "sot_for",
                        "sot_against", "adj_perf", "z", "c_plus", "c_minus", "alarm", "coach"]]
                     .rename(columns={"opp": "opponent"}).round(2), hide_index=True)

    # V2 - league heatmap
    st.markdown("### League alarm map")
    st.caption("**For:** analysts, journalists · **Question:** which teams are in an upward or downward alarm "
               "right now? · **Supports:** weekly briefing priorities")
    cs = d["cusum_path"][d["cusum_path"]["season"] == season].copy()
    cs["state"] = np.where(cs["c_plus"] >= cs["c_minus"], cs["c_plus"], -cs["c_minus"]) / cs["h"]
    cs.loc[cs["alarm"] == "down", "state"] = -1.0
    cs.loc[cs["alarm"] == "up", "state"] = 1.0
    piv = cs.pivot_table(index="team_id", columns="team_match_no", values="state").clip(-1, 1)
    alarms = cs.pivot_table(index="team_id", columns="team_match_no", values="alarm", aggfunc="first")
    order = piv.ffill(axis=1).iloc[:, -1].sort_values().index
    piv, alarms = piv.loc[order], alarms.loc[order]
    names = [team_name(d, t) for t in piv.index]
    txt = alarms.map(lambda a: "▼" if a == "down" else ("▲" if a == "up" else ""))
    hm = go.Figure(go.Heatmap(z=piv.values, x=piv.columns, y=names, zmin=-1, zmax=1, colorscale=DIVERGING,
                              text=txt.values, texttemplate="%{text}", textfont=dict(color=INK, size=11),
                              xgap=2, ygap=2,
                              colorbar=dict(title="", tickvals=[-1, 0, 1], len=0.6, thickness=10,
                                            ticktext=["▼ Decline alarm", "In control", "▲ Improvement alarm"]),
                              hovertemplate="%{y} · match %{x}<br>Evidence: %{z:.2f} of an alarm<extra></extra>"))
    hm.update_xaxes(title_text="League match of the season", dtick=2, showline=False)
    hm.update_yaxes(autorange="reversed", showline=False)
    st.plotly_chart(style(hm, 34 * len(names) + 90, legend=False), width="stretch")
    st.caption(f"Colour = CUSUM evidence as a share of the alarm threshold (h = {h_default:.1f}); "
               "▼/▲ = alarm raised at that match (the statistic then restarts). Sorted by the latest state.")

    with st.expander("How reliable are the alarms? (back-test on 2015/16 to 2025/26)"):
        op = d["cusum_operating"]
        bt = d["cusum_backtest"]
        cus, form = op[op["rule"] == "CUSUM"], op[op["rule"] != "CUSUM"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=cus["share_stable_seasons_flagged"], y=cus["share_sackings_flagged"],
                                 mode="lines+markers+text", name="CUSUM (label = h)", line=dict(color=BLUE, width=2),
                                 marker=dict(size=9, line=dict(color=SURFACE, width=2)), text=cus["h"].map("{:.1f}".format),
                                 textposition="top left", textfont=dict(color=INK2, size=11),
                                 hovertemplate="h = %{text}<br>False alarms: %{x:.0%} of stable seasons"
                                               "<br>Sackings flagged first: %{y:.0%}<extra></extra>"))
        fig.add_trace(go.Scatter(x=form["share_stable_seasons_flagged"], y=form["share_sackings_flagged"],
                                 mode="markers+text", name="5 matches without a win", text=["5 without a win"],
                                 textposition="bottom right", textfont=dict(color=INK2, size=11),
                                 marker=dict(color=ORANGE, size=11, symbol="diamond", line=dict(color=SURFACE, width=2)),
                                 hovertemplate="False alarms: %{x:.0%}<br>Sackings flagged first: %{y:.0%}<extra></extra>"))
        fig.update_xaxes(title_text="Share of stable team-seasons with a decline alarm (false alarms)", tickformat=".0%", range=[0, 0.75])
        fig.update_yaxes(title_text="Share of sackings preceded by an alarm", tickformat=".0%", range=[0, 0.8])
        st.plotly_chart(style(fig, 380), width="stretch")
        n = len(bt)
        st.markdown(
            f"Of **{n} in-season sackings**, a decline alarm at h = {h_default:.1f} preceded "
            f"**{bt['cusum_first_alarm_match'].notna().sum()}** (median {bt['cusum_lead_matches'].median():.0f} matches before), "
            f"while the results-based rule fired before **{bt['form_rule_first_match'].notna().sum()}**. "
            "Boards sack on results; many sacked coaches showed no significant decline in underlying performance.")
        st.dataframe(op.round(3), hide_index=True)


def page_matches(d):
    header("Match review", "Performance analyst", "Which matches were abnormal, and on which metric?",
           "pick matches for video review")
    o = d["outlier_team_match"].copy()
    o["team"] = o["team_id"].map(lambda t: team_name(d, t))
    o["opponent"] = o["opponent_id"].map(lambda t: team_name(d, t))
    c1, c2, c3 = st.columns([2, 3, 3])
    season = c1.selectbox("Season", sorted(o["season"].unique())[::-1], format_func=season_label, key="m_season")
    teams = ["All teams"] + sorted(o.loc[o["season"] == season, "team"].unique())
    team = c2.selectbox("Highlight team", teams)
    driver = c3.multiselect("Main driver", sorted(o["main_driver"].dropna().unique()), placeholder="All drivers")
    s = o[o["season"] == season]
    sel = s if team == "All teams" else s[s["team"] == team]
    flagged = sel[sel["is_outlier"]]
    if driver:
        flagged = flagged[flagged["main_driver"].isin(driver)]
    t1, t2, t3 = st.columns(3)
    tile(t1, "Team-matches checked", f"{len(sel):,}")
    tile(t2, "Flagged for review", f"{len(flagged):,}", "Any robust |z| > 3 or Mahalanobis distance above the 99% cut")
    tile(t3, "Share flagged", f"{len(flagged) / max(len(sel), 1):.1%}")

    cut = d["params"]["outliers"]["chi2_cut"]
    base = s[~s.index.isin(flagged.index)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=base["date"], y=base["mahalanobis_sq"], mode="markers", name="Normal",
                             marker=dict(color=NEUTRAL, size=6, opacity=0.6), hoverinfo="skip"))
    hov = [f"{t} {'vs' if h else 'at'} {op}<br>{gf}-{ga} · shots {sh} · fouls {f} · yellows {y}<br>Main driver: {dr} (z = {z:+.1f})"
           for t, h, op, gf, ga, sh, f, y, dr, z in zip(flagged["team"], flagged["is_home"], flagged["opponent"],
                                                       flagged["goals_for"], flagged["goals_against"], flagged["shots_for"],
                                                       flagged["fouls"], flagged["yellow"], flagged["main_driver"], flagged["driver_z"])]
    fig.add_trace(go.Scatter(x=flagged["date"], y=flagged["mahalanobis_sq"], mode="markers", name="Flagged for review",
                             marker=dict(color=BLUE, size=9, line=dict(color=SURFACE, width=2)), text=hov,
                             hovertemplate="%{x|%d %b %Y}<br>%{text}<extra></extra>"))
    fig.add_hline(y=cut, line=dict(color=MUTED, width=1, dash="dash"),
                  annotation_text="99% multivariate cut", annotation_font=dict(size=11, color=INK2))
    fig.update_yaxes(title_text="Robust Mahalanobis distance² (higher = more unusual)", type="log")
    st.plotly_chart(style(fig, 440, title="Unusual team-matches across the season"), width="stretch")
    st.caption("Grey points include matches flagged only for teams not highlighted. Log scale.")

    st.markdown("#### Matches to review")
    show = flagged.sort_values("mahalanobis_sq", ascending=False)[
        ["date", "team", "opponent", "is_home", "goals_for", "goals_against", "shots_for", "sot_for", "sot_against",
         "fouls", "yellow", "main_driver", "driver_z", "mahalanobis_sq"]].round(2)
    show["date"] = show["date"].dt.date
    st.dataframe(show, hide_index=True, width="stretch")


def page_referees(d):
    header("Referee consistency", "Referee committee, assessors",
           "Which referees card or penalise fouls significantly more or less than average?",
           "select referees for calibration or closer assessment")
    a, s, p = d["anom_referee"], d["anom_referee_season"], d["params"]["anom"]
    c1, c2 = st.columns([2, 6])
    metric = c1.radio("Measure", ["yellow", "fouls"], format_func=lambda m: p[m]["label"], horizontal=False)
    g = a[a["metric"] == metric].sort_values("ratio").reset_index(drop=True)
    above, below = g[g["signal"] == "Above"], g[g["signal"] == "Below"]
    t1, t2, t3 = c2.columns(3)
    tile(t1, "Referees tested", f"{len(g)}", "At least 30 EPL matches, 2014/15 to now")
    tile(t2, "▲ Significantly above", f"{len(above)}")
    tile(t3, "▼ Significantly below", f"{len(below)}")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=g["referee"], y=(g["upper"] - 1) * 100, mode="lines", line=dict(color=MUTED, width=1, shape="hvh"),
                             name="Decision limits (α = 0.05, Bonferroni)", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=g["referee"], y=(g["lower"] - 1) * 100, mode="lines", line=dict(color=MUTED, width=1, shape="hvh"),
                             showlegend=False, hoverinfo="skip", fill="tonexty", fillcolor="rgba(195,194,183,0.18)"))
    colors = np.where(g["signal"] == "Above", RED, np.where(g["signal"] == "Below", BLUE, NEUTRAL))
    fig.add_trace(go.Scatter(x=g["referee"], y=(g["ratio"] - 1) * 100, mode="markers", name="Referee vs league",
                             marker=dict(color=colors, size=10, line=dict(color=SURFACE, width=2)),
                             customdata=np.stack([g["n"], g["rate"], g["league_rate"], g["signal"]], axis=1),
                             hovertemplate="%{x} · %{customdata[0]} matches<br>%{customdata[1]:.2f} per match vs "
                                           "league %{customdata[2]:.2f}<br>%{y:+.1f}% · %{customdata[3]}<extra></extra>"))
    for r in pd.concat([above, below]).itertuples():
        fig.add_annotation(x=r.referee, y=(r.ratio - 1) * 100, text=f"{(r.ratio - 1) * 100:+.0f}%", showarrow=False,
                           yshift=14 if r.ratio > 1 else -14, font=dict(size=11, color=INK))
    fig.add_hline(y=0, line=dict(color=AXIS, width=1))
    fig.update_yaxes(title_text="Difference from league average (%)", ticksuffix="%")
    fig.update_xaxes(tickangle=-60, showgrid=False)
    st.plotly_chart(style(fig, 520, title=f"ANOM: {p[metric]['label'].lower()} by referee, season-adjusted"), width="stretch")
    st.caption(f"Expected value for each match = that season's league mean. Overdispersion φ = {p[metric]['phi']:.2f}. "
               "Limits widen for referees with fewer matches. Red = above, blue = below, grey = within limits. "
               "A flag means 'worth reviewing', not proof of bias: fixture mix (derbies, rivalries) is not adjusted.")

    st.markdown("### Is the deviation stable across seasons?")
    st.caption("**For:** referee assessor · **Supports:** confirm or dismiss a flag before acting")
    default = list(pd.concat([above, below])["referee"])[:4] or list(g["referee"].tail(2))
    refs = st.multiselect("Referees", list(g["referee"]), default=default, max_selections=6)
    if refs:
        ss = s[(s["metric"] == metric) & s["referee"].isin(refs)]
        cols = min(3, len(refs))
        rows = int(np.ceil(len(refs) / cols))
        fig = make_subplots(rows=rows, cols=cols, shared_yaxes=True, subplot_titles=refs,
                            vertical_spacing=0.18, horizontal_spacing=0.04)
        for i, ref in enumerate(refs):
            r, c = i // cols + 1, i % cols + 1
            x = ss[ss["referee"] == ref].sort_values("season")
            lab = x["season"].map(season_label)
            fig.add_trace(go.Scatter(x=lab, y=(x["upper"] - 1) * 100, mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False), r, c)
            fig.add_trace(go.Scatter(x=lab, y=(x["lower"] - 1) * 100, mode="lines", line=dict(width=0), fill="tonexty",
                                     fillcolor="rgba(195,194,183,0.25)", hoverinfo="skip", showlegend=(i == 0), name="95% band for that season"), r, c)
            fig.add_trace(go.Scatter(x=lab, y=(x["ratio"] - 1) * 100, mode="lines+markers", line=dict(color=BLUE, width=2),
                                     marker=dict(size=8, line=dict(color=SURFACE, width=2)), showlegend=(i == 0), name="Season value",
                                     customdata=x["n"], hovertemplate="%{x}: %{y:+.0f}% (%{customdata} matches)<extra></extra>"), r, c)
            fig.add_hline(y=0, line=dict(color=AXIS, width=1), row=r, col=c)
        fig.update_yaxes(ticksuffix="%")
        fig.update_xaxes(tickangle=-45, showgrid=False)
        st.plotly_chart(style(fig, 300 * rows + 40, extra_top=16), width="stretch")
    with st.expander("Table view"):
        st.dataframe(g[["referee", "n", "rate", "league_rate", "ratio", "lower", "upper", "signal"]].round(3), hide_index=True)


def page_coaches(d):
    header("Coaching change", "Board, sporting director",
           "Has the new coach improved the team yet, or do we need more matches?",
           "set the review date; stop early when the evidence is clear")
    t, paths, sp = d["sprt_test"], d["sprt_path"], d["params"]["sprt"]
    tested = t[t["status"] == "Tested"].sort_values("appointment_date", ascending=False).copy()
    tested["label"] = [f"{season_label(s)} · {team_name(d, tm)} · {o} → {i}"
                       for s, tm, o, i in zip(tested["season"], tested["team_id"], tested["coach_out"], tested["coach_in"])]
    # Default to the most recent change that already has matches under the new coach.
    has_data = np.flatnonzero(tested["matches_observed"].fillna(0).to_numpy() > 0)
    pick = st.selectbox("Coaching change", tested["change_id"], index=int(has_data[0]) if len(has_data) else 0,
                        format_func=dict(zip(tested["change_id"], tested["label"])).get)
    row = tested.set_index("change_id").loc[pick]
    path = paths[paths["change_id"] == pick]
    t1, t2, t3, t4 = st.columns(4)
    icon = {"Improved": "▲ Improved", "No improvement": "■ No improvement"}.get(row["decision"], "● " + row["decision"])
    tile(t1, "SPRT decision", icon)
    tile(t2, "Matches to decision", "-" if pd.isna(row["matches_to_decision"]) else f"{int(row['matches_to_decision'])}")
    tile(t3, "Points per match before", f"{row['baseline_points_pg']:.2f}", f"Previous coach's last {int(row['baseline_matches'])} matches")
    tile(t4, "Points per match after", "-" if pd.isna(row["after_points_pg"]) else f"{row['after_points_pg']:.2f}",
         f"{int(row['matches_observed'])} matches under the new coach")

    fig = go.Figure()
    if len(path):
        opp = path["opponent_id"].map(lambda x: team_name(d, x))
        fig.add_trace(go.Scatter(x=path["match_no"], y=path["llr"], mode="lines+markers", name="Evidence (log-likelihood ratio)",
                                 line=dict(color=BLUE, width=2), marker=dict(size=8, line=dict(color=SURFACE, width=2)),
                                 text=opp, customdata=path["adj_perf"],
                                 hovertemplate="Match %{x} vs %{text}<br>Performance %{customdata:+.2f}<br>LLR %{y:.2f}<extra></extra>"))
        if not pd.isna(row["matches_to_decision"]):
            m = int(row["matches_to_decision"])
            y = path.loc[path["match_no"] == m, "llr"].iloc[0]
            fig.add_annotation(x=m, y=y, text=f"Decision at match {m}", showarrow=True, arrowcolor=MUTED,
                               ax=40, ay=-30 if y > 0 else 30, font=dict(size=12, color=INK))
    fig.add_hline(y=sp["upper"], line=dict(color=GOOD, width=1.5),
                  annotation_text="▲ Accept 'improved'", annotation_font=dict(size=11, color=INK))
    fig.add_hline(y=sp["lower"], line=dict(color=MUTED, width=1.5),
                  annotation_text="■ Accept 'no improvement'", annotation_position="bottom left", annotation_font=dict(size=11, color=INK))
    fig.add_hline(y=0, line=dict(color=AXIS, width=1))
    fig.update_xaxes(title_text="Matches under the new coach", dtick=2)
    fig.update_yaxes(title_text="Cumulative evidence")
    st.plotly_chart(style(fig, 420, title="Sequential test: evidence for improvement, match by match"), width="stretch")
    st.caption(f"H0: no change from the previous coach's level ({row['baseline_mean']:+.2f}); H1: improvement of "
               f"{sp['delta']:.2f} shots-on-target difference per match (0.5σ). α = {sp['alpha']}, β = {sp['beta']}. "
               "The test stops as soon as a boundary is crossed; caretaker matches are excluded.")

    st.markdown("### How long does it take to know?")
    st.caption("**For:** board, analyst · **Supports:** set realistic expectations before hiring")
    dec = tested[tested["decision"].isin(["Improved", "No improvement"])]
    k1, k2, k3, k4 = st.columns(4)
    tile(k1, "In-season changes tested", f"{len(tested)}")
    tile(k2, "▲ Improved", f"{(tested['decision'] == 'Improved').sum()}")
    tile(k3, "■ No improvement", f"{(tested['decision'] == 'No improvement').sum()}")
    tile(k4, "Median matches to a decision", f"{dec['matches_to_decision'].median():.0f}")
    fig = go.Figure()
    for name, color in (("Improved", BLUE), ("No improvement", ORANGE)):
        x = dec[dec["decision"] == name]["matches_to_decision"]
        fig.add_trace(go.Histogram(x=x, name=f"{name} (median {x.median():.0f})", marker_color=color,
                                   xbins=dict(start=0.5, end=38.5, size=2), marker_line=dict(color=SURFACE, width=2),
                                   hovertemplate="%{x} matches: %{y} changes<extra></extra>"))
    fig.update_layout(barmode="group", bargap=0.15)
    fig.update_xaxes(title_text="Matches needed to reach a decision", range=[0, 38])
    fig.update_yaxes(title_text="Coaching changes")
    st.plotly_chart(style(fig, 340), width="stretch")
    st.caption(f"{(tested['decision'].str.startswith('Undecided')).sum()} changes stayed undecided "
               f"(up to 38 matches or the next change); {len(t[t['status'] != 'Tested'])} pre-season or short-baseline "
               "changes were excluded. Teams often sack at a low point, so part of any rebound is regression to the mean.")
    with st.expander("Table view"):
        st.dataframe(tested[["season", "team_id", "coach_out", "coach_in", "appointment_date", "baseline_matches",
                             "baseline_points_pg", "after_points_pg", "decision", "matches_to_decision"]].round(2), hide_index=True)


def page_quality(d):
    header("Data quality (admin)", "Project team", "Is this week's data complete and valid enough to publish?",
           "approve or block the weekly dashboard refresh")
    q = d["qa_results"]
    counts = q["status"].value_counts()
    t1, t2, t3, t4 = st.columns(4)
    tile(t1, "Last check (UTC)", q["checked_at"].iloc[0][:16].replace("T", " "))
    tile(t2, "✓ PASS", f"{counts.get('PASS', 0)}")
    tile(t3, "! WARN", f"{counts.get('WARN', 0)}")
    tile(t4, "✕ FAIL", f"{counts.get('FAIL', 0)}", "Any FAIL blocks publication")
    icon = {"PASS": "✓ PASS", "WARN": "! WARN", "FAIL": "✕ FAIL"}
    st.dataframe(q.assign(status=q["status"].map(icon))[["status", "check", "value", "expectation"]],
                 hide_index=True, width="stretch")

    comp = d["qa_completeness"]
    piv = comp.pivot(index="column", columns="season", values="completeness")
    fig = go.Figure(go.Heatmap(z=piv.values, x=[season_label(s) for s in piv.columns], y=piv.index, zmin=0, zmax=1,
                               colorscale=SEQUENTIAL, xgap=2, ygap=2, text=(piv * 100).round(0).astype(int).astype(str) + "%",
                               texttemplate="%{text}", textfont=dict(size=10),
                               colorbar=dict(title="", tickformat=".0%", len=0.6, thickness=10),
                               hovertemplate="%{y} · %{x}<br>%{z:.0%} of matches have a value<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showline=False)
    fig.update_xaxes(showline=False)
    st.plotly_chart(style(fig, 560, legend=False, title="Completeness by season and column"), width="stretch")
    st.caption("xG columns exist only in 2026/27; the analysis therefore uses shots on target.")
    st.markdown("#### Cleaning log")
    st.dataframe(d["cleaning_log"], hide_index=True, width="stretch")


# ---------------------------------------------------------------- main
def main():
    st.set_page_config(page_title="EPL Performance Monitor", page_icon="⚽", layout="wide")
    if not DB_PATH.exists():
        st.error("No published database. Run `uv run python -m epl.pipeline` first.")
        return
    d = load()
    pages = {"Team monitor": page_team, "Match review": page_matches, "Referee consistency": page_referees,
             "Coaching change": page_coaches, "Data quality (admin)": page_quality}
    with st.sidebar:
        st.markdown("### EPL Performance Monitor")
        st.caption("Real change or noise? Outlier detection, ANOM, CUSUM and SPRT on Premier League data, 2014/15 to now.")
        choice = st.radio("Page", list(pages), label_visibility="collapsed")
        last = d["team_match_metrics"]["date"].max()
        st.caption(f"Data to {last:%d %b %Y} · source: football-data.co.uk, Wikipedia")
    pages[choice](d)


main()
