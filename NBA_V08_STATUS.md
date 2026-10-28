# NBA v0.8: incremental work

This is not an operational automated trading system. The v0.7 research archives
and forecasts are unchanged. No order endpoint or Kalshi credential is used.

`python nba_v08_capture.py --output-dir paper_v08/snapshots` retrieves all open
KXNBAGAME markets and full public orderbooks, writing a timestamped,
content-addressed JSON snapshot. The command reports failures and exits nonzero
when individual books fail. A successful response is an observation, not a
promise that displayed prices can be filled. Snapshots are not automatically
persisted or scheduled by this change. Run without secrets; avoid publishing
sensitive information in the public repository.

PaperEngine reserves open position costs plus today's net realized losses against
$150, including fees, and caps aggregate open cost per ticker at $50. Its daily
boundary is UTC. This deliberately conservative reserve means the $150 budget
can bind before the $500 open-exposure cap. It is not a mark-to-market stop or a
loss guarantee: settlement corrections, gaps, and multi-ticker correlated bets
still require explicit handling. The existing runner requires manually supplied
probabilities and fees; it is not connected to NBA forecasts.

Remaining: verified contract/game matching and cancellation rules; quote
freshness and executable depth validation; fee and slippage model; immutable
forecast-to-market provenance; ledger exit and verified settlement handling;
reporting and automated scheduling with durable state; independent integration
and risk tests. Do not run automated entries until these are implemented and
validated. No conclusion about profitability follows from prediction accuracy.

## Matcher and valuation prototype

`nba_v08_valuation.py` adds strict pregame contract matching and a one-contract
research valuation: displayed ask, a one-cent slippage assumption, and
cent-rounded taker fee with verified standard series multiplier. It rejects
unsupported fees, changed rules, invalid or crossed quotes, and quotes older
than 30 seconds. This module is not wired to the existing paper runner and
cannot execute or simulate an order by itself. It does not establish an edge.

A live integration observation blocks deployment: on Oct 27, 2026 the
archived BALLDONTLIE Brooklyn at Boston forecast gave tipoff as 23:30 UTC,
while the corresponding Kalshi market's `occurrence_datetime` was 02:30 UTC
on Oct 28. Kalshi documents this field as when the underlying event occurred,
not specifically as its scheduled tipoff. Strict time matching currently rejects
this case. An independent, authoritative schedule source and a documented
contract-identity strategy are needed before relaxing this gate. Historical
forecasts must remain untouched. Settlement still needs public finalized market
results including scalar/fair-price treatment and independently auditable raw
snapshots. Automated execution, durable scheduler, dashboard, and a real
end-to-end paper cycle remain unimplemented.

Potential future markets: Kalshi lists NBA player points and first-quarter
winner and totals; first-quarter winner includes a tie contract, so a binary
full-game Elo model cannot value it. Player props require player minutes,
availability, and stat-distribution models. Quarter markets require separate
period-level models. Combo pricing requires joint probabilities and correlation;
RFQ communication is authenticated and can lead to execution, so it is outside
the read-only pipeline. See https://docs.kalshi.com/getting_started/rfqs and
https://kalshi.com/markets/kxnba1q/nba-1st-quarter-winner . No props or combo
execution has been enabled.

## Timestamp investigation and paper pipeline increment

On 2026-10-27, the NBA schedule listed Brooklyn at Boston on Oct 27 at
4:30 p.m. Pacific (23:30 UTC); NBA game identifier 0022600128 and the archived
BALLDONTLIE home/away IDs 2 and 3 refer to that matchup. The Kalshi contract
KXNBAGAME-26OCT27BKNBOS-BOS names Boston and Brooklyn in its primary rules,
and names Boston as the Yes winner. ESPN also lists that matchup at 4:30 p.m.
Pacific. Sources: https://www.nba.com/schedule ,
https://www.nba.com/nets/game/0022600128-nets-vs-celtics-boston-ma-10-27-2026 ,
https://www.espn.com/nba/game/_/gameId/401909877/nets-celtics . Kalshi's API
changelog defines `occurrence_datetime` as the recorded datetime when the
underlying event occurred, when available; it does not define it as scheduled
tipoff: https://docs.kalshi.com/changelog . The observed Kalshi value was
2026-10-28T02:30:00Z. We have not established why it differs. The matcher
continues to reject this event; no three-hour correction is applied.

`nba_v08_paper.py` adds a paper-only bridge. It checks v0.7 archive hashes,
rejects late forecasts, reads content-addressed snapshots, rechecks active
contracts and fees, and records at most one one-contract position per game.
It uses a 30-second market and book age limit and an assumed one-cent adverse
slippage. Ledger risk checks and provenance insertion are atomic. It records
raw finalized public market settlements, including scalar fair-price payouts,
and does not infer a result from a game score. Repeated cycles do not re-enter
an existing game. The existing v0.7 workflow runs the v0.8 cycle after scoring,
commits the separate `paper_v08/state` snapshots and SQLite ledger to the same
development branch, uploads evidence, and fails visibly on collection errors.
It is scheduled by the existing external trigger; branch-only GitHub cron does
not run by itself. Forecast and paper states remain separate. Network or push
failures can interrupt runs, and quotes may age out before evaluation.

`latest.json` reports cost-based open exposure, cash, realized equity, and
realized drawdown; these are paper estimates and not a mark-to-market balance.
Holding until finalized settlement is the only supported exit. This is a
research prototype pending live workflow verification. A complete synthetic
entry/settlement lifecycle in tests is not a real forward-tested profit record.

## Independent schedule identity gate

The NBA's published October 27 schedule confirms the four archived tipoffs:
https://www.nba.com/schedule/2026 . Kalshi documents occurrence_datetime as
when an underlying event occurred, not a scheduled-start field:
https://docs.kalshi.com/changelog . The observed +3-hour values are preserved
as secondary metadata, not corrected or assumed to be a game-end timestamp.

For automated entries the bridge now archives a fresh, unauthenticated ESPN NBA
scoreboard response by date (ESPN is named in Kalshi's NBA game settlement
sources). It requires one and only one scheduled ESPN event, ESPN numeric team
IDs and abbreviations, archived BALLDONTLIE team IDs, matching home/away teams,
league date, and tipoffs within one minute. It rejects stale, missing, ambiguous,
postponed, or started games. It then requires the exact KXNBAGAME event ticker,
both and only both team contracts, active binary status, exact selection and
primary rules, and a recognized fair-price cancellation provision. The two
sources' team IDs are explicitly mapped; they are never assumed equal. ISO
instant parsing honors offsets and rejects naive timestamps. The previously
archived v0.7 predictions are not changed.

The occurrence metadata must remain a valid aware timestamp but is not compared
to tipoff after the independent schedule gate succeeds. Matching does not imply
an opportunity: only a sufficiently fresh order book, supported fee schedule,
positive net edge of at least three cents after one-cent assumed slippage and
fees, and paper risk checks can create a one-contract simulated position. The
paper report lists identity evidence, quotes, computed side edges, and rejection
reasons. Schedule, order book, prediction, and simulated fill evidence are
archived separately. The default research workflow remains GET-only, and no
Kalshi authentication or order placement is used.

## First position audit and per-run records

The original Portland NO paper entry is backed by snapshot SHA-256
`0502e3c11cfb67fc685ff65b2e07daf4d39b75dc09cebb10b300f7a10d3b498c`.
Its YES bid was $0.4600 with 34,866.04 displayed contracts, equivalent to a
$0.5400 NO ask. The simulated fill was one contract at $0.5500, including a
one-cent adverse slippage assumption; displayed depth supports one contract
at the observed instant, not proof of an actual fill or of future availability.
The archived NBA series metadata reports quadratic fees and multiplier 1.
For one contract at $0.55 the fee is ceil-to-cent(0.07*1*0.55*0.45)=$0.02.
The position's total simulated stake and fee were $0.57.

From this version, each run writes its report into a content-addressed
`paper_v08/state/reports/` archive before replacing `latest.json`. On the
first run, it also preserves the previous latest report. Individual side
assessments record modeled edge or an explicit missing/invalid-book reason.
Git history is auditable but is not write-once storage against an administrator.
Synthetic tests exercise the archived real entry with hypothetical finalized
YES and NO outcomes, idempotent settlement, and immutable report history.
They do not assert the actual game outcome or guarantee a simulated fill.

## Portfolio audit and daily evidence

`nba_v08_daily.py` separately verifies each entry's sealed forecast and game
identity, archived schedule and market snapshot hashes, executable depth,
quote age, assumed slippage, and recorded standard-series fee. It archives
current public market, top-of-book, and paginated event fee-change observations.
The independent report is stored at `paper_v08/state/daily.json` with immutable
content-addressed copies under `audits/`; raw observations are under
`audit_snapshots/`. The serialized research workflow runs it after paper
reconciliation and fails visibly if the audit is incomplete.

Unrealized estimates are available only for active books with displayed bid
depth sufficient for the position. They use the bid minus recorded entry cost,
before any exit fee and without a guarantee of an actual fill. Separate times
mean values are not a simultaneous portfolio quote. Team exposure is the sum
of recorded entry costs for open games involving each team and is not an
estimate of correlation or a supplementary risk limit. Realized P&L remains
based on the recorded paper fees.

Kalshi publishes paginated `/events/fee_changes` history. That feed and current
market observations do not replace event metadata captured at the entry time:
all existing entry fees remain estimates. A returned empty list is not claimed
as a guarantee of complete historical fee data. The valuation engine still
uses the series-level fee assumption for new entries and does not enforce
market-specific fee overrides; resulting edge and P&L estimates need that
limitation. The audit does not send orders.

A new entry requires its immutable first forecast to be no more than 24 hours
old at decision time. Forecasts are not regenerated or replaced to pass the
check. The existing one-signal-per-game and quote-age checks remain in force.
