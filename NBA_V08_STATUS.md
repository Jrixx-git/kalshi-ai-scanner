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
