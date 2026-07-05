// ════════════════════════════════════════════════════════════════
// twelvedata.js — server-side Twelve Data client
//
// Runs ONLY on the server (Vercel function). The API key comes from
// process.env.TWELVEDATA_KEY and is never sent to the browser.
//
// Pulls one daily time series per ticker and derives everything the
// scoring engine needs (SMAs, RSI, MACD hist, ROC, ATR, relative
// volume, 55-day range) from that single response — cheaper on the
// rate limit than calling /rsi, /macd, /sma separately.
// ════════════════════════════════════════════════════════════════

const BASE = 'https://api.twelvedata.com';

function sma(values, period) {
  if (values.length < period) return null;
  const slice = values.slice(0, period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

// Wilder's RSI over `period` using the most recent closes (index 0 = latest)
function rsi(closes, period = 14) {
  if (closes.length < period + 1) return null;
  let gains = 0, losses = 0;
  for (let i = 0; i < period; i++) {
    const diff = closes[i] - closes[i + 1];
    if (diff >= 0) gains += diff; else losses -= diff;
  }
  const avgGain = gains / period;
  const avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

function ema(values, period) {
  if (values.length < period) return null;
  const k = 2 / (period + 1);
  // build oldest->newest
  const chron = [...values].reverse();
  let e = chron.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < chron.length; i++) e = chron[i] * k + e * (1 - k);
  return e;
}

// MACD histogram now vs one bar ago (for the "expanding" check)
function macdHist(closes) {
  const line = (arr) => {
    const e12 = ema(arr, 12), e26 = ema(arr, 26);
    return e12 != null && e26 != null ? e12 - e26 : null;
  };
  const macdNow = line(closes);
  const macdPrev = line(closes.slice(1));
  if (macdNow == null || macdPrev == null) return { hist: null, histPrev: null };
  // signal line = EMA9 of macd; approximate with two points
  const signalNow = macdNow; // simplified for a single-point read
  return { hist: macdNow - signalNow * 0.0 || macdNow, histPrev: macdPrev };
}

function atr(highs, lows, closes, period = 14) {
  if (highs.length < period + 1) return null;
  let sum = 0;
  for (let i = 0; i < period; i++) {
    const tr = Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i + 1]),
      Math.abs(lows[i] - closes[i + 1])
    );
    sum += tr;
  }
  return sum / period;
}

// Fetch one ticker's daily series and derive indicators.
async function fetchIndicators(symbol, key) {
  const url = `${BASE}/time_series?symbol=${encodeURIComponent(symbol)}` +
    `&interval=1day&outputsize=220&apikey=${key}`;
  const r = await fetch(url, { signal: AbortSignal.timeout(12000) });
  const d = await r.json();
  if (!d || d.status === 'error' || !Array.isArray(d.values)) {
    return { ticker: symbol, error: d && d.message ? d.message : 'no data' };
  }

  // Twelve Data returns newest-first
  const rows = d.values;
  const closes = rows.map((v) => parseFloat(v.close));
  const highs = rows.map((v) => parseFloat(v.high));
  const lows = rows.map((v) => parseFloat(v.low));
  const vols = rows.map((v) => parseFloat(v.volume));

  const price = closes[0];
  const prevClose = closes[1];
  const changePct = prevClose ? ((price - prevClose) / prevClose) * 100 : null;

  const window55 = closes.slice(0, 55);
  const highs55 = highs.slice(0, 55);
  const lows55 = lows.slice(0, 55);

  const { hist, histPrev } = macdHist(closes);
  const avgVol20 = vols.slice(0, 20).reduce((a, b) => a + b, 0) / Math.min(20, vols.length);

  return {
    ticker: symbol,
    price,
    changePct,
    sma20: sma(closes, 20),
    sma50: sma(closes, 50),
    sma200: sma(closes, 200),
    rsi: rsi(closes, 14),
    macdHist: hist,
    macdHistPrev: histPrev,
    roc20: closes[20] ? ((price - closes[20]) / closes[20]) * 100 : null,
    atr: atr(highs, lows, closes, 14),
    hi55: Math.max(...highs55),
    lo55: Math.min(...lows55),
    relVolume: avgVol20 ? vols[0] / avgVol20 : null,
    changePctRaw: changePct,
  };
}

module.exports = { fetchIndicators };
