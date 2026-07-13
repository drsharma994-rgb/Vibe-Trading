---
name: delta-futures
category: data-source
description: Delta Exchange futures/perpetual contracts via the ccxt library (already a pinned dependency, ccxt exposes a native "delta" exchange class). Public market data only, no API key required.
---

# Delta Exchange Futures

## Overview

Delta Exchange lists perpetual and dated futures on crypto majors and altcoins. This repo already pins `ccxt` in requirements-lock.txt, and ccxt ships a dedicated `delta` exchange class, so no bespoke HTTP client is needed to reach it.

## Quick Start

```python
import ccxt

exchange = ccxt.delta({"enableRateLimit": True})
markets = exchange.load_markets()

# Every live futures / perpetual contract
futures = {sym: m for sym, m in markets.items() if m.get("contract") and m.get("active", True)}
print(str(len(futures)) + " active Delta Exchange futures/perpetual contracts")

ohlcv = exchange.fetch_ohlcv("BTC/USDT:USDT", timeframe="1h", limit=200)
tickers = exchange.fetch_tickers(list(futures.keys())[:50])  # batch large universes
```

## Key fields (per market)

| Field | Meaning |
|---|---|
| m["contract"] | True for futures/perpetual/swap instruments |
| m["linear"] / m["inverse"] | Settlement currency type |
| m["limits"]["leverage"]["max"] | Max leverage |
| m["precision"] | Price/amount tick sizes |

See `example_signal_engine.py` in this folder for ready-to-use Python wrappers, and the general `ccxt` skill for the unified API shared across 100+ exchanges.

## Guardrails

- Only public ccxt methods are called here (`load_markets`, `fetch_ohlcv`, `fetch_tickers`, `fetch_order_book`). No `apiKey`/`secret` is configured, so trading methods (`create_order`, `cancel_order`, etc.) are intentionally unavailable — keep it that way.
- ccxt handles Delta Exchange's native symbol format internally; use ccxt unified symbols like `BTC/USDT:USDT`.
- Treat any generated "setup" as informational market analysis, not investment advice or an instruction to trade.
