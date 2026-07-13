"""Cross-venue futures + gold scanner.

Combines CoinDCX futures, Delta Exchange futures (via ccxt) and COMEX gold
futures (via yfinance) with the repo's technical-basic composite indicator
(EMA/ADX trend + Bollinger/RSI mean-reversion + OBV volume confirmation) to
rank trending "setups".

This module is READ-ONLY market analysis. It never authenticates to an
exchange, never submits/cancels orders, and is not investment advice.
"""

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests

try:
    import ccxt
except ImportError:  # pragma: no cover
    ccxt = None

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None


# --------------------------------------------------------------------------
# 1. Data sources
# --------------------------------------------------------------------------

COINDCX_BASE = "https://api.coindcx.com"
COINDCX_PUBLIC = "https://public.coindcx.com"


def coindcx_active_futures(margin_currency="USDT"):
    resp = requests.get(
        COINDCX_BASE + "/exchange/v1/derivatives/futures/data/active_instruments",
        params={"margin_currency_short_name[]": margin_currency},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def coindcx_ohlcv(pair, resolution="60", lookback_seconds=60 * 60 * 24 * 30):
    now = int(time.time())
    resp = requests.get(
        COINDCX_PUBLIC + "/market_data/candlesticks",
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


def delta_active_futures(exchange):
    markets = exchange.load_markets()
    return {s: m for s, m in markets.items() if m.get("contract") and m.get("active", True)}


def delta_ohlcv(exchange, symbol, timeframe="1h", limit=200):
    rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.set_index("time")


def gold_ohlcv(period="6mo", interval="1d"):
    if yf is None:
        return pd.DataFrame()
    df = yf.download("GC=F", period=period, interval=interval, progress=False)
    df = df.rename(columns=str.lower)
    return df[["open", "high", "low", "close", "volume"]]


# --------------------------------------------------------------------------
# 2. technical-basic composite indicator (EMA/ADX + BB/RSI + OBV voting).
#    Methodology matches agent/src/skills/technical-basic/SKILL.md exactly.
# --------------------------------------------------------------------------

@dataclass
class CompositeParams:
    ema_fast: int = 12
    ema_slow: int = 26
    adx_period: int = 14
    adx_threshold: float = 25.0
    bb_window: int = 20
    bb_std: float = 2.0
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    vol_ma_period: int = 20
    obv_ma_period: int = 20


def _wilder_ewm(series, period):
    return series.ewm(alpha=1 / period, adjust=False).mean()


def _rsi(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _wilder_ewm(gain, period)
    avg_loss = _wilder_ewm(loss, period)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _adx(high, low, close, period):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    atr = _wilder_ewm(tr, period)
    plus_di = 100 * _wilder_ewm(pd.Series(plus_dm, index=high.index), period) / atr
    minus_di = 100 * _wilder_ewm(pd.Series(minus_dm, index=high.index), period) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return _wilder_ewm(dx, period), plus_di, minus_di


def composite_signal(df, params=None):
    """Return (signal, detail) for the latest bar. signal in {1, -1, 0}."""
    params = params or CompositeParams()
    min_len = max(params.ema_slow, params.adx_period, params.bb_window) + 5
    if df is None or len(df) < min_len:
        return 0, {}

    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    ema_fast = close.ewm(span=params.ema_fast, adjust=False).mean()
    ema_slow = close.ewm(span=params.ema_slow, adjust=False).mean()
    adx, plus_di, minus_di = _adx(high, low, close, params.adx_period)

    bb_mid = close.rolling(params.bb_window).mean()
    bb_sd = close.rolling(params.bb_window).std()
    bb_upper = bb_mid + params.bb_std * bb_sd
    bb_lower = bb_mid - params.bb_std * bb_sd
    rsi = _rsi(close, params.rsi_period)

    obv = (volume * np.sign(close.diff().fillna(0))).cumsum()
    obv_ma = obv.rolling(params.obv_ma_period).mean()
    vol_ma = volume.rolling(params.vol_ma_period).mean()

    i = -1
    trend_bullish = (ema_fast.iloc[i] > ema_slow.iloc[i]) and (adx.iloc[i] >= params.adx_threshold)
    trend_bearish = (ema_fast.iloc[i] < ema_slow.iloc[i]) and (adx.iloc[i] >= params.adx_threshold)
    not_overbought = rsi.iloc[i] < params.rsi_overbought
    not_oversold = rsi.iloc[i] > params.rsi_oversold
    obv_rising = obv.iloc[i] > obv_ma.iloc[i]
    obv_falling = obv.iloc[i] < obv_ma.iloc[i]

    if trend_bullish and not_overbought and obv_rising:
        signal = 1
    elif trend_bearish and not_oversold and obv_falling:
        signal = -1
    else:
        signal = 0

    detail = {
        "close": close.iloc[i],
        "ema_fast": ema_fast.iloc[i],
        "ema_slow": ema_slow.iloc[i],
        "adx": adx.iloc[i],
        "rsi": rsi.iloc[i],
        "bb_upper": bb_upper.iloc[i],
        "bb_lower": bb_lower.iloc[i],
        "volume_ratio": volume.iloc[i] / vol_ma.iloc[i] if vol_ma.iloc[i] else np.nan,
    }
    return signal, detail


# --------------------------------------------------------------------------
# 3. Scanner
# --------------------------------------------------------------------------

def scan(max_coindcx=40, max_delta=40, include_gold=True, timeframe_minutes="60"):
    """Scan CoinDCX futures + Delta Exchange futures + gold, return ranked setups.

    Read-only analysis. Performs no authentication and places no orders on
    any venue. Results are informational, not investment advice.
    """
    results = []

    for pair in coindcx_active_futures("USDT")[:max_coindcx]:
        try:
            df = coindcx_ohlcv(pair, resolution=timeframe_minutes)
            signal, detail = composite_signal(df)
            if signal:
                results.append({
                    "venue": "coindcx",
                    "symbol": pair,
                    "signal": "long" if signal > 0 else "short",
                    **detail,
                })
        except Exception:
            continue

    if ccxt is not None:
        exchange = ccxt.delta({"enableRateLimit": True})
        futures = delta_active_futures(exchange)
        for symbol in list(futures)[:max_delta]:
            try:
                df = delta_ohlcv(exchange, symbol, timeframe="1h")
                signal, detail = composite_signal(df)
                if signal:
                    results.append({
                        "venue": "delta",
                        "symbol": symbol,
                        "signal": "long" if signal > 0 else "short",
                        **detail,
                    })
            except Exception:
                continue

    if include_gold:
        try:
            df = gold_ohlcv()
            signal, detail = composite_signal(df)
            results.append({
                "venue": "comex",
                "symbol": "GC=F (Gold)",
                "signal": "long" if signal > 0 else "short" if signal < 0 else "neutral",
                **detail,
            })
        except Exception:
            pass

    ranked = [r for r in results if r["signal"] != "neutral"]
    ranked.sort(
        key=lambda r: r.get("adx", 0)
        * abs(r.get("ema_fast", 0) - r.get("ema_slow", 0))
        / max(r.get("close", 1), 1e-9),
        reverse=True,
    )
    return ranked


if __name__ == "__main__":
    setups = scan()
    for row in setups[:20]:
        print(row)
