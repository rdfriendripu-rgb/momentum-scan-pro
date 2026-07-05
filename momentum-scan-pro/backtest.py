"""
backtest.py — the "so I can test it" engine.

Walk-forward evaluation done honestly:
  * expanding-window training (only past data trains each step)
  * an EMBARGO gap so a training row's forward-looking label can't peek into
    the test window (real leakage protection, since 5-day labels overlap)
  * NON-OVERLAPPING rebalances (every `horizon` days) so paper trades don't
    stack on top of each other and inflate results
  * cost-aware equity curve (round-trip cost + optional CFD overnight funding),
    because a leveraged few-day hold on IG is not free

Outputs the numbers that tell you whether the model is real:
  ROC-AUC, Brier score, accuracy, precision of the top-K picks, a CALIBRATION
  TABLE (does "70% confident" actually win ~70%?), and an equity curve vs a
  naive equal-weight baseline.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss

from features import FEATURE_COLS


def train_model(X, y):
    m = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=300,
        l2_regularization=1.0, min_samples_leaf=40, random_state=0,
    )
    m.fit(X, y)
    return m


def calibration_table(prob, y, bins=10):
    df = pd.DataFrame({"p": prob, "y": y})
    df["bucket"] = (df["p"] * bins).clip(0, bins - 1).astype(int)
    g = df.groupby("bucket").agg(
        predicted=("p", "mean"), actual=("y", "mean"), n=("y", "size")
    )
    g.index = [f"{b*100//bins}-{(b+1)*100//bins}%" for b in g.index]
    return g.round(3)


def walk_forward(data: pd.DataFrame, horizon=5, top_k=5, cost_bps=10,
                 funding_bps_per_day=0, initial_frac=0.5):
    """Run the walk-forward backtest. `data` is the frame from build_dataset()."""
    data = data.sort_values("date").reset_index(drop=True)
    dates = np.array(sorted(data["date"].unique()))
    if len(dates) < 60:
        raise RuntimeError("Not enough history for a walk-forward test.")

    start_i = int(len(dates) * initial_frac)
    # rebalance dates: every `horizon`-th trading day after the initial train cut
    rebal_dates = dates[start_i::horizon]

    oos_prob, oos_y = [], []       # out-of-sample predictions for metrics
    equity, base_equity = [1.0], [1.0]
    curve_dates = []
    trades = []

    round_trip = cost_bps / 10000.0
    funding = (funding_bps_per_day * horizon) / 10000.0

    for d in rebal_dates:
        embargo_cut = d - np.timedelta64(horizon, "D")
        train = data[data["date"] <= embargo_cut]
        test = data[data["date"] == d]
        if len(train) < 500 or test.empty:
            continue

        model = train_model(train[FEATURE_COLS].values, train["y"].values)
        p = model.predict_proba(test[FEATURE_COLS].values)[:, 1]
        test = test.assign(prob=p)

        oos_prob.extend(p.tolist())
        oos_y.extend(test["y"].tolist())

        # trade: long the top-K by predicted probability, equal weight
        picks = test.sort_values("prob", ascending=False).head(top_k)
        gross = picks["fwd_ret"].mean() / 100.0
        net = gross - round_trip - funding
        equity.append(equity[-1] * (1 + net))

        # baseline: hold the whole universe equal weight, same period
        base_equity.append(base_equity[-1] * (1 + test["fwd_ret"].mean() / 100.0))
        curve_dates.append(pd.Timestamp(d))

        for _, row in picks.iterrows():
            trades.append(dict(date=pd.Timestamp(d), ticker=row["ticker"],
                               prob=round(row["prob"], 3), fwd_ret=round(row["fwd_ret"], 2)))

    if not oos_prob:
        raise RuntimeError("No out-of-sample folds produced — need more data.")

    oos_prob = np.array(oos_prob); oos_y = np.array(oos_y)
    metrics = {
        "oos_samples": int(len(oos_y)),
        "base_rate": round(float(oos_y.mean()), 3),      # how often 'up' happens at all
        "roc_auc": round(float(roc_auc_score(oos_y, oos_prob)), 3) if len(set(oos_y)) > 1 else None,
        "brier": round(float(brier_score_loss(oos_y, oos_prob)), 4),
        "accuracy": round(float(((oos_prob > 0.5) == oos_y).mean()), 3),
        "rebalances": len(curve_dates),
        "strategy_return_pct": round((equity[-1] - 1) * 100, 1),
        "baseline_return_pct": round((base_equity[-1] - 1) * 100, 1),
    }
    # precision of the highest-confidence decile
    if len(oos_prob) >= 20:
        thr = np.quantile(oos_prob, 0.9)
        top = oos_y[oos_prob >= thr]
        metrics["top_decile_hit_rate"] = round(float(top.mean()), 3) if len(top) else None

    return {
        "metrics": metrics,
        "calibration": calibration_table(oos_prob, oos_y),
        "equity_curve": pd.DataFrame({"date": curve_dates,
                                      "strategy": equity[1:], "baseline": base_equity[1:]}),
        "trades": pd.DataFrame(trades),
    }
