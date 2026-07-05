"""
run_backtest.py — one command to test the model on history.

    python run_backtest.py

Pulls history for the universe, builds the labeled dataset, runs the
walk-forward backtest, prints the report, and saves the equity curve and
trade log to CSV so you can inspect or chart them.

Set costs to reflect how YOU trade:
  * shares (invest):        cost_bps ~5-10, funding 0
  * IG CFDs / spread bets:  cost_bps ~5-10 PLUS funding_bps_per_day for the
    overnight financing on a leveraged multi-day hold
"""

import pandas as pd
from dataset import load_universe, build_dataset
from backtest import walk_forward
from predict import UNIVERSE, HORIZON, UP_THRESHOLD, TOP_K

# how you're trading — change these two for shares vs CFDs
COST_BPS = 8              # round-trip transaction cost in basis points
FUNDING_BPS_PER_DAY = 0   # set ~1-2 for leveraged IG CFD overnight funding


def main():
    print(f"Universe: {len(UNIVERSE)} tickers | horizon {HORIZON}d | "
          f"up-threshold {UP_THRESHOLD}% | top-{TOP_K}")
    frames = load_universe(UNIVERSE, outputsize=800)
    data = build_dataset(frames, horizon=HORIZON, up_threshold=UP_THRESHOLD)
    if data.empty:
        print("No data assembled — check TWELVEDATA_KEY and tickers.")
        return

    res = walk_forward(data, horizon=HORIZON, top_k=TOP_K,
                       cost_bps=COST_BPS, funding_bps_per_day=FUNDING_BPS_PER_DAY)

    print("\n================ BACKTEST REPORT ================")
    for k, v in res["metrics"].items():
        print(f"  {k:22s}: {v}")
    print("\n--- Calibration (does confidence match reality?) ---")
    print(res["calibration"].to_string())
    print("\nHow to read it: ROC-AUC > 0.55 = some real signal; 0.5 = none.")
    print("Strategy return should beat baseline AFTER costs, and the")
    print("calibration 'actual' column should track the 'predicted' column.")

    res["equity_curve"].to_csv("equity_curve.csv", index=False)
    res["trades"].to_csv("backtest_trades.csv", index=False)
    print("\nSaved equity_curve.csv and backtest_trades.csv")


if __name__ == "__main__":
    main()
