# Data dictionary and lineage

Database: `data/epl.duckdb` (published) and `data/epl_staging.duckdb` (built on every run, published only if QA passes).

## Lineage

| Stage | Module | Input | Output |
| --- | --- | --- | --- |
| 1 Collection | `epl/collect.py` | football-data.co.uk `mmz4281/<season>/E0.csv`, Wikipedia `<yyyy>–<yy>_Premier_League` | `data/raw/football-data/E0_<season>.csv`, `data/raw/wikipedia/<yyyy>-<yy>.html`, `data/raw/manifest.csv` (URL, time, bytes, SHA-256) |
| 2 Cleaning | `epl/clean.py` | raw files | in-memory `matches`, `coaching_changes`, `cleaning_log` |
| 3–4 Integration, storage | `epl/store.py` | cleaned tables | dimension and fact tables below |
| 5 QA | `epl/qa.py` | staging database | `qa_results`, `qa_completeness`, `reports/data_quality.md` |
| Analysis | `epl/metrics.py`, `outliers.py`, `anom.py`, `cusum.py`, `sprt.py` | facts | result tables below |

Season codes follow football-data: `1415` = 2014/15.

## Dimensions

**dim_season**: season, season_label, completed, no_crowd_matches (2019/20, 2020/21).

**dim_team**: team_id (3 letters, e.g. `NFO`), fd_name (football-data short name, e.g. `Nott'm Forest`), team_name (Wikipedia name, e.g. `Nottingham Forest`).

**dim_referee**: referee_id, referee (as recorded, after trimming and capitalising), n_matches, first_season, last_season, suspected_typo_of (a regular referee with the same surname when this name appears in at most 2 matches; flagged, not changed).

**dim_coaching_change**: one row per Wikipedia table row.

| Column | Meaning |
| --- | --- |
| change_id | `C001`… |
| season, team_wiki, team_id | season page and team |
| outgoing_coach, incoming_coach | names without "(interim)" / "(caretaker)" and footnotes |
| departure | manner of departure (Sacked, Resigned, …) |
| vacancy_date, appointment_date | parsed dates |
| table_position | position at the time, or "Pre-season" |
| incoming_interim, outgoing_interim, pre_season | flags |

## Facts

**fact_match**: one row per match (4,660).

| Column | Meaning |
| --- | --- |
| match_id | `<season>_<yyyymmdd>_<Home>_<Away>` |
| date, kickoff, home_team_id, away_team_id, referee_id | |
| home_goals, away_goals, result, home_goals_ht, away_goals_ht | full-time and half-time |
| home_/away_ shots, sot, fouls, corners, yellow, red | match statistics (yellow excludes the first yellow of a two-yellow red) |
| home_xg, away_xg | 2026/27 only |
| psc_*, avgc_* | Pinnacle and market-average closing odds as published |
| close_home/draw/away, odds_source | odds used: Pinnacle up to 2018/19, market average from 2019/20 |
| overround, p_home, p_draw, p_away | implied probabilities with the margin removed |
| flag_sot_gt_shots, flag_result_mismatch, flag_negative, flag_duplicate | validity flags |

**fact_team_match**: two rows per match (9,320), one per team: team_id, opponent_id, is_home, goals_for/against, shots_for/against, sot_for/against, fouls, yellow, red, corners_for, xg_for/against, p_win, p_draw, p_loss, points, xpts (= 3·p_win + p_draw), sot_diff, goal_diff, team_match_no (match number within the team's season), coach ("Caretaker" between a vacancy and an appointment; "Not recorded" when the coach was appointed outside the EPL).

## Analysis tables

| Table | Grain | Key columns |
| --- | --- | --- |
| team_match_metrics | team-match | home_adv, venue_adj, rating_pre, opp_rating_pre, adj_perf (venue- and opponent-adjusted SoT difference), perf_vs_level |
| cusum_path | team-match (2015/16+) | mu0, z, c_plus, c_minus, alarm (up/down), h |
| cusum_backtest | in-season sacking | cusum_first_alarm_match, cusum_lead_matches, form_rule_first_match, form_rule_lead_matches |
| cusum_operating | value of h, plus the form rule | arl0_one_sided, share_sackings_flagged, median_lead_matches, share_stable_seasons_flagged |
| sprt_test | coaching change | status, baseline_matches, baseline_mean, after_mean, points per match before and after, decision, matches_to_decision |
| sprt_path | match under a new coach | match_no, adj_perf, llr |
| anom_referee | referee × metric | n, observed, expected, ratio, lower, upper, signal, rate, league_rate |
| anom_referee_season | referee × season × metric | ratio, lower, upper (95%) |
| outlier_team_match | team-match | z_* per metric, mahalanobis_sq, flag_univariate, flag_multivariate, is_outlier, main_driver, driver_z |
| analysis_params | one row | JSON with σ, home advantage, h, SPRT boundaries, ANOM φ, cut-offs, xG cross-check |
| qa_results, qa_completeness, cleaning_log | check / season × column / rule | status, value, expectation |
