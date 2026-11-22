# Findings: real change or noise in the Premier League

Data to 8 November 2026 (EPL 2014/15 to 2026/27: 4,660 matches, 9,320 team-matches, 160 coaching changes). All numbers below come from the published database `data/epl.duckdb` and can be reproduced with `uv run python -m epl.pipeline`.

**Headline.** Most coaching decisions in the EPL follow results rather than underlying performance. Of 75 in-season sackings since 2015/16, only 30 (40%) were preceded by a statistically significant decline in underlying performance. A simple "five matches without a win" rule fired before 51 (68%). After a coaching change, the new coach produced a detectable improvement in only 17 of 80 tested changes (21%).

## 1. Measure used throughout

Historical expected goals (xG) are not available (only 2026/27), so underlying performance is the **shots-on-target difference**, adjusted for:

- **Venue:** league home advantage per season. It fell from about +1.0 shots on target in 2014/15 to +0.46 in the no-crowd season 2020/21, then returned to +1.0 in 2022/23 and 2023/24.
- **Opponent strength:** the opponent's rolling rating over its previous 38 EPL matches, computed before kick-off so that no future information is used.

One match has a standard deviation of σ = 3.13 shots-on-target difference around a team's season level. In 2026/27 this measure correlates at r = 0.66 with xG difference (200 team-matches), which supports using it as the stand-in.

## 2. Q1 Outlier detection: which matches deserve video review? (performance analyst)

**Method.** Robust z-scores (season median, pooled MAD) on five metrics: performance against the team's own level, shots, fouls, yellow cards, and result against the odds. A robust Mahalanobis distance (MCD) is computed over the same five. A team-match is flagged when |z| > 3 or the distance exceeds the χ² 99% quantile (15.09).

**Result.** 314 of 9,320 team-matches (3.4%) are flagged, between 12 and 36 per completed season. The main drivers are fouls (153), shots (74), performance against own level (58), yellow cards (28) and result against the odds (1).

The detector recovers matches known for exactly these reasons:

| Date | Team v opponent | Score | Why flagged |
| --- | --- | --- | --- |
| 2 May 2016 | Tottenham at Chelsea | 2-2 | 9 yellow cards (z = 5.4) |
| 21 Mar 2015 | Man City v West Brom | 3-0 | 43 shots (z = 5.2) |
| 18 Jan 2025 | Liverpool at Brentford | 2-0 | 37 shots (z = 4.2) |
| 14 Sep 2024 | Chelsea at Bournemouth | 1-0 | 8 yellow cards (z = 4.0) |
| 2 Dec 2017 | Arsenal v Man United | 1-3 | 33 shots but lost (z = 3.5) |

**Decision supported.** In 2026/27, 9 team-matches have been flagged so far, which is a manageable weekly review list. Manchester United appears 3 times (Ipswich, Fulham, Chelsea).

**Method note.** A first version scaled each season by its own MAD. Because a count's MAD is an integer, the scale jumped between seasons and 2024/25 got twice as many flags. Pooling the scale removed this artefact.

## 3. Q2 ANOM: are referees consistent? (referee committee)

**Method.** Analysis of means for Poisson rates, stratified by season: each referee's observed total is compared with the total expected from that season's league mean per match. Overdispersion is modest (φ = 1.08 for yellow cards, 1.22 for fouls). Limits are Bonferroni-corrected over the 32 referees with at least 30 matches (α = 0.05, z = 3.16).

| Measure | Referee | Matches | Per match | League | Difference | Signal |
| --- | --- | --- | --- | --- | --- | --- |
| Yellow cards | M Dean | 224 | 3.75 | 3.28 | +14.2% | Above |
| Yellow cards | G Scott | 105 | 2.68 | 3.29 | −18.7% | Below |
| Fouls | D Coote | 112 | 23.48 | 21.33 | +10.1% | Above |
| Fouls | A Madley | 138 | 23.07 | 21.64 | +6.6% | Above |
| Fouls | C Pawson | 283 | 22.63 | 21.56 | +4.9% | Above |
| Fouls | A Marriner | 208 | 18.86 | 21.45 | −12.1% | Below |

**Decision supported.** 30 of 32 referees for yellow cards, and 28 of 32 for fouls, are within the limits. The flagged referees are candidates for calibration review, not proof of bias.

The per-season view (V5) separates stable styles from single-season effects. M Dean is above average in most seasons. G Scott's first two seasons were high and later ones low, so his overall flag is a change of style rather than a constant.

**Limitation.** Fixture mix is not adjusted: senior referees get more high-stakes matches.

## 4. Q3 CUSUM: when did performance shift? (sporting director, analyst)

**Method.** Two-sided tabular CUSUM per team and season on standardised adjusted performance, with k = 0.5σ. The decision interval h = 2.6 was chosen by bootstrap simulation for an in-control run length of 80 matches per side, which is about one false alarm per side every two seasons. 2014/15 is the burn-in season for the ratings.

**Back-test on 75 in-season sackings (2015/16 to 2025/26):**

| Rule | Sackings preceded by an alarm | Median lead (matches) | Stable team-seasons with an alarm |
| --- | --- | --- | --- |
| CUSUM, h = 2.0 | 51% | 7 | 64% |
| CUSUM, h = 2.6 (default) | 40% | 4 | 41% |
| CUSUM, h = 4.0 | 20% | 8 | 19% |
| 5 matches without a win | 68% | 8 | 60% |

The results rule "predicts" sackings better because boards sack on results. The CUSUM is not trying to predict sackings. Its value is in the 31 sackings that followed the results rule with **no** decline in underlying performance: those decisions were most likely reacting to noise, which is exactly the risk this project addresses.

The operating curve (Team monitor, "How reliable are the alarms?") lets the director pick h knowingly: a lower h catches more true declines but raises more false alarms.

**Live example (2026/27, after 10 matches).** Crystal Palace's decline statistic reached 2.35 of 2.6 before the club sacked Pierre Sage on 12 November 2026; the evidence was building but not yet conclusive. Hull City (1.80), Newcastle (1.39) and Manchester United (1.37) are the next teams to watch. Sunderland raised the season's only improvement alarm, at match 5.

## 5. Q4 SPRT: did the new coach improve the team? (board)

**Method.** For each in-season permanent appointment, the baseline is the previous permanent coach's last (up to) 19 matches. H0 is no change; H1 is an improvement of δ = 0.5σ = 1.57 shots-on-target difference per match. Wald boundaries use α = 0.05 and β = 0.20, and caretaker matches are excluded. 80 changes were tested; 53 were excluded (51 pre-season appointments, 2 with baselines under 5 matches).

| Decision | Changes | Median matches to decide | Change in points per match | Change in adjusted performance |
| --- | --- | --- | --- | --- |
| Improved | 17 | 15 | +0.34 | +1.71 |
| No improvement | 41 | 9 | +0.09 | −0.52 |
| Undecided (38 matches or next change) | 18 | - | +0.07 | +0.56 |
| Undecided, ongoing | 4 | - | +0.68 | +0.94 |

**Decision supported.** A board can expect a reliable verdict on a new coach after about 9 to 15 matches, not 3 or 4. "No improvement" is usually clear sooner than "improved".

Across all tested changes, points per match rose from 0.96 to 1.11. Teams sack at a low point, so part of this rise is regression to the mean rather than the coach's effect.

## 6. Data management summary

- **Two sources.** football-data.co.uk (13 CSVs) and Wikipedia (13 season pages), stored raw with a SHA-256 manifest.
- **Cleaning, logged rule by rule.** Two date formats, a byte-order mark, a blank trailing row, two referee-name format fixes, footnote markers, three variants of the position column, and 27 interim appointments.
- **Integration.** Canonical team IDs map the short names (for example "Nott'm Forest") to the Wikipedia names (for example "Nottingham Forest"). Coach in charge is known for 93% of team-matches. The two closing-odds sources agree at r = 0.9995 on 2,490 overlapping matches.
- **QA gate.** 21 checks: 18 PASS and 3 WARN (one source row with more shots on target than shots, xG only in 2026/27, four suspected referee-name typos kept as recorded). A FAIL blocks publication. See `reports/data_quality.md`.

## 7. Limitations

- Shots on target ignore shot quality; xG would be better once a historical source is available.
- Opponent ratings come from shots on target only, and the rating window (38 matches) and shrinkage (10 matches) were set, not tuned.
- ANOM does not adjust for fixture mix; SPRT does not adjust for regression to the mean.
- Wikipedia lists changes made only while a club was in the EPL, so coaches before a club's first recorded change are labelled "Not recorded" (7% of team-matches).
