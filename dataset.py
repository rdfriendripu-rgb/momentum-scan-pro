"""
dataset.py — build a labeled training set across a universe of tickers.

Two parts:
  fetch_daily()   — pulls daily bars from Twelve Data. This is the only piece
                    that touches the network; kept small and isolated so the
                    rest of the pipeline is unit-testable without an API key.
  build_dataset() — pure function: stacks features (at day t) against the
                    forward return label (day t+horizon) across all tickers.
                    Fully testable on synthetic data.

Bulk history comes from Twelve Data (not IG) to spare IG's weekly datapoint
allowance. IG is used live for prices, client sentiment, and execution.
"""

import os
import time
import requests
import numpy as np
import pandas as pd

from features import compute_features, forward_return, FEATURE_COLS

TD_BASE = "https://api.twelvedata.com"


# Free tier = 8 API credits per minute; each symbol in a time_series call = 1
# credit. So we batch up to FREE_CHUNK symbols per request and pause a full
# minute between batches. On a paid plan, raise FREE_CHUNK and drop the pause.
FREE_CHUNK = 8
MINUTE_PAUSE = 62  # seconds — a little over 60 so the credit window fully resets


def _parse_series(payload) -> pd.DataFrame:
    """Turn one symbol's Twelve Data payload into a clean OHLCV frame."""
    if not isinstance(payload, dict) or payload.get("status") == "error" or "values" not in payload:
        msg = payload.get("message", "no data") if isinstance(payload, dict) else "no data"
        raise RuntimeError(msg)
    df = pd.DataFrame(payload["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["open", "high", "low", "close", "volume"]]


def fetch_daily(ticker: str, outputsize: int = 800, key: str | None = None) -> pd.DataFrame:
    """Daily OHLCV for ONE ticker (used by predict.py grade). Raises on error."""
    key = key or os.getenv("TWELVEDATA_KEY")
    if not key:
        raise RuntimeError("TWELVEDATA_KEY not set")
    r = requests.get(f"{TD_BASE}/time_series",
                     params=dict(symbol=ticker, interval="1day",
                                 outputsize=outputsize, apikey=key), timeout=15)
    try:
        return _parse_series(r.json())
    except Exception as e:
        raise RuntimeError(f"{ticker}: {e}")


def _fetch_batch(symbols, outputsize, key) -> dict:
    """Fetch up to ~120 symbols in ONE request (costs 1 credit per symbol).
    Twelve Data returns a single object when one symbol is asked, or a dict
    keyed by symbol when several are — this handles both."""
    r = requests.get(f"{TD_BASE}/time_series",
                     params=dict(symbol=",".join(symbols), interval="1day",
                                 outputsize=outputsize, apikey=key), timeout=30)
    d = r.json()
    out = {}
    if len(symbols) == 1:
        out[symbols[0]] = d
    else:
        for s in symbols:
            out[s] = d.get(s, {"status": "error", "message": "missing in batch response"})
    return out


def load_universe(tickers, outputsize=800, key=None, chunk=FREE_CHUNK, pause=MINUTE_PAUSE) -> dict:
    """Fetch daily bars for many tickers, pacing to respect the free-tier
    8-credits-per-minute cap. Batches `chunk` symbols per request and waits
    `pause` seconds between batches. Returns {ticker: DataFrame}; skips failures.
    """
    key = key or os.getenv("TWELVEDATA_KEY")
    if not key:
        raise RuntimeError("TWELVEDATA_KEY not set")
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    batches = [tickers[i:i + chunk] for i in range(0, len(tickers), chunk)]
    out = {}
    for bi, batch in enumerate(batches):
        print(f"  fetching batch {bi+1}/{len(batches)}: {', '.join(batch)}")
        try:
            for sym, payload in _fetch_batch(batch, outputsize, key).items():
                try:
                    out[sym] = _parse_series(payload)
                except Exception as e:
                    print(f"    skip {sym}: {e}")
        except Exception as e:
            print(f"    batch failed: {e}")
        if bi < len(batches) - 1:
            print(f"    ...waiting {pause}s for the free-tier credit window to reset")
            time.sleep(pause)
    return out


def build_dataset(price_frames: dict, horizon: int = 5, up_threshold: float = 2.0) -> pd.DataFrame:
    """Stack features + labels across the universe.

    Label `y` = 1 if the forward `horizon`-day return exceeds `up_threshold` (%).
    Also keeps `fwd_ret` (continuous) for the backtest's equity curve.
    Returns a tidy frame: [ticker, date, <features>, fwd_ret, y].
    """
    parts = []
    for ticker, df in price_frames.items():
        if df is None or len(df) < 220:
            continue
        feats = compute_features(df)
        fwd = forward_return(df, horizon)
        block = feats[FEATURE_COLS].copy()
        block["fwd_ret"] = fwd
        block["y"] = (fwd > up_threshold).astype(float)
        block["ticker"] = ticker
        block["date"] = block.index
        parts.append(block)
    if not parts:
        return pd.DataFrame()
    data = pd.concat(parts, ignore_index=True)
    # drop rows without full features or without a matured label
    data = data.dropna(subset=FEATURE_COLS + ["fwd_ret"]).reset_index(drop=True)
    return data
