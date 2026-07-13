"""CoinDCX Futures public market-data fetchers.

Read-only market-data helpers for CoinDCX derivatives (USDT-M and INR-M
futures). No API key/secret is required or accepted here - this module only
ever calls public GET endpoints and must never be extended to place, modify,
or cancel orders.
"""

import time

import pandas as pd
import requests

BASE = "https://api.coindcx.com"
PUBLIC = "https://public.coindcx.com"


def list_active_futures(margin_currency="USDT"):
    """Return every active futures pair for a given margin currency (USDT or INR)."""
    resp = requests.get(
        BASE + "/exchange/v1/derivatives/futures/data/active_instruments",
        params={"margin_currency_short_name[]": margin_currency},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def instrument_spec(pair):
    """Leverage, tick size and price/quantity bounds for one futures pair."""
    resp = requests.get(
        BASE + "/exchange/v1/derivatives/futures/data/instrument",
        params={"pair": pair},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("instrument", {})


def fetch_ohlcv(pair, resolution="60", lookback_seconds=60 * 60 * 24 * 30):
    """OHLCV candles as a DataFrame indexed by UTC timestamp.

    resolution: '1', '5', '60' (minutes) or '1D'
    """
    now = int(time.time())
    resp = requests.get(
        PUBLIC + "/market_data/candlesticks",
        params={
            "pair": pair,
            "resolution": resolution,
            "from": now - lookback_seconds,
            "to": now,
            "pcode": "f",
        },
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json().get("data", [])
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.set_index("time").sort_index()[["open", "high", "low", "close", "volume"]]


if __name__ == "__main__":
    pairs = list_active_futures("USDT")
    print(str(len(pairs)) + " active USDT-margined futures contracts")
    if pairs:
        print(instrument_spec(pairs[0]))
        print(fetch_ohlcv(pairs[0]).tail())
