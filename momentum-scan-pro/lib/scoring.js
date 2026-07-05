// ════════════════════════════════════════════════════════════════
// scoring.js — MomentumScan Pro scoring engine
//
// This replaces the hardcoded `sc:` values in the old prototype.
// Every score here is COMPUTED from live technical inputs.
//
// It is transparent, rule-based technical analysis — NOT a price
// prediction model. A 0-100 score is a *ranking* of how strong a
// momentum setup looks right now, decomposed into pillars so the UI
// (and the user) can see exactly why a stock scored what it did.
//
// Pillar weights live in DEFAULT_WEIGHTS. The "learning" loop
// (api/record-outcomes.js) adjusts these over time based on which
// pillars actually preceded moves in your stored history.
// ════════════════════════════════════════════════════════════════

// Default pillar weights. Must sum to 100.
// These are the numbers the learning loop tunes.
const DEFAULT_WEIGHTS = {
  trend: 30,      // price vs moving averages + MACD
  momentum: 25,   // RSI zone + rate of change
  volume: 20,     // relative volume / participation
  position: 15,   // where price sits in its recent range (breakout proximity)
  news: 10,       // headline sentiment (0 until the news pillar is wired in)
};

// ── helpers ──────────────────────────────────────────────────────
const clamp = (x, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, x));
const num = (x) => (typeof x === 'number' && isFinite(x) ? x : null);

// ── TREND (0-100 within pillar) ──────────────────────────────────
// Rewards price trading above rising moving averages and a positive,
// expanding MACD histogram. This is the "is it in an uptrend" pillar.
function trendScore({ price, sma20, sma50, sma200, macdHist, macdHistPrev }) {
  let s = 0;
  if (num(price) && num(sma20)) s += price > sma20 ? 22 : 0;
  if (num(price) && num(sma50)) s += price > sma50 ? 22 : 0;
  if (num(price) && num(sma200)) s += price > sma200 ? 18 : 0;
  // MA stacking (20 > 50 > 200) = clean uptrend
  if (num(sma20) && num(sma50) && num(sma200) && sma20 > sma50 && sma50 > sma200) s += 12;
  // MACD histogram sign + whether it's expanding (accelerating)
  if (num(macdHist)) {
    if (macdHist > 0) s += 14;
    if (num(macdHistPrev) && macdHist > macdHistPrev) s += 12; // momentum building
  }
  return clamp(s);
}

// ── MOMENTUM (0-100 within pillar) ───────────────────────────────
// RSI sweet-spot is ~55-70: strong but not yet exhausted. Overbought
// (>75) is penalised because chasing it is where retail gets hurt.
// Rate-of-change adds the "how fast" dimension.
function momentumScore({ rsi, roc20 }) {
  let s = 0;
  if (num(rsi)) {
    if (rsi >= 55 && rsi <= 70) s += 55;        // ideal momentum zone
    else if (rsi > 70 && rsi <= 75) s += 40;    // strong, getting hot
    else if (rsi > 75) s += 18;                 // overbought — risky
    else if (rsi >= 45 && rsi < 55) s += 35;    // neutral / building
    else if (rsi >= 35 && rsi < 45) s += 18;    // weak
    else s += 5;                                // oversold / broken
  }
  if (num(roc20)) {
    // 20-day rate of change, capped so a single monster move can't dominate
    s += clamp(roc20 * 1.8, -20, 45);
  }
  return clamp(s);
}

// ── VOLUME (0-100 within pillar) ─────────────────────────────────
// Relative volume = today vs its own 20-day average. Moves on high
// participation are more trustworthy than moves on thin volume.
function volumeScore({ relVolume, changePct }) {
  let s = 30; // baseline
  if (num(relVolume)) {
    if (relVolume >= 2.0) s += 45;
    else if (relVolume >= 1.5) s += 35;
    else if (relVolume >= 1.1) s += 22;
    else if (relVolume >= 0.9) s += 10;
    else s -= 5; // drying up
  }
  // reward volume that comes on an up-day, penalise heavy down-day volume
  if (num(relVolume) && num(changePct)) {
    if (relVolume > 1.2 && changePct > 0) s += 20;
    if (relVolume > 1.2 && changePct < -1) s -= 15;
  }
  return clamp(s);
}

// ── POSITION (0-100 within pillar) ───────────────────────────────
// Where does price sit inside its recent (e.g. 55-day) high/low band?
// Near the top of the range = breakout proximity. Uses ATR to flag
// how much room a stop needs.
function positionScore({ price, hi55, lo55 }) {
  if (!num(price) || !num(hi55) || !num(lo55) || hi55 <= lo55) return 40;
  const pctOfRange = ((price - lo55) / (hi55 - lo55)) * 100; // 0=low, 100=high
  // Sweet spot: 70-95% of range (pushing highs but not blown off the top).
  if (pctOfRange >= 95) return 78;        // at/above highs — breakout, but extended
  if (pctOfRange >= 70) return 92;        // strong, near breakout
  if (pctOfRange >= 50) return 62;
  if (pctOfRange >= 30) return 40;
  return 20;                              // near lows
}

// ── NEWS (0-100 within pillar) ───────────────────────────────────
// Placeholder until the news/sentiment pillar is wired in (Phase 3).
// `sentiment` is expected in [-1, +1]. Returns 50 (neutral) when absent
// so it neither helps nor hurts.
function newsScore({ sentiment }) {
  if (!num(sentiment)) return 50;
  return clamp(50 + sentiment * 50);
}

// ── ENTRY / TARGET / STOP (ATR-based, transparent) ───────────────
// Derives levels from volatility and the recent range instead of
// pulling numbers out of thin air like the old prototype did.
function levels({ price, atr, hi55, lo55 }) {
  const a = num(atr) ? atr : num(price) ? price * 0.03 : 0;
  const entry = price;
  const stop = num(price) ? +(price - 1.8 * a).toFixed(2) : null;         // 1.8 ATR below
  // Target: nearer of a measured move (2.5 ATR) or the prior range high extension
  const measured = num(price) ? price + 2.5 * a : null;
  const target = measured ? +measured.toFixed(2) : null;
  const riskReward = entry && stop && target && entry > stop
    ? +((target - entry) / (entry - stop)).toFixed(2)
    : null;
  return { entry: num(entry) ? +entry.toFixed(2) : null, stop, target, riskReward };
}

// ── SIGNAL CLASSIFICATION ────────────────────────────────────────
// Turns the pillar scores into a human-readable signal. Rule-based
// and inspectable — no black box.
function classify({ total, pillars, rsi, position, changePct }) {
  const tags = [];
  if (pillars.trend >= 70) tags.push('Uptrend');
  if (pillars.volume >= 70) tags.push('High volume');
  if (position >= 90) tags.push('Near breakout');
  if (num(rsi) && rsi > 75) tags.push('Overbought');
  if (pillars.momentum >= 70) tags.push('Strong momentum');

  let signal = 'neutral';
  if (num(rsi) && rsi > 78 && total < 70) signal = 'overbought';
  else if (total >= 80 && position >= 88) signal = 'breakout';
  else if (total >= 72) signal = 'strong';
  else if (total >= 55) signal = 'watch';
  else signal = 'weak';

  return { signal, tags };
}

// ── MAIN ENTRY POINT ─────────────────────────────────────────────
// `inputs` is one object per ticker with as many of these fields as
// you have. Missing fields degrade the score gracefully rather than
// breaking. `weights` lets the learning loop pass tuned weights in.
function scoreTicker(inputs, weights = DEFAULT_WEIGHTS) {
  const pillars = {
    trend: trendScore(inputs),
    momentum: momentumScore(inputs),
    volume: volumeScore(inputs),
    position: positionScore(inputs),
    news: newsScore(inputs),
  };

  const wSum = Object.values(weights).reduce((a, b) => a + b, 0) || 100;
  const total = clamp(
    Object.keys(pillars).reduce(
      (acc, k) => acc + (pillars[k] * (weights[k] || 0)) / wSum,
      0
    )
  );

  const lv = levels(inputs);
  const meta = classify({
    total,
    pillars,
    rsi: inputs.rsi,
    position: pillars.position,
    changePct: inputs.changePct,
  });

  return {
    ticker: inputs.ticker,
    price: num(inputs.price) ? +inputs.price.toFixed(2) : null,
    changePct: num(inputs.changePct) ? +inputs.changePct.toFixed(2) : null,
    score: Math.round(total),
    pillars: {
      trend: Math.round(pillars.trend),
      momentum: Math.round(pillars.momentum),
      volume: Math.round(pillars.volume),
      position: Math.round(pillars.position),
      news: Math.round(pillars.news),
    },
    signal: meta.signal,
    tags: meta.tags,
    ...lv,
    rsi: num(inputs.rsi) ? +inputs.rsi.toFixed(1) : null,
    weightsVersion: inputs.weightsVersion || 'default',
  };
}

module.exports = { scoreTicker, DEFAULT_WEIGHTS };
