# ============================================================================
#  MomentumScan Pro — Gate 1 backtest  (Google Colab, no Terminal needed)
#
#  HOW TO RUN:
#   1. Go to  https://colab.research.google.com  → New notebook
#   2. Paste this ENTIRE file into the first cell
#   3. Press the ▶ run button (or Shift+Enter)
#   4. When it asks, paste your Twelve Data key (it stays hidden, not saved)
#   5. Wait ~5 min (free tier paces 8 symbols/minute) → read the report
#
#  Runs on Google's servers in your browser. Nothing installs on your Mac.
# ============================================================================

import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "scikit-learn", "pandas", "numpy", "requests"])

import time, requests
import numpy as np, pandas as pd
from getpass import getpass
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss

# ---- config -----------------------------------------------------------------
KEY = getpass("Paste your Twelve Data API key, then press Enter: ").strip()

UNIVERSE = [
    "AAPL","MSFT","GOOGL","META","AMZN","NFLX","ORCL","CRM","ADBE",        # tech
    "NVDA","AMD","AVGO","MU","INTC","QCOM","TXN",                          # semis
    "JPM","BAC","GS","V","MA","AXP",                                       # financials
    "UNH","JNJ","LLY","PFE","ABBV",                                        # healthcare
    "WMT","COST","HD","MCD","NKE","SBUX",                                  # consumer
    "XOM","CVX","CAT","BA","GE","DIS","TSLA",                              # energy/ind/other
]
HORIZON = 5           # trading days held (swing)
UP_THRESHOLD = 2.0    # label = up >2% over the horizon
TOP_K = 5             # how many names you'd actually take
COST_BPS = 8          # round-trip transaction cost (bps)
FUNDING_BPS_PER_DAY = 0   # set ~1-2 to simulate IG CFD overnight funding
FREE_CHUNK = 8        # free tier: 8 symbols/minute
MINUTE_PAUSE = 62

FEATURE_COLS = ["rsi14","macd_hist","macd_hist_slope","dist_sma20","dist_sma50",
                "dist_sma200","ma_stack","roc5","roc20","rel_volume","range_pct",
                "atr_pct","upday_vol"]

# ---- data fetch (paced for the free tier) -----------------------------------
def _parse(payload):
    if not isinstance(payload, dict) or payload.get("status")=="error" or "values" not in payload:
        raise RuntimeError(payload.get("message","no data") if isinstance(payload,dict) else "no data")
    df = pd.DataFrame(payload["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["open","high","low","close","volume"]]

def load_universe(tickers):
    tickers = list(dict.fromkeys(t.upper() for t in tickers))
    batches = [tickers[i:i+FREE_CHUNK] for i in range(0,len(tickers),FREE_CHUNK)]
    out = {}
    for bi,batch in enumerate(batches):
        print(f"  fetching batch {bi+1}/{len(batches)}: {', '.join(batch)}")
        r = requests.get("https://api.twelvedata.com/time_series",
                         params=dict(symbol=",".join(batch), interval="1day",
                                     outputsize=800, apikey=KEY), timeout=30)
        d = r.json()
        for s in batch:
            payload = d if len(batch)==1 else d.get(s, {"status":"error"})
            try: out[s] = _parse(payload)
            except Exception as e: print(f"    skip {s}: {e}")
        if bi < len(batches)-1:
            print(f"    ...waiting {MINUTE_PAUSE}s for the free-tier window to reset")
            time.sleep(MINUTE_PAUSE)
    return out

# ---- features ---------------------------------------------------------------
def _rsi(c,p=14):
    d=c.diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/p,min_periods=p,adjust=False).mean()
    al=l.ewm(alpha=1/p,min_periods=p,adjust=False).mean()
    return 100-100/(1+ag/al.replace(0,np.nan))

def _macd_hist(c):
    m=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    return m-m.ewm(span=9,adjust=False).mean()

def _atr(df,p=14):
    h,l,c=df["high"],df["low"],df["close"]; pc=c.shift(1)
    tr=pd.concat([(h-l),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/p,min_periods=p,adjust=False).mean()

def compute_features(df):
    df=df.sort_index().copy(); close,vol=df["close"],df["volume"]
    s20,s50,s200=close.rolling(20).mean(),close.rolling(50).mean(),close.rolling(200).mean()
    hist=_macd_hist(close); atr=_atr(df); av20=vol.rolling(20).mean()
    hi55=df["high"].rolling(55).max(); lo55=df["low"].rolling(55).min()
    f=pd.DataFrame(index=df.index)
    f["rsi14"]=_rsi(close); f["macd_hist"]=hist/close
    f["macd_hist_slope"]=(hist-hist.shift(1))/close
    f["dist_sma20"]=close/s20-1; f["dist_sma50"]=close/s50-1; f["dist_sma200"]=close/s200-1
    f["ma_stack"]=((s20>s50)&(s50>s200)).astype(float)
    f["roc5"]=close/close.shift(5)-1; f["roc20"]=close/close.shift(20)-1
    f["rel_volume"]=vol/av20; f["range_pct"]=(close-lo55)/(hi55-lo55)
    f["atr_pct"]=atr/close
    f["upday_vol"]=((close.diff()>0).astype(float))*(vol/av20)
    return f

def build_dataset(frames):
    parts=[]
    for tk,df in frames.items():
        if df is None or len(df)<220: continue
        feats=compute_features(df)
        fwd=(df.sort_index()["close"].shift(-HORIZON)/df.sort_index()["close"]-1)*100
        b=feats[FEATURE_COLS].copy(); b["fwd_ret"]=fwd
        b["y"]=(fwd>UP_THRESHOLD).astype(float); b["ticker"]=tk; b["date"]=b.index
        parts.append(b)
    if not parts: return pd.DataFrame()
    return pd.concat(parts,ignore_index=True).dropna(subset=FEATURE_COLS+["fwd_ret"]).reset_index(drop=True)

# ---- walk-forward backtest --------------------------------------------------
def train(X,y):
    m=HistGradientBoostingClassifier(max_depth=3,learning_rate=0.05,max_iter=300,
        l2_regularization=1.0,min_samples_leaf=40,random_state=0); m.fit(X,y); return m

def calibration(prob,y,bins=10):
    df=pd.DataFrame({"p":prob,"y":y}); df["b"]=(df["p"]*bins).clip(0,bins-1).astype(int)
    g=df.groupby("b").agg(predicted=("p","mean"),actual=("y","mean"),n=("y","size"))
    g.index=[f"{b*100//bins}-{(b+1)*100//bins}%" for b in g.index]; return g.round(3)

def walk_forward(data):
    data=data.sort_values("date").reset_index(drop=True)
    dates=np.array(sorted(data["date"].unique()))
    start=int(len(dates)*0.5); rebal=dates[start::HORIZON]
    op,oy=[],[]; eq,beq=[1.0],[1.0]; cd=[]
    rt=COST_BPS/10000; fund=FUNDING_BPS_PER_DAY*HORIZON/10000
    for d in rebal:
        emb=d-np.timedelta64(HORIZON,"D")
        tr=data[data["date"]<=emb]; te=data[data["date"]==d]
        if len(tr)<500 or te.empty: continue
        m=train(tr[FEATURE_COLS].values,tr["y"].values)
        p=m.predict_proba(te[FEATURE_COLS].values)[:,1]; te=te.assign(prob=p)
        op.extend(p.tolist()); oy.extend(te["y"].tolist())
        picks=te.sort_values("prob",ascending=False).head(TOP_K)
        eq.append(eq[-1]*(1+picks["fwd_ret"].mean()/100-rt-fund))
        beq.append(beq[-1]*(1+te["fwd_ret"].mean()/100)); cd.append(pd.Timestamp(d))
    op,oy=np.array(op),np.array(oy)
    met={"oos_samples":len(oy),"base_rate":round(float(oy.mean()),3),
         "roc_auc":round(float(roc_auc_score(oy,op)),3) if len(set(oy))>1 else None,
         "brier":round(float(brier_score_loss(oy,op)),4),
         "accuracy":round(float(((op>0.5)==oy).mean()),3),"rebalances":len(cd),
         "strategy_return_pct":round((eq[-1]-1)*100,1),
         "baseline_return_pct":round((beq[-1]-1)*100,1)}
    if len(op)>=20:
        thr=np.quantile(op,0.9); top=oy[op>=thr]
        met["top_decile_hit_rate"]=round(float(top.mean()),3) if len(top) else None
    return met,calibration(op,oy)

# ---- run --------------------------------------------------------------------
print(f"Universe: {len(UNIVERSE)} tickers | horizon {HORIZON}d | up {UP_THRESHOLD}% | top-{TOP_K}\n")
frames = load_universe(UNIVERSE)
data = build_dataset(frames)
print(f"\nAssembled {len(data)} labeled rows from {len(frames)} tickers.")
met, calib = walk_forward(data)
print("\n================ BACKTEST REPORT ================")
for k,v in met.items(): print(f"  {k:22s}: {v}")
print("\n--- Calibration (does confidence match reality?) ---")
print(calib.to_string())
print("\nGate 1 needs: ROC-AUC >= 0.55, strategy beats baseline after costs,")
print("and the 'actual' column tracks the 'predicted' column.")
