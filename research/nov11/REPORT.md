# November 11, 2026: SportsDataIO audit of seven paper entries

All seven entries are **inconclusive** against SportsDataIO. Endpoint access and identity joins succeeded, but trial scrambling and missing historical as-of values prevent an honest corroborated/contradicted finding. No injury-adjusted win probabilities were invented, and no numerical superiority is claimed.

## Scope and provenance

Research base: development commit `37508d00d10401df021021afdff57850b68a1af8`. Isolated branch: `research/sportsdataio-positions-2026-11-11`. [Collection workflow](https://github.com/Jrixx-git/kalshi-ai-scanner/actions/runs/43058656461), executed commit `3074e30b441e86e31d90cda3c9585dba2cb42792`. The collection made exactly four provider GET requests, without retries, redirects, or pagination. Only schema, timestamps, response fingerprints, identity aggregates, and existing repository entry evidence were retained; no raw player values, medical notes, biographies, or API credentials were exported.

[summary.json](evidence/summary.json) contains the derived collection and immutable local inputs. [comparison.json](evidence/comparison.json) contains the verified entry-side comparison. The downloaded workflow ZIP SHA256 is `03973891b702f065dd3abb592b6d87f63d4a901a8aa86a8edc1d1e11b5fbde7f`, matching GitHub artifact 13872362244. The ZIP itself is not committed.

## Historical entries versus observed quotes

These are the original entries from the read-only ledger and `paper_evidence`, not prices reconstructed from a later report. All decisions occurred at **16:08:25 UTC / 10:08:25 AM Central**; the prior chat's approximate 10:18 entry time was incorrect. Quotes were observed at 16:08:25.012–16:08:25.354 UTC. Assumed fills add one cent to the selected-side observed ask, then fees are added separately. Elo probability refers to the purchased contract: SAS NO means CHI wins, MEM NO means DEN wins, UTA NO means ORL wins, and POR NO means OKC wins.

| Position | Sealed contract probability | Observed ask | Assumed fill | Fee | Total cost | Model edge | Finding |
|---|---:|---:|---:|---:|---:|---:|---|
| NYK YES vs CLE | 71.0505% | 64¢ | 65¢ | 2¢ | 67¢ | 4.0505 pp | Inconclusive |
| TOR YES vs BOS | 39.5420% | 32¢ | 33¢ | 2¢ | 35¢ | 4.5420 pp | Inconclusive |
| SAS NO vs CHI | 19.1331% | 10¢ | 11¢ | 1¢ | 12¢ | 7.1331 pp | Inconclusive |
| MEM NO vs DEN | 69.7841% | 61¢ | 62¢ | 2¢ | 64¢ | 5.7841 pp | Inconclusive |
| MIL YES vs LAL | 25.0566% | 13¢ | 14¢ | 1¢ | 15¢ | 10.0566 pp | Inconclusive |
| UTA NO vs ORL | 71.8602% | 60¢ | 61¢ | 2¢ | 63¢ | 8.8602 pp | Inconclusive |
| POR NO vs OKC | 64.1465% | 52¢ | 53¢ | 2¢ | 55¢ | 9.1465 pp | Inconclusive |

Every entry references archive `a4ac56badc64783b5ca6c9eaecc245bdad4f8415e1c8ff9780c22339e1e82395`, generated 15:51:22.117541 UTC and sealed/observed 15:51:22.346850 UTC. Verification confirms each entry forecast matches its sealed CSV; CSV, metadata, schedule and history hashes match the manifest. The later archive `beaa4885e4191e2d8f36f7b5e252b34ebedf70fdb26c54f0399bdd6ee5039b88` was generated at 16:18:17 UTC and was not substituted for the entry forecast. These model edges are arithmetic estimates, not evidence of profitable opportunities.

## Entitlements, authenticity, and source time

At 16:28:35–16:28:37 UTC (10:28 AM Central), all requests returned HTTP 200:

| Resource | Rows | Time information |
|---|---:|---|
| GamesByDate/2026-11-11 | 10 | Updated 11:12:51–11:28:19 Eastern; UTC tipoffs 00:00–03:00 Nov 12 |
| StartingLineupsByDate/2026-11-11 | 10 games | No top-level Updated/Created publication timestamp |
| PlayerGameProjectionStatsByDate/2026-11-11 | 349 | All Updated 11:24:57 Eastern = 16:24:57 UTC |
| projections/InjuredPlayers | 97 | No Updated/Created source publication timestamp |

The injury endpoint is accessible with this key at collection time; HTTP 200 does not certify a paid subscription or authentic medical/availability values. [SportsDataIO's scrambling policy](https://sportsdata.io/help/scrambled-data) says trial values may be perturbed and directs users to the field-level dictionary. Its [NBA dictionary](https://sportsdata.io/developers/data-dictionary/nba) marks injury status/body part/notes, lineup Starting/Confirmed/LineupStatus, and projected Minutes/Points/statistics as scrambled. PlayerID, team IDs and game identities are marked unscrambled. This is a documented trial limitation, not a claim that a hidden account-tier flag was independently retrieved. Absence of an IsScrambled response field does not override the dictionary. We excluded scrambled values from directional analysis, including aggregate injury counts as measures of team strength.

The [earlier trial run](https://github.com/Jrixx-git/kalshi-ai-scanner/actions/runs/43052759965) collected November 11 projections at 15:53:22 UTC, with Updated 10:51:59 Eastern = 15:51:59 UTC. That update and collection were **after the 15:51:22 forecast seal**, although before entries. Its preserved [summary](evidence/prior-entitlements.json) contains schema and hashes, not player/team values or nested lineup records, so it cannot reconstruct what any particular player was projected to do at entry. November 12 accessibility in that run does not supply November 11 as-of values.

New projection Updated 16:24:57 UTC is after the 16:08:25 entry cutoff. New receipt times are also after entry. Collection was before every selected tipoff (earliest 00:00 UTC November 12), verified against both sealed and provider schedules, but **pregame does not mean available at the decision**. Updated means last update in US Eastern per the dictionary, not first publication. The injury endpoint is current and undated ([API description](https://sportsdata.io/developers/api-documentation/nba)); it cannot establish a historical injury report. No post-tipoff results, final scores, or later realized performance were used to justify a position.

## Identity mapping

Each pair matched exactly one SportsDataIO game, with matching home/away orientation and UTC tipoff against the sealed forecast. Internal game IDs differ across providers and were not equated numerically. Lineups and projections were joined within SportsDataIO by GameID and PlayerID; abbreviations were normalized (including SA→SAS, NY→NYK, UTAH→UTA).

| Pair | Bot game ID | SportsDataIO GameID | Lineup IDs matched / lineup rows | Projection rows | Injury-feed rows for pair* |
|---|---:|---:|---:|---:|---:|
| NYK–CLE | 21718082 | 24095 | 34/34 | 34 | 4 |
| TOR–BOS | 21718083 | 24096 | 34/34 | 34 | 6 |
| SAS–CHI | 21718084 | 24097 | 34/34 | 34 | 6 |
| MEM–DEN | 21718085 | 24098 | 35/35 | 35 | 5 |
| MIL–LAL | 21718086 | 24099 | 36/36 | 36 | 2 |
| UTA–ORL | 21718088 | 24101 | 35/35 | 35 | 10 |
| POR–OKC | 21718090 | 24103 | 35/35 | 35 | 9 |

All 243 lineup IDs occur in their game's projections. No duplicate projection PlayerIDs or projection team abbreviation/TeamID mismatches were found in the selected games. This checks within-game membership, not independent real-world roster accuracy, player-name consistency, or each lineup player's own team-side assignment. No external player-ID crosswalk was required because Elo uses team-level inputs. *Injury-feed row counts describe returned trial records only; they do not establish genuine injury prevalence, severity, projected minutes lost, or directional support. All 243 selected projection rows had nonempty InjuryStatus; this is not interpreted as 243 genuinely injured players.*

## Validation and implications

The isolated workflow passed **205 existing tests plus 4 audit safeguard tests**. Local runs also passed those counts. An initial local full-suite attempt encountered Windows temporary-folder access errors; rerunning with a workspace temporary directory passed. Offline `verify.py` checks seven sealed entry links, archive hashes, exact contract-side probability/cost/edge arithmetic, quote/decision/seal ordering, provider schedule orientation/tipoffs, and pre-tipoff collection. No protected forecast, ledger, risk, or live-trading files differ from the pinned base.

The comparison is complete at the evidence level available: **0 corroborated, 0 contradicted, 7 inconclusive**. To make a directional finding later requires authentic entitled data with retained observations before the chosen decision cutoff, validated identity joins, and a specified player-to-team win-probability model. Any claim of improvement requires paired holdout validation against sealed Elo and contemporaneous market baselines, with fees and uncertainty included. This seven-position audit supplies neither an injury-adjusted pricing model nor that validation.
