"""
features.py — turn a daily OHLCV frame into model features.

This is the Python port of the pillar logic from scoring.js, but built for
machine learning: instead of collapsing to hand-weighted 0-100 pillars, it
exposes the raw, normalised indicators and lets the model LEARN the weighting
from your history. The pillar scores are still computed (for a human-readable
dashboard), but the model trains on the raw feature columns.

Input:  DataFrame indexed by date, columns: open, high, low, close, volume
        (chronological, oldest -> newest)
Output: same index, one row per day, with feature columns + pillar scores.
        Early rows are NaN until enough history exists (dropna before training).
"""

import numpy as np
import pandas as pd

FEATURE_COLS = [
    "rsi14", "macd_hist", "macd_hist_slope",
    "dist_sma20", "dist_sma50", "dist_sma200",
    "ma_stack", "roc5", "roc20",
    "rel_volume", "range_pct", "atr_pct", "upday_vol",
]


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder smoothing
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _macd_hist(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd - sig  # true histogram (line minus signal)


def _atr(df, period=14):
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_index().copy()
    close, vol = df["close"], df["volume"]

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    hist = _macd_hist(close)
    atr = _atr(df)
    avg_vol20 = vol.rolling(20).mean()
    hi55 = df["high"].rolling(55).max()
    lo55 = df["low"].rolling(55).min()

    f = pd.DataFrame(index=df.index)
    f["rsi14"] = _rsi(close)
    f["macd_hist"] = hist / close                      # normalised by price
    f["macd_hist_slope"] = (hist - hist.shift(1)) / close
    f["dist_sma20"] = close / sma20 - 1                 # % above/below each MA
    f["dist_sma50"] = close / sma50 - 1
    f["dist_sma200"] = close / sma200 - 1
    f["ma_stack"] = ((sma20 > sma50) & (sma50 > sma200)).astype(float)
    f["roc5"] = close / close.shift(5) - 1
    f["roc20"] = close / close.shift(20) - 1
    f["rel_volume"] = vol / avg_vol20
    f["range_pct"] = (close - lo55) / (hi55 - lo55)     # 0=low .. 1=high of 55d range
    f["atr_pct"] = atr / close
    f["upday_vol"] = ((close.diff() > 0).astype(float)) * (vol / avg_vol20)

    # keep the current price & a few raw levels for the predictor/dashboard
    f["close"] = close
    f["atr"] = atr
    f["hi55"] = hi55
    f["lo55"] = lo55
    return f


def forward_return(df: pd.DataFrame, horizon: int) -> pd.Series:
    """% change from close[t] to close[t+horizon]. NaN for the last `horizon` rows."""
    close = df.sort_index()["close"]
    return (close.shift(-horizon) / close - 1) * 100
