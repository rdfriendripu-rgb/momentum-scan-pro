"""
predict.py — daily live scoring + forward paper-trade logging.

Covers the "forward-test" half of testing (the backtest covers the historical
half). Workflow you'd run once a day:

    python predict.py train      # (re)train on all history, save model.joblib
    python predict.py score      # score the universe today, log picks to CSV
    python predict.py grade      # grade past picks whose horizon has elapsed

`score` writes every day's ranked picks to paper_trades.csv with the date and
horizon. `grade` later fills in what actually happened — that's your live,
out-of-sample track record accumulating in real time, separate from the backtest.

IG client sentiment is shown alongside as extra context but is NOT a model
input (we don't have reliable historical sentiment to train on, so feeding it
live would be inconsistent). Keep the model honest: it predicts on the same
features it was trained on.
"""

import os
import sys
import joblib
import pandas as pd

from features import compute_features, forward_return, FEATURE_COLS
from dataset import fetch_daily, load_universe, build_dataset
from backtest import train_model

# ---- config (edit to taste, or move to .env) --------------------------------
# Wide, sector-spread universe so the ranking model has real DISPERSION to
# work with (not 15 correlated AI/tech names moving together). ~40 liquid
# large-caps across tech, semis, financials, healthcare, consumer, energy,
# industrials. On the free tier this loads in ~5 batches / ~5 minutes.
UNIVERSE = [
    # mega-cap tech / internet
    "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NFLX", "ORCL", "CRM", "ADBE",
    # semis
    "NVDA", "AMD", "AVGO", "MU", "INTC", "QCOM", "TXN",
    # financials
    "JPM", "BAC", "GS", "V", "MA", "AXP",
    # healthcare
    "UNH", "JNJ", "LLY", "PFE", "ABBV",
    # consumer
    "WMT", "COST", "HD", "MCD", "NKE", "SBUX",
    # energy / industrials / other
    "XOM", "CVX", "CAT", "BA", "GE", "DIS", "TSLA",
]
HORIZON = 5           # trading days held (swing)
UP_THRESHOLD = 2.0    # label = up >2% over the horizon
TOP_K = 5             # how many names you'd actually take
MODEL_PATH = "model.joblib"
LOG_PATH = "paper_trades.csv"


def train_and_save():
    print("Fetching history...")
    frames = load_universe(UNIVERSE, outputsize=800)
    data = build_dataset(frames, horizon=HORIZON, up_threshold=UP_THRESHOLD)
    if data.empty:
        raise RuntimeError("No training data assembled.")
    model = train_model(data[FEATURE_COLS].values, data["y"].values)
    joblib.dump({"model": model, "features": FEATURE_COLS,
                 "horizon": HORIZON, "threshold": UP_THRESHOLD}, MODEL_PATH)
    print(f"Trained on {len(data)} rows -> saved {MODEL_PATH}")


def score_today():
    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    frames = load_universe(UNIVERSE, outputsize=300)

    rows = []
    for ticker, df in frames.items():
        feats = compute_features(df).dropna(subset=FEATURE_COLS)
        if feats.empty:
            continue
        latest = feats.iloc[-1]
        prob = float(model.predict_proba(latest[FEATURE_COLS].values.reshape(1, -1))[0, 1])
        rows.append(dict(
            date=pd.Timestamp(feats.index[-1]).date(),
            ticker=ticker,
            prob_up=round(prob, 3),
            price=round(float(latest["close"]), 2),
            rsi14=round(float(latest["rsi14"]), 1),
            range_pct=round(float(latest["range_pct"]), 2),
            # ATR-based levels, same idea as the JS engine
            entry=round(float(latest["close"]), 2),
            stop=round(float(latest["close"] - 1.8 * latest["atr"]), 2),
            target=round(float(latest["close"] + 2.5 * latest["atr"]), 2),
            horizon=HORIZON,
        ))
    out = pd.DataFrame(rows).sort_values("prob_up", ascending=False).reset_index(drop=True)
    print(f"\n=== Today's ranked picks (top {TOP_K} are the trades) ===")
    print(out.to_string(index=False))

    # append the top-K to the paper-trade log for later grading
    picks = out.head(TOP_K).copy()
    picks["logged_at"] = pd.Timestamp.now().normalize().date()
    picks["outcome_ret"] = pd.NA
    header = not os.path.exists(LOG_PATH)
    picks.to_csv(LOG_PATH, mode="a", header=header, index=False)
    print(f"\nLogged top {TOP_K} to {LOG_PATH}")


def grade_log():
    """Fill outcome_ret for picks whose horizon has elapsed (forward track record)."""
    if not os.path.exists(LOG_PATH):
        print("No paper_trades.csv yet.")
        return
    log = pd.read_csv(LOG_PATH)
    log["date"] = pd.to_datetime(log["date"])
    updated = 0
    for i, row in log.iterrows():
        if pd.notna(row.get("outcome_ret")):
            continue
        if (pd.Timestamp.now() - row["date"]).days < row["horizon"] + 2:
            continue  # not matured yet
        try:
            df = fetch_daily(row["ticker"], outputsize=30)
            entry_price = row["price"]
            now_price = float(df["close"].iloc[-1])
            log.at[i, "outcome_ret"] = round((now_price - entry_price) / entry_price * 100, 2)
            updated += 1
        except Exception as e:
            print(f"  skip {row['ticker']}: {e}")
    log.to_csv(LOG_PATH, index=False)

    graded = log.dropna(subset=["outcome_ret"])
    if len(graded):
        hit = (graded["outcome_ret"] > 0).mean()
        print(f"Graded {updated} new. Live record: {len(graded)} picks, "
              f"win rate {hit*100:.0f}%, avg return {graded['outcome_ret'].mean():.2f}%")
    else:
        print(f"Graded {updated} new; none matured yet.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    {"train": train_and_save, "score": score_today, "grade": grade_log}.get(
        cmd, lambda: print("usage: python predict.py [train|score|grade]")
    )()
