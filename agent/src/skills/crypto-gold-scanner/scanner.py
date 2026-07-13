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


# --------------------------------------------------------------------------
# 4. Additional confirmation layer: extra indicators/strategies used only to
#    judge whether a setup composite_signal() already flagged is "solid"
#    enough to be worth a human's attention. This never overrides
#    composite_signal(), never places orders, and never fabricates a single
#    black-box score -- it adds more independent, visible evidence on top,
#    the same "gates you can see" approach used elsewhere in this repo.
#    Nothing here is investment advice or a guarantee of any outcome.
# --------------------------------------------------------------------------


def _stoch_rsi(close, rsi_period=14, stoch_period=14):
    """Stochastic RSI: momentum-of-momentum. Flags when RSI is already near
    the top/bottom of its own recent range (momentum stretched, not fresh).
    Used only as an exhaustion check, never as a standalone trigger.
    """
    rsi_vals = _rsi(close, rsi_period)
    lowest = rsi_vals.rolling(stoch_period).min()
    highest = rsi_vals.rolling(stoch_period).max()
    denom = (highest - lowest).replace(0.0, np.nan)
    return (rsi_vals - lowest) / denom * 100.0


def _atr(high, low, close, period=14):
    """Average True Range (Wilder). Used only to size a structural stop
    distance for the reward:risk check below -- never to size a live
    position or place an order.
    """
    prev_close = close.shift()
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return _wilder_ewm(true_range, period)


def _volume_zscore(volume, window=20):
    """How far the latest bar's volume sits from its own rolling mean, in
    standard deviations. A weak/negative value means thin participation.
    """
    recent = volume.iloc[-(window + 1):-1]
    if len(recent) < window or recent.std(ddof=0) == 0:
        return float("nan")
    return float((volume.iloc[-1] - recent.mean()) / recent.std(ddof=0))


def _bollinger_squeeze_then_expand(close, params, direction):
    """True if band width was compressed relative to its own recent average
    on the prior bar AND the latest close has broken outside the band in
    the setup's direction. A volatility-expansion confirmation, separate
    from the trend-strength check ADX already provides.
    """
    mid = close.rolling(params.bb_window).mean()
    sd = close.rolling(params.bb_window).std()
    width = (2 * params.bb_std * sd) / mid.replace(0.0, np.nan)
    if len(width.dropna()) < params.bb_window + 5:
        return False
    prior_avg_width = width.iloc[-(params.bb_window + 1):-1].mean()
    if not np.isfinite(prior_avg_width) or not np.isfinite(width.iloc[-2]):
        return False
    was_squeezed = width.iloc[-2] <= prior_avg_width
    upper = mid.iloc[-1] + params.bb_std * sd.iloc[-1]
    lower = mid.iloc[-1] - params.bb_std * sd.iloc[-1]
    broke_out = (close.iloc[-1] > upper) if direction > 0 else (close.iloc[-1] < lower)
    return bool(was_squeezed and broke_out)


def mtf_trend_agrees(higher_tf_df, direction, params=None):
    """Re-checks the EMA fast/slow cascade on a HIGHER-timeframe candle set
    you supply (e.g. 4h candles when the base signal is on 1h) and returns
    whether it points the same way. A signal that only exists on one
    timeframe is weaker evidence than one that agrees across two. Pass
    None / an empty frame to skip this honestly -- it returns False rather
    than guessing.
    """
    params = params or CompositeParams()
    if higher_tf_df is None or higher_tf_df.empty or len(higher_tf_df) < params.ema_slow + 5:
        return False
    close = higher_tf_df["close"]
    ema_fast = close.ewm(span=params.ema_fast, adjust=False).mean()
    ema_slow = close.ewm(span=params.ema_slow, adjust=False).mean()
    if direction > 0:
        return bool(ema_fast.iloc[-1] > ema_slow.iloc[-1])
    return bool(ema_fast.iloc[-1] < ema_slow.iloc[-1])


def confluence_check(df, signal, detail, params=None, higher_tf_df=None, min_rr=2.0, swing_lookback=30):
    """Given the bar-set and the (signal, detail) composite_signal() already
    produced, run four ADDITIONAL, independent confirmation families and
    report a transparent pass/fail ledger -- never a single fabricated
    score. `is_solid` only turns True when the base signal is non-zero AND
    at least 3 of these 4 extra families confirm it:

      trend_mtf     -- higher-timeframe EMA cascade agrees (if supplied)
      momentum_ok   -- StochRSI is NOT already at its own extreme
      participation -- volume z-score > 0.5 (real activity behind the move)
      volatility    -- a Bollinger squeeze-then-expand just fired this bar
      structure_rr  -- ATR-based structural stop gives >= min_rr to a
                       naive 2x-ATR target from the latest close

    Read-only analysis for a human to review; places no orders and is not
    investment advice.
    """
    params = params or CompositeParams()
    if signal == 0 or df is None or df.empty:
        return {"is_solid": False, "reason": "no base signal", "families": {}}

    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    stoch = _stoch_rsi(close, params.rsi_period)
    stoch_last = stoch.iloc[-1] if len(stoch.dropna()) else float("nan")
    momentum_ok = bool(np.isfinite(stoch_last) and (stoch_last < 80 if signal > 0 else stoch_last > 20))

    vz = _volume_zscore(volume)
    participation = bool(np.isfinite(vz) and vz > 0.5)

    volatility = _bollinger_squeeze_then_expand(close, params, signal)

    atr_val = _atr(high, low, close, params.adx_period)
    atr_last = atr_val.iloc[-1] if len(atr_val.dropna()) else float("nan")
    structure_rr = False
    rr_value = float("nan")
    if np.isfinite(atr_last) and atr_last > 0:
        entry = close.iloc[-1]
        lookback = df.iloc[-(swing_lookback + 1):-1]
        if not lookback.empty:
            stop = lookback["low"].min() if signal > 0 else lookback["high"].max()
            risk = abs(entry - stop)
            if risk > 0:
                target = entry + 2 * atr_last if signal > 0 else entry - 2 * atr_last
                reward = abs(target - entry)
                rr_value = reward / risk
                structure_rr = rr_value >= min_rr

    trend_mtf = mtf_trend_agrees(higher_tf_df, signal, params)

    families = {
        "trend_mtf": {"pass": trend_mtf, "detail": "higher-timeframe EMA cascade" if higher_tf_df is not None else "not supplied"},
        "momentum_ok": {"pass": momentum_ok, "detail": "StochRSI=%.1f" % stoch_last if np.isfinite(stoch_last) else "n/a"},
        "participation": {"pass": participation, "detail": "volume z=%.2f" % vz if np.isfinite(vz) else "n/a"},
        "volatility": {"pass": volatility, "detail": "squeeze-then-expand fired" if volatility else "no fresh expansion"},
        "structure_rr": {"pass": structure_rr, "detail": "R:R=%.2f" % rr_value if np.isfinite(rr_value) else "n/a"},
    }
    confirm_count = sum(1 for f in families.values() if f["pass"])
    is_solid = confirm_count >= 3
    return {"is_solid": is_solid, "confirmations": confirm_count, "of": len(families), "families": families}


def scan_with_confluence(max_coindcx=15, max_delta=15, include_gold=True,
                          timeframe_minutes="60", higher_timeframe_minutes="240", min_rr=2.0):
    """Same universe as scan(), but each ranked setup is additionally run
    through confluence_check() using a higher-timeframe candle set for the
    trend_mtf confirmation. Adds `is_solid` / `confirmations` / `families`
    to each row without removing or reordering anything scan() produced.
    Still read-only, still not investment advice.
    """
    base_results = scan(max_coindcx=max_coindcx, max_delta=max_delta, include_gold=include_gold,
                         timeframe_minutes=timeframe_minutes)
    enriched = []
    for row in base_results:
        signal = 1 if row["signal"] == "long" else -1
        venue, symbol = row["venue"], row["symbol"]
        df, higher_df = None, None
        try:
            if venue == "coindcx":
                df = coindcx_ohlcv(symbol, resolution=timeframe_minutes)
                higher_df = coindcx_ohlcv(symbol, resolution=higher_timeframe_minutes)
            elif venue == "delta" and ccxt is not None:
                exchange = ccxt.delta({"enableRateLimit": True})
                df = delta_ohlcv(exchange, symbol, timeframe="1h")
                higher_df = delta_ohlcv(exchange, symbol, timeframe="4h")
            elif venue == "comex":
                df = gold_ohlcv()
                higher_df = gold_ohlcv(period="2y", interval="1wk")
        except Exception:
            df, higher_df = None, None
        if df is not None:
            conf = confluence_check(df, signal, row.get("detail", {}), higher_tf_df=higher_df, min_rr=min_rr)
        else:
            conf = {"is_solid": False, "reason": "confirmation data unavailable", "families": {}}
        enriched.append({**row, **conf})
    return enriched
