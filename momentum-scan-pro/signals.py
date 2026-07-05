"""
signals.py — multi-source enrichment layer.

Attaches alternative-data signals to each ticker. Every source is OPTIONAL:
if its key is missing or the call fails, that signal returns None and the rest
still work. Each signal is tagged FRESH (usable as a live/predictive feature)
or STALE (context/catalyst only — too lagged to time a few-day swing).

Keys (set in .env):
    QUIVER_API_KEY      congress, senate, insiders, 13F, WSB   (one key, lots of data)
    FINNHUB_KEY         company + market/Fed news
    ANTHROPIC_API_KEY   scores news headlines into a sentiment number

Freshness reality (why some are context-only):
    insider Form-4 buying ...... FRESH  (reported within ~2 business days)
    WSB / Reddit chatter ....... FRESH  (live)
    news + sentiment ........... FRESH  (live)
    congress / senate trades ... STALE  (disclosed up to ~45 days late)
    hedge-fund 13F ............. STALE  (quarterly, filed 45 days after quarter-end)

The FRESH numeric signals can feed the model as features (validated FORWARD via
predict.py's paper-trade log, since cheap historical news/insider data for a
backtest doesn't exist). The STALE ones are shown as context, not fed as timing
features.
"""

import os
import json
import datetime as dt
import requests

_quiver_client = None


def _quiver():
    global _quiver_client
    if _quiver_client is None:
        key = os.getenv("QUIVER_API_KEY")
        if not key:
            return None
        import quiverquant
        _quiver_client = quiverquant.quiver(key)
    return _quiver_client


def _recent(df, date_cols=("TransactionDate", "Date", "date", "file_date"), days=90):
    """Filter a Quiver DataFrame to the last `days` days using whatever date col exists."""
    if df is None or len(df) == 0:
        return df
    for c in date_cols:
        if c in df.columns:
            d = __import__("pandas").to_datetime(df[c], errors="coerce")
            cutoff = dt.datetime.now() - dt.timedelta(days=days)
            return df[d >= cutoff]
    return df


# ── FRESH: insider Form-4 buying ─────────────────────────────────
def insider_signal(ticker):
    q = _quiver()
    if not q:
        return None
    try:
        df = _recent(q.insiders(ticker), days=30)
        if df is None or len(df) == 0:
            return {"fresh": True, "net_buys": 0, "n": 0, "note": "no recent insider filings"}
        # Buys vs sells — column names vary; look for a transaction/direction field
        txt = df.astype(str)
        joined = txt.apply(lambda r: " ".join(r.values).lower(), axis=1)
        buys = joined.str.contains("purchase|acquired| p |code p| a ").sum()
        sells = joined.str.contains("sale|disposed| s |code s| d ").sum()
        return {"fresh": True, "net_buys": int(buys - sells), "n": int(len(df)),
                "label": "insider Form-4 (fresh)"}
    except Exception as e:
        return {"error": str(e)}


# ── FRESH: WSB / Reddit chatter ──────────────────────────────────
def wsb_signal(ticker):
    q = _quiver()
    if not q:
        return None
    try:
        df = q.wallstreetbets(ticker)
        df = _recent(df, days=7)
        if df is None or len(df) == 0:
            return {"fresh": True, "mentions_7d": 0}
        mcol = next((c for c in ["Mentions", "mentions", "Count"] if c in df.columns), None)
        scol = next((c for c in ["Sentiment", "sentiment"] if c in df.columns), None)
        return {"fresh": True,
                "mentions_7d": int(df[mcol].astype(float).sum()) if mcol else len(df),
                "sentiment": round(float(df[scol].astype(float).mean()), 3) if scol else None,
                "label": "WSB chatter (fresh)"}
    except Exception as e:
        return {"error": str(e)}


# ── STALE: congressional trades (context/catalyst only) ──────────
def congress_signal(ticker):
    q = _quiver()
    if not q:
        return None
    try:
        df = _recent(q.congress_trading(ticker), days=90)
        if df is None or len(df) == 0:
            return {"fresh": False, "net_buys_90d": 0, "label": "congress (STALE — context only)"}
        tcol = next((c for c in ["Transaction", "transaction"] if c in df.columns), None)
        if tcol:
            buys = df[tcol].astype(str).str.contains("Purchase", case=False).sum()
            sells = df[tcol].astype(str).str.contains("Sale", case=False).sum()
            net = int(buys - sells)
        else:
            net = 0
        return {"fresh": False, "net_buys_90d": net, "n": int(len(df)),
                "label": "congress (STALE — context only)"}
    except Exception as e:
        return {"error": str(e)}


# ── STALE: hedge-fund 13F changes (context only) ─────────────────
def institutional_signal(ticker):
    q = _quiver()
    if not q:
        return None
    try:
        df = q.sec13FChanges(ticker=ticker)
        if df is None or len(df) == 0:
            return {"fresh": False, "label": "13F (STALE — quarterly)"}
        return {"fresh": False, "n_funds": int(len(df)),
                "label": "13F (STALE — quarterly)"}
    except Exception as e:
        return {"error": str(e)}


# ── FRESH: Finnhub news headlines ────────────────────────────────
def finnhub_news(ticker, days=5):
    key = os.getenv("FINNHUB_KEY")
    if not key:
        return None
    try:
        today = dt.date.today()
        frm = today - dt.timedelta(days=days)
        r = requests.get("https://finnhub.io/api/v1/company-news",
                         params={"symbol": ticker, "from": str(frm), "to": str(today), "token": key},
                         timeout=12)
        items = r.json()
        heads = [i.get("headline", "") for i in items[:12] if i.get("headline")]
        return {"fresh": True, "headlines": heads, "n": len(heads)}
    except Exception as e:
        return {"error": str(e)}


# ── Market-wide: Fed / macro news (regime context) ───────────────
def fed_macro_news():
    key = os.getenv("FINNHUB_KEY")
    if not key:
        return None
    try:
        r = requests.get("https://finnhub.io/api/v1/news",
                         params={"category": "general", "token": key}, timeout=12)
        items = r.json()
        fed = [i.get("headline", "") for i in items
               if any(k in i.get("headline", "").lower()
                      for k in ["fed", "fomc", "powell", "rate cut", "rate hike", "inflation"])]
        return {"fed_headlines": fed[:8], "n": len(fed)}
    except Exception as e:
        return {"error": str(e)}


# ── LLM sentiment: turn headlines into a number in [-1, +1] ──────
def llm_sentiment(headlines):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key or not headlines:
        return None
    try:
        prompt = ("Score the overall stock-market sentiment of these headlines for the "
                  "company, as a single number from -1 (very bearish) to 1 (very bullish). "
                  "Reply with ONLY the number.\n\n" + "\n".join(f"- {h}" for h in headlines))
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": "claude-haiku-4-5-20251001", "max_tokens": 10,
                                "messages": [{"role": "user", "content": prompt}]},
                          timeout=20)
        txt = "".join(b.get("text", "") for b in r.json().get("content", []))
        val = float(txt.strip().split()[0])
        return max(-1.0, min(1.0, val))
    except Exception:
        return None


# ── Aggregate everything for one ticker ──────────────────────────
def enrich(ticker):
    """Returns a dict of all available signals for a ticker. Missing sources -> None.
    `news_sentiment` is the one meant to feed the model's news pillar; the STALE
    blocks are context you'd display, not train on.
    """
    news = finnhub_news(ticker)
    heads = news.get("headlines") if isinstance(news, dict) else None
    return {
        "ticker": ticker,
        # FRESH — candidate model features
        "insider": insider_signal(ticker),
        "wsb": wsb_signal(ticker),
        "news_sentiment": llm_sentiment(heads) if heads else None,
        "headlines": heads,
        # STALE — context / catalyst only
        "congress": congress_signal(ticker),
        "institutional_13f": institutional_signal(ticker),
    }


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    print(json.dumps(enrich(t), indent=2, default=str))
    print("\nMarket context (Fed/macro):")
    print(json.dumps(fed_macro_news(), indent=2, default=str))
