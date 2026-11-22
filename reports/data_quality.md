# Data quality report

Checked at 2026-11-22T08:07:34+00:00 UTC. Result: 18 PASS, 3 WARN, 0 FAIL. Published to the dashboard.

## Checks

| Status | Check | Value | Expectation |
| --- | --- | --- | --- |
| PASS | 380 matches in every completed season | 12/12 seasons | 12/12 seasons |
| PASS | all 13 seasons loaded | 13 seasons | 13 seasons |
| PASS | 38 matches per team in completed seasons | 240/240 team-seasons | all team-seasons = 38 |
| PASS | 20 teams in every season | 13/13 seasons | 20 teams each season |
| PASS | current season: teams within 2 matches of each other | 10 to 10 matches | spread <= 2 matches |
| PASS | each match once as home and once as away | 0 matches violate | 0 matches violate |
| PASS | result matches the goals | 0.0 matches | 0 |
| PASS | no negative counts | 0.0 matches | 0 |
| PASS | no duplicate fixtures | 0.0 matches | 0 |
| WARN | shots on target <= shots | 1 matches: NEW-WHU 2021-08-15 (H 3/17, A 9/8) | 0 (WARN: kept, source value) |
| PASS | closing odds present for every match | 0 missing | 0 missing |
| PASS | implied probabilities sum slightly above 1 | 1.012 to 1.070 | 1.000 to 1.150 |
| PASS | Pinnacle vs market-average odds agree on overlap seasons | r = 0.9995, mean |diff| = 0.0052 over 2490 matches | r > 0.98, mean |diff| < 0.03 |
| PASS | no missing referee, shots, fouls or cards | 0 missing cells | 0 |
| WARN | xG coverage (optional) | 2026/27 | optional; used only as cross-check |
| PASS | every Wikipedia team mapped to a team ID | 0 rows  | 0 unmapped |
| PASS | coaching-change dates parsed | 0 of 160 missing | 0 missing |
| PASS | coaching-change gap between vacancy and appointment plausible | 0 outside -60..200 days | 0 |
| PASS | coach known for team-matches | 93.0% known | >= 90% (unknown = change made outside the EPL) |
| WARN | referee names consistent | 'A Moss' (1 match) may be J Moss; 'K Kavanagh' (1 match) may be C Kavanagh; 'O Oliver' (1 match) may be M Oliver; 'S Scott' (1 match) may be G Scott | 0 suspected typos (kept as recorded) |
| PASS | current season data is fresh | last match 2026-11-08 (14 days ago) | <= 14 days |

## Completeness by season (share of matches with a value)

| Season | away_fouls | away_red | away_shots | away_sot | away_xg | away_yellow | close_away | close_draw | close_home | home_fouls | home_red | home_shots | home_sot | home_xg | home_yellow | referee_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2014/15 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2015/16 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2016/17 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2017/18 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2018/19 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2019/20 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2020/21 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2021/22 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2022/23 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2023/24 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2024/25 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2025/26 | 100% | 100% | 100% | 100% | 0% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0% | 100% | 100% |
| 2026/27 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |

## Cleaning log

| Source | Season | Rule | Rows | Detail |
| --- | --- | --- | --- | --- |
| football-data | 2014/15 | drop blank trailing rows | 1 |  |
| football-data | 2014/15 | parse 2-digit-year dates | 380 | dd/mm/yy -> date |
| football-data | 2016/17 | parse 2-digit-year dates | 380 | dd/mm/yy -> date |
| football-data | 2016/17 | normalise referee name (spaces, case) | 1 | 'l Mason' |
| football-data | 2023/24 | normalise referee name (spaces, case) | 1 | 'J Gillett ' |
| football-data | all | select closing odds source | 4660 | Pinnacle (PSC*) for 2014/15-2018/19, market average (AvgC*) from 2019/20 |
| football-data | all | rule check: sot_gt_shots | 1 | flagged, not dropped |
| football-data | all | rule check: result_mismatch | 0 | flagged, not dropped |
| football-data | all | rule check: negative | 0 | flagged, not dropped |
| football-data | all | rule check: duplicate | 0 | flagged, not dropped |
| wikipedia | 2014/15 | rename position column | 10 | 'League position' -> table_position |
| wikipedia | 2014/15 | remove footnote markers | 20 | e.g. '[61]' |
| wikipedia | 2015/16 | remove footnote markers | 26 | e.g. '[61]' |
| wikipedia | 2016/17 | remove footnote markers | 28 | e.g. '[61]' |
| wikipedia | 2017/18 | remove footnote markers | 26 | e.g. '[61]' |
| wikipedia | 2018/19 | remove footnote markers | 22 | e.g. '[61]' |
| wikipedia | 2019/20 | remove footnote markers | 20 | e.g. '[61]' |
| wikipedia | 2020/21 | remove footnote markers | 8 | e.g. '[61]' |
| wikipedia | 2021/22 | rename position column | 17 | 'Position in the table' -> table_position |
| wikipedia | 2021/22 | remove footnote markers | 34 | e.g. '[61]' |
| wikipedia | 2022/23 | rename position column | 22 | 'Position in the table' -> table_position |
| wikipedia | 2022/23 | remove footnote markers | 43 | e.g. '[61]' |
| wikipedia | 2023/24 | rename position column | 7 | 'Position in the table' -> table_position |
| wikipedia | 2023/24 | remove footnote markers | 14 | e.g. '[61]' |
| wikipedia | 2024/25 | rename position column | 16 | 'Position in the table' -> table_position |
| wikipedia | 2024/25 | remove footnote markers | 32 | e.g. '[61]' |
| wikipedia | 2025/26 | rename position column | 13 | 'Position in the table' -> table_position |
| wikipedia | 2025/26 | remove footnote markers | 26 | e.g. '[61]' |
| wikipedia | 2026/27 | rename position column | 11 | 'Position in the table' -> table_position |
| wikipedia | 2026/27 | remove footnote markers | 22 | e.g. '[61]' |
| wikipedia | all | flag interim / caretaker appointments | 27 |  |
| integration | all | unmapped Wikipedia team names | 0 |  |
