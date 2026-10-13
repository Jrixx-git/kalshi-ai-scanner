# Kalshi read-only scanner — prototype v0.1

Python 3.10+; standard library only. No credentials, no authenticated endpoints, no real orders.

Run: `python scanner.py --pages 3`

It downloads a limited number of open markets, filters by keyword into sports/crypto/politics/economics, and writes `markets.csv`. Categories are heuristic, so some markets will be missed or mislabeled.

To test a probability hypothesis, add a market ticker and your **independently estimated** YES probability between 0 and 1 to `estimates.csv`, then run again. `opportunities.csv` lists positive modeled EV using the displayed ask and a default *illustrative* $0.02/contract fee-and-slippage buffer. This is NOT Kalshi's actual fee calculation. Real fees vary; model them exactly before interpreting any edge. No AI prediction model is included yet, and without independently validated estimates there are no trustworthy +EV signals.

Paper journal example: `python scanner.py --paper --ticker EXAMPLE --side YES --price 0.45 --contracts 10`. This creates `paper_trades.csv`; trades must be manually settled and P&L calculated for now. It does not verify fills or liquidity. No notifications or background scheduling are included.

The market feed may change, be incomplete, or fail due to API changes/rate limits. Consult https://docs.kalshi.com and Kalshi's developer terms. Intended solely for personal research/paper trading. Check market settlement rules and eligibility before using any platform.
