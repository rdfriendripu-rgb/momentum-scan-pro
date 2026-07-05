"""
ig_data.py — IG Trading connector (READ ONLY)

Wraps the `trading-ig` library to give the momentum engine three things
IG genuinely exposes through its public API:

  1. Historical OHLCV candles   -> for computing indicators / backtest history
  2. Client sentiment           -> % of IG clients long vs short (a crowd signal)
  3. Watchlists                 -> sync your universe straight from IG

What IG's API does NOT give you (don't expect it): the platform's news feed
and the pre-computed third-party technical/analyst widgets. Those are licensed
into the web UI, not the API. Compute your own technicals from the OHLCV here.

Credentials come from environment variables ONLY — never hardcode them, never
paste them into a chat. Set these in a .env (and load with python-dotenv) or
your shell:

  IG_USERNAME
  IG_PASSWORD
  IG_API_KEY
  IG_ACC_TYPE      = DEMO or LIVE
  IG_ACC_NUMBER    (optional; your spread-bet/CFD account, not ISA/SIPP)

Note on limits: IG meters historical data by a WEEKLY datapoint allowance.
For bulk backtest history, prefer a dedicated data vendor (e.g. Twelve Data)
and use IG for live prices, sentiment, and — once your model is proven —
execution. This module never places orders.
"""

import os
import pandas as pd
from trading_ig import IGService


def _env(name, default=None, required=False):
    v = os.getenv(name, default)
    if required and not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def connect():
    """Create an authenticated IG session from environment variables.

    Uses session version 2 (CST + X-SECURITY-TOKEN, valid 6h, auto-extends
    to 72h while in use). Returns a live IGService you can pass around.
    """
    svc = IGService(
        _env("IG_USERNAME", required=True),
        _env("IG_PASSWORD", required=True),
        _env("IG_API_KEY", required=True),
        _env("IG_ACC_TYPE", "DEMO"),
        acc_number=_env("IG_ACC_NUMBER"),
    )
    svc.create_session(version="2")
    return svc


def _normalise_prices(raw) -> pd.DataFrame:
    """Turn trading-ig's price frame into clean OHLCV using the MID price.

    trading-ig returns a DataFrame with MultiIndex columns like
    ('bid','Open'), ('ask','Close'), ('last','Volume'). We take the mid of
    bid/ask for OHLC and the last-traded volume, so downstream indicator
    code sees a plain open/high/low/close/volume frame (newest last).
    """
    df = raw["prices"] if isinstance(raw, dict) else raw
    out = pd.DataFrame(index=df.index)
    for col in ["Open", "High", "Low", "Close"]:
        try:
            out[col.lower()] = (df[("bid", col)] + df[("ask", col)]) / 2.0
        except Exception:
            # some markets only return 'last'
            out[col.lower()] = df[("last", col)]
    try:
        out["volume"] = df[("last", "Volume")]
    except Exception:
        out["volume"] = pd.NA
    return out.sort_index()  # chronological, oldest -> newest


def history(svc, epic, resolution="D", num_points=250) -> pd.DataFrame:
    """Fetch the most recent `num_points` candles for an epic.

    resolution: 'D', 'HOUR', '1MIN', '5MIN', '15MIN', '30MIN', etc.
    Watch your weekly allowance when pulling large windows.
    """
    raw = svc.fetch_historical_prices_by_epic_and_num_points(epic, resolution, num_points)
    return _normalise_prices(raw)


def history_range(svc, epic, start, end, resolution="D") -> pd.DataFrame:
    """Fetch candles between two dates (YYYY-MM-DD)."""
    raw = svc.fetch_historical_prices_by_epic_and_date_range(epic, resolution, start, end)
    return _normalise_prices(raw)


def client_sentiment(svc, market_id) -> dict:
    """Return IG client positioning: % long vs short for a market.

    A contrarian/confirmation signal — heavy retail crowding one way is
    itself information. `market_id` is the instrument's sentiment id (often
    the base ticker, e.g. 'NVDA'); resolve via fetch_market_by_epic if unsure.
    """
    r = svc.fetch_client_sentiment_by_instrument(market_id)
    return {
        "market_id": market_id,
        "long_pct": getattr(r, "longPositionPercentage", None) if not isinstance(r, dict) else r.get("longPositionPercentage"),
        "short_pct": getattr(r, "shortPositionPercentage", None) if not isinstance(r, dict) else r.get("shortPositionPercentage"),
    }


def find_epic(svc, term):
    """Search IG markets for a term (e.g. 'NVIDIA') and return candidate
    (epic, instrumentName, expiry) rows so you can build a ticker->epic map.
    IG uses epics, not tickers — this is the bridge.
    """
    res = svc.search_markets(term)
    df = res if isinstance(res, pd.DataFrame) else pd.DataFrame(res)
    cols = [c for c in ["epic", "instrumentName", "expiry", "instrumentType"] if c in df.columns]
    return df[cols] if cols else df


def universe_from_watchlist(svc, watchlist_name):
    """Pull all epics from one of your IG watchlists so your scan universe
    lives in IG and stays in sync. Returns a list of epics.
    """
    wls = svc.fetch_all_watchlists()
    wdf = wls if isinstance(wls, pd.DataFrame) else pd.DataFrame(wls)
    match = wdf[wdf["name"] == watchlist_name]
    if match.empty:
        raise ValueError(f"No watchlist named {watchlist_name!r}. Have: {list(wdf.get('name', []))}")
    wid = match.iloc[0]["id"]
    markets = svc.fetch_watchlist_markets(wid)
    mdf = markets if isinstance(markets, pd.DataFrame) else pd.DataFrame(markets)
    return list(mdf["epic"]) if "epic" in mdf.columns else []


def open_positions(svc) -> pd.DataFrame:
    """Read-only view of your current open positions (for a live P&L / risk
    panel later). This module intentionally has NO order-placement function.
    """
    r = svc.fetch_open_positions()
    return r if isinstance(r, pd.DataFrame) else pd.DataFrame(r)


if __name__ == "__main__":
    # Smoke test — requires real env vars and network; safe to run yourself.
    svc = connect()
    print("Connected.")
    print(find_epic(svc, "NVIDIA").head())
    # df = history(svc, "UA.D.NVDA.CASH.IP", "D", 60)   # example US-share CFD epic
    # print(df.tail())
