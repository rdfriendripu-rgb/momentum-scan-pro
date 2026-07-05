#!/bin/bash
# MomentumScan Pro — one-command local test (macOS/Linux)
# Usage:  bash quickstart.sh
set -e

echo "==> Installing dependencies..."
pip3 install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "!!  Created .env — open it and paste your TWELVEDATA_KEY, then re-run this script."
  echo "    (IG_* keys are optional; only needed for live IG prices/sentiment.)"
  exit 0
fi

# load .env into the environment
export $(grep -v '^#' .env | grep -v '^$' | xargs)

if [ -z "$TWELVEDATA_KEY" ] || [ "$TWELVEDATA_KEY" = "your_twelvedata_key" ]; then
  echo "!!  TWELVEDATA_KEY not set in .env yet. Add it and re-run."
  exit 1
fi

echo "==> Running the walk-forward backtest on real data..."
python3 run_backtest.py

echo ""
echo "==> Done. To generate today's live picks next:"
echo "      python3 predict.py train   # train + save the model"
echo "      python3 predict.py score   # today's ranked picks"
echo "      python3 predict.py grade   # (a week later) what actually happened"
