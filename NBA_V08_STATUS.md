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
