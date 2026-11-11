# NBA v0.9 as-of research — November 11, 2026

Research branch: `research/nba-v09-asof-2026-11-11`. Development input commit: `785e848acbc0e5d849d4630848e6c5950afce9d6`.

**The observed market benchmark outperformed Elo on this matched sample. This does not establish a tradable edge. No trade is admitted by v0.9.**

## Coverage and missingness

| Measure | Count |
|---|---:|
| Games in archived schedule/forecast union | 118 |
| Eligible games with first sealed forecasts | 118 |
| Missing forecasts within that union | 0 |
| Valid contemporaneous quote + schedule pairs | 112 (94.9%) |
| Missing valid pairs | 6 (5.1%) |
| Matched games with verified final outcomes | 102 |
| Matched games without verified final outcomes | 10 |
| Major divergence flags (at least 8 percentage points) | 54 |
| v0.9 admitted paper trades | 0 |

The six unmatched games are November 10 IDs `21718074`, `21718075`, `21718076`, `21718078`, `21718079`, `21718080`. Missing means no pair passed the full as-of, identity and freshness checks; it does not assert that no raw quote exists. Every game retains failure counts and provenance in [verified-audit.json](validation/verified-audit.json). All six are outside the historical selected-position subset.

The archived date range is October 27–November 11, with no pregame schedule evidence dated November 3. This absence is **unknown coverage**, not proof of an off day. An additional inventory of 108 completed games from the archived BALLDONTLIE history inputs found no games omitted from the pregame union. That is a same-provider cross-check, not independent certification that every NBA game was supplied. The October 27 baseline has no raw schedule archive; its four sealed forecasts enter the union with that limitation. Later schedules retain unforecast and ineligible games rather than using selected trades as the denominator.

Inputs: 48 immutable market snapshots, 21 independent ESPN schedule captures, 155 fee records, 25 result snapshots, and the sealed prediction manifests. Result observations retain their original retrieval times; verified finals are used only as outcome labels, never to select a quote.

## Matched benchmark (same 102 games)

| Metric (lower is better) | Elo | Market midpoint |
|---|---:|---:|
| Brier score | 0.197521 | 0.176088 |
| Log loss | 0.576276 | 0.528070 |

| Absolute disagreement | Games | Elo Brier | Market Brier |
|---|---:|---:|---:|
| Below 3 points | 21 | 0.114298 | 0.113758 |
| 3 to below 8 points | 33 | 0.205120 | 0.192494 |
| 8 to below 15 points | 32 | 0.193771 | 0.178861 |
| At least 15 points | 16 | 0.298580 | 0.218513 |

Ten-bin calibration tables, log losses by disagreement, per-date coverage and per-game records are in the JSON. Bin counts are small; no statistical significance or independent-game assumption is claimed.

## Selection bias audit

Historical paper selection is read from a read-only connection to the existing ledger and is used only for subgroup labels.

| Subgroup | Total | Matched | Scored | Elo Brier | Market Brier |
|---|---:|---:|---:|---:|---:|
| Historically selected | 67 | 67 | 59 | 0.217017 | 0.184269 |
| Not selected | 51 | 45 | 43 | 0.170772 | 0.164862 |

Using only positions would omit 51 games and all six missing pairs. Full-union scoring reduces that selection problem but cannot remove bias from incomplete source coverage, capture timing, or schedule availability. The historical ledger is not rewritten or revalued by this research.

## Fee-adjusted counterfactual scenario

Use the canonical **home-team contract**, comparing YES and NO on that single contract, at the earliest valid capture after sealing. Require observed depth of at least one contract, ask plus 1 cent slippage, a verified as-of event fee schedule with the repository's rounded taker-fee calculation, and at least 3 cents net model edge. Block spreads above 10 points and absolute model–midpoint disagreement of at least 8 points.

Across 112 matches: 54 quality-blocked, 9 with unavailable/conflicting as-of fees, 39 below the edge threshold, and 10 hypothetical signals. Nine of those signals have verified results: **net -$1.14**, one contract each; one remains unscored. This is neither actual fills nor the historical portfolio return. It excludes portfolio constraints and assumes displayed size is fillable after slippage. All ten remain **unadmitted** because verified as-of player availability is unavailable.

The thresholds were chosen for this exploratory implementation, after historical outcomes existed. They are not a preregistered out-of-sample policy. No historical model, calibration temperature, archive or production risk limit was changed. SportsDataIO trial fields are not imported.

## Official injury evidence

The [official 2026–27 NBA injury index](https://official.nba.com/nba-injury-report-2026-27-season/) and its two latest available PDFs were retrieved with three GET requests at approximately **11:27 a.m. Central on November 11**. PDFs were labeled 12:00 and 12:15 p.m. Eastern (17:00 and 17:15 UTC). The raw bytes and individual request/receipt records are under [injuries](injuries/).

PDF publication timestamps are explicitly **inferred from the official filename in America/New_York**, with content unverified; they are separate from retrieval timestamps and HTTP Last-Modified. The collector does not extract or assert player statuses, submission completeness, team coverage, or injury severity. A raw PDF being available does not imply a healthy roster. These retrievals cannot be used as evidence available before the earlier entries. `asof()` requires publication, request and retrieval times to precede the decision and still returns player availability unverified and no-trade.

The collector accepts exactly the official season index and matching official NBA report URLs. Redirects are refused; each response is capped at 8 MiB and 15 seconds; it makes one index request plus at most four PDF requests, with no retry. Default is two PDFs. Failures have immutable unavailable records, never empty healthy-player lists. Raw and metadata files are content-addressed and exclusive-created. An index with no report links yields only an index record; it supplies no report evidence.

## Reproduction and prospective collection

Run from the repository root with Python 3.12+ (Windows also requires `tzdata`):

```text
python -m unittest discover -v
python nba_v09_research.py --output NEW_DIRECTORY/audit.json
python nba_v09_injuries.py --output NEW_DIRECTORY/injuries --max-reports 2
```

Outputs refuse conflicting overwrites. [Local validation log](validation/tests-local.log) records the complete suite. Local Python was 3.15 with the existing workspace dependency bundle providing timezone data; GitHub validation uses Python 3.12.

The isolated GitHub workflow performs offline tests and uploads a fresh audit without changing source archives. Its manual `collect_today` option reuses **the existing repository BALLDONTLIE_API_KEY secret** to retrieve the full day through the existing validated pagination API (at most two pages). It archives all games, collects public books without filtering to selected positions, and writes only its separate artifact directory. Locally the key was not present, so the authenticated prospective collection was not executed here. No key was purchased, copied or printed.

```text
python nba_v09_collect.py --output NEW_DIRECTORY/prospective
python nba_v09_research.py --additional-market-root NEW_DIRECTORY/prospective --output NEW_DIRECTORY/audit.json
```

The prospective collector is restricted to today's league date; it refuses retrospective reconstruction. Its wrapper allows at most 120 one-attempt Kalshi GET calls, at most 40 event fee captures, plus one existing independent schedule GET and the bounded NBA injury collector. Fee records collected after a first quote cannot qualify that earlier quote; later captures must still meet freshness checks. All partial raw captures remain auditable on failure. It never invokes an order endpoint or the paper trading engine. Scheduled collection is not enabled.

The branch is unmerged. Production execution and its risk limits are unchanged.
