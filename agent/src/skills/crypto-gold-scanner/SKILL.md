---
name: crypto-gold-scanner
category: strategy
description: Cross-venue futures scanner (CoinDCX + Delta Exchange crypto futures, plus XAU/USD gold) that ranks contracts using the repo's technical-basic composite indicator (EMA/ADX trend, Bollinger/RSI mean-reversion, OBV volume confirmation). Produces informational analysis only, never places orders.
---

# Crypto + Gold Futures Scanner

## Overview

Combines three data sources — coindcx-futures, delta-futures (ccxt), and yfinance for gold (ticker `GC=F`, COMEX futures in USD) — with the technical-basic composite indicator to surface ranked trade "setups" across CoinDCX futures, Delta Exchange futures, and gold. This is analysis only: it never authenticates to an exchange and never submits orders. Every setup is a starting point for the user's own research, not financial advice.

## Universe

1. **CoinDCX**: `coindcx_active_futures("USDT")` → all active USDT-margined perpetuals.
2. **Delta Exchange**: `delta_active_futures(exchange)` (ccxt) → all active perpetual/futures contracts.
3. **Gold**: `GC=F` (COMEX gold futures, USD) via yfinance. Cross-check any gold setup against the macro drivers in the commodity-analysis skill (real rates, DXY, safe-haven flows, central-bank buying) before treating it as high-conviction.

## Indicator methodology (matches technical-basic exactly)

- Trend: EMA(12) vs EMA(26) + ADX(14), Wilder smoothing, threshold 25
- Mean reversion: Bollinger Bands(20, 2σ) + RSI(14), oversold 30 / overbought 70
- Volume/participation confirmation: OBV vs its 20-period moving average
- Composite vote: long if trend is bullish + RSI not overbought + OBV rising; short if trend is bearish + RSI not oversold + OBV falling; otherwise stand aside

## Setup ranking

For every contract:
1. Pull OHLCV (1h default for crypto; 1D for gold).
2. Compute the composite vote above.
3. Keep only symbols where the vote is non-zero AND ADX is above threshold (trending, not chop).
4. Rank by `ADX * |EMA12 - EMA26| / close` (trend strength normalized by price), descending.
5. Optionally attach funding rate / open interest context from the crypto-derivatives and perp-funding-basis skills — context only, not part of the vote.

## Output contract

A list of dicts: `{venue, symbol, signal ("long"/"short"/"neutral"), rsi, adx, ema_fast, ema_slow, close}`.

See `scanner.py` in this folder for a runnable implementation.

## Guardrails

- Read-only market data across all three venues; no API keys, no order placement, no position management, no account access.
- CoinDCX Market Data Terms forbid redistributing raw market data to third parties — scanner output is for the account owner's own use only.
- Composite signals are historical/statistical pattern matches, not a guarantee of future performance. Crypto and gold futures are leveraged, high-risk instruments — always disclose this alongside any setup.
- This skill must never be wired to order-execution endpoints on any venue.

## Additional confirmation layer (is a setup "solid enough"?)

`composite_signal()` gives a base long/short/neutral vote. On top of that,
`confluence_check()` in `scanner.py` runs four MORE independent confirmation
families and reports a transparent pass/fail ledger -- never a single
fabricated score:

- **trend_mtf** -- the same EMA9/EMA26 cascade re-checked on a higher
  timeframe (e.g. 4h when the base signal is 1h). A signal that only
  exists on one timeframe is weaker evidence than one that agrees on two.
- **momentum_ok** -- Stochastic RSI is NOT already at its own extreme
  (>80 for longs / <20 for shorts), i.e. momentum isn't already stretched.
- **participation** -- volume z-score vs its own 20-bar mean is above 0.5,
  i.e. real activity is behind the move, not a thin/quiet drift.
- **volatility** -- a Bollinger Band squeeze-then-expand fired this bar
  (band width was compressed vs its recent average, then price broke out
  of the band in the setup's direction).
- **structure_rr** -- an ATR-based structural stop against the recent
  swing high/low still gives at least a 2:1 reward:risk to a naive 2x-ATR
  target.

`is_solid` only turns `True` when the base signal is non-zero AND at least
3 of these 4 extra families confirm it. `scan_with_confluence(...)` wraps
`scan()` and attaches `is_solid` / `confirmations` / `families` to every
row without changing scan()'s own ranking. This is still read-only
analysis for a human to review -- it does not place orders, does not
change position sizing, and is not investment advice. A "solid" setup can
still lose; a "not solid" one can still win. Treat it as one more filter,
not a promise.
