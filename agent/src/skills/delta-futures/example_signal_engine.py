"""Delta Exchange futures public market-data fetchers (via ccxt).

Read-only: only public ccxt methods are called. No apiKey/secret is
configured, so this module has no ability to place, modify, or cancel
orders on Delta Exchange or any other venue.
"""

import ccxt
import pandas as pd


def get_exchange():
    return ccxt.delta({"enableRateLimit": True})


def list_active_futures(exchange=None):
    """Return {symbol: market} for every active futures/perpetual contract."""
    exchange = exchange or get_exchange()
    markets = exchange.load_markets()
    return {
        sym: m for sym, m in markets.items()
        if m.get("contract") and m.get("active", True)
    }


def fetch_ohlcv(symbol, timeframe="1h", limit=200, exchange=None):
    """OHLCV candles as a DataFrame indexed by UTC timestamp."""
    exchange = exchange or get_exchange()
    rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.set_index("time")


if __name__ == "__main__":
    ex = get_exchange()
    futures = list_active_futures(ex)
    print(str(len(futures)) + " active Delta Exchange futures/perpetual contracts")
    if futures:
        sample = next(iter(futures))
        print(fetch_ohlcv(sample, exchange=ex).tail())
