# MomentumScan Pro — predictive layer (Python)

Swing-horizon (a few days) momentum model you can **backtest on history** and
**paper-trade forward**. It learns the feature weighting from your data and
outputs a calibrated probability per stock — not a static score, and not a
confident-sounding guess you can't check.

## What each file does

| File | Role |
|---|---|
| `features.py` | Daily OHLCV → indicators (RSI, MACD hist, MA distances, ROC, rel-volume, range position, ATR). The model's inputs. |
| `dataset.py` | Pulls daily history (Twelve Data) and builds a labeled training set: features at day *t* vs the forward *H*-day return. |
| `backtest.py` | Walk-forward evaluation with an embargo (no look-ahead), non-overlapping rebalances, calibration table, and a cost-aware equity curve. |
| `predict.py` | `train` / `score` / `grade` — train & save the model, score the universe today, and grade past picks once their horizon elapses. |
| `run_backtest.py` | One command to test on history and save the equity curve + trades. |
| `ig_data.py` | IG connector (read-only): live prices, **client sentiment**, watchlist sync. No order placement. |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in TWELVEDATA_KEY (+ IG_* if using IG)
```

Load the `.env` (either `export $(cat .env | xargs)` or add
`from dotenv import load_dotenv; load_dotenv()` at the top of a script).

## Test it on history (backtest)

```bash
python run_backtest.py
```

Reads the report. The three numbers that matter:

- **ROC-AUC** — > 0.55 means the model has found *some* real signal; 0.50 is a coin flip.
- **Strategy vs baseline return** — the top-K picks should beat equal-weighting the whole universe **after costs**.
- **Calibration table** — the `actual` column should roughly track `predicted`. If the model says 60% and those win 60% of the time, its probabilities are trustworthy.

Set costs in `run_backtest.py` to match how you trade: shares = a few bps
round-trip, no funding; **IG CFDs = add `FUNDING_BPS_PER_DAY`** for overnight
financing on a leveraged multi-day hold (this is why a "few days" CFD swing
needs a bigger edge than the same trade in shares).

## Run it daily (forward paper-trade)

```bash
python predict.py train     # (re)train on all history, saves model.joblib
python predict.py score     # ranks the universe today, logs top-K to paper_trades.csv
python predict.py grade     # later: fills in what actually happened
```

`score` each morning + `grade` a week later builds a **live, out-of-sample
track record** that accumulates in real time — the honest test of whether the
backtest edge survives contact with the live market.

## Connecting IG

`ig_data.py` gives you live prices, watchlist sync, and **client sentiment**
(% of IG clients long vs short — a real crowd-positioning signal). Credentials
come from environment variables only. Example:

```python
from dotenv import load_dotenv; load_dotenv()
import ig_data
svc = ig_data.connect()
print(ig_data.find_epic(svc, "NVIDIA"))          # ticker -> IG epic
print(ig_data.client_sentiment(svc, "NVDA"))     # crowd long/short %
```

Two honest limits: IG's API does **not** expose the platform's news feed or
its third-party technical/analyst widgets (compute your own from OHLCV here),
and historical price pulls are metered by a **weekly datapoint allowance** —
which is why bulk training history comes from Twelve Data, and IG is used for
live signals and (once the model earns it) execution.

## Honest expectations

Momentum has a real, documented historical edge, but it's modest, it decays,
and it goes through painful drawdowns. This tool's job is to **measure**
whether *your* version has an edge after *your* costs — not to promise one.
Trust the calibration table and the live `grade` record over any single
backtest number. Nothing here is investment advice.
