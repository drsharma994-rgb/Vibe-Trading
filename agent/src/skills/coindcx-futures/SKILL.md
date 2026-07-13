---
name: coindcx-futures
category: data-source
description: CoinDCX Futures public market data (all active USDT/INR-margined futures & perpetual contracts, instrument specs, candlesticks). No authentication required for market data; read-only.
---

# CoinDCX Futures

## Overview

CoinDCX is an Indian crypto exchange offering USDT-margined and INR-margined futures/perpetual contracts. Every endpoint below is a public, unauthenticated GET call intended for market-data retrieval only. This skill must never be extended to place, modify, or cancel orders — that requires an account API key/secret which this skill does not use and should never be asked for.

## Quick Start

```python
import requests

BASE = "https://api.coindcx.com"
PUBLIC = "https://public.coindcx.com"

# 1. List every active USDT-margined futures contract
resp = requests.get(f"{BASE}/exchange/v1/derivatives/futures/data/active_instruments",
                     params={"margin_currency_short_name[]": "USDT"})
usdt_contracts = resp.json()  # e.g. ["B-BTC_USDT", "B-ETH_USDT", ...]

# 2. Contract spec (leverage, tick size, price band) for one pair
detail = requests.get(f"{BASE}/exchange/v1/derivatives/futures/data/instrument",
                       params={"pair": "B-BTC_USDT"}).json()["instrument"]

# 3. OHLCV candles (resolution: '1', '5', '60' minutes or '1D')
candles = requests.get(f"{PUBLIC}/market_data/candlesticks",
                        params={"pair": "B-BTC_USDT", "resolution": "60",
                                "from": 1710000000, "to": 1720000000,
                                "pcode": "f"}).json()["data"]
```

## Endpoints (public, GET only)

| Endpoint | Purpose |
|---|---|
| /exchange/v1/derivatives/futures/data/active_instruments | list all active futures pairs (filter with margin_currency_short_name[]=USDT or INR) |
| /exchange/v1/derivatives/futures/data/instrument | leverage, tick size, min/max price & quantity for one pair |
| /exchange/v1/derivatives/futures/data/trades | recent public trade prints |
| public.coindcx.com/market_data/candlesticks | OHLCV candles; resolution 1/5/60/1D, pcode=f for futures |
| public.coindcx.com/market_data/v3/orderbook/{pair} | live order book snapshot |

See `example_signal_engine.py` in this folder for ready-to-use Python wrappers, and https://docs.coindcx.com/ for the full reference and rate limits.

## Guardrails

- Read-only. Never pass an API key/secret through this skill, and never call the authenticated order-placement endpoints documented on the CoinDCX site.
- CoinDCX's Market Data Terms prohibit redistributing raw market data to third parties — treat output as for the account owner's own research only.
- CoinDCX explicitly disclaims giving investment advice; any "setup" produced from this data is informational, not a recommendation.
