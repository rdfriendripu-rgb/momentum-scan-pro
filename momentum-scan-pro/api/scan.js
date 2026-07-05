// ════════════════════════════════════════════════════════════════
// api/scan.js — Vercel serverless function
//
// The browser calls THIS, never Twelve Data directly. Keys stay in
// environment variables on the server. Flow:
//   1. take a list of tickers (or a default universe)
//   2. fetch indicators server-side (keys hidden)
//   3. run the real scoring engine
//   4. write a dated snapshot to Supabase (this is what enables
//      "learning" — see api/record-outcomes.js)
//   5. return scored results to the client
//
// ENV required:
//   TWELVEDATA_KEY
//   SUPABASE_URL
//   SUPABASE_SERVICE_KEY   (service role — server only, never client)
// ════════════════════════════════════════════════════════════════

const { fetchIndicators } = require('../lib/twelvedata');
const { scoreTicker } = require('../lib/scoring');

const DEFAULT_UNIVERSE = ['NVDA','AMD','AVGO','MU','PLTR','META','AMZN','GOOGL'];

async function loadTunedWeights() {
  // Pull the latest learned weights if the learning loop has written any.
  // Falls back to defaults inside scoreTicker if this returns null.
  try {
    const url = process.env.SUPABASE_URL;
    const key = process.env.SUPABASE_SERVICE_KEY;
    if (!url || !key) return null;
    const r = await fetch(
      `${url}/rest/v1/model_weights?select=weights,version&order=created_at.desc&limit=1`,
      { headers: { apikey: key, Authorization: `Bearer ${key}` } }
    );
    const rows = await r.json();
    return rows && rows[0] ? rows[0] : null;
  } catch {
    return null;
  }
}

async function saveSnapshot(rows) {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) return { saved: false, reason: 'supabase not configured' };
  const today = new Date().toISOString().slice(0, 10);
  const payload = rows
    .filter((r) => r.score != null && r.price != null)
    .map((r) => ({
      snapshot_date: today,
      ticker: r.ticker,
      price: r.price,
      change_pct: r.changePct,
      score: r.score,
      pillar_trend: r.pillars.trend,
      pillar_momentum: r.pillars.momentum,
      pillar_volume: r.pillars.volume,
      pillar_position: r.pillars.position,
      pillar_news: r.pillars.news,
      signal: r.signal,
      rsi: r.rsi,
      entry: r.entry,
      target: r.target,
      stop: r.stop,
      weights_version: r.weightsVersion,
    }));
  const r = await fetch(`${url}/rest/v1/daily_snapshots`, {
    method: 'POST',
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      'Content-Type': 'application/json',
      Prefer: 'resolution=merge-duplicates', // upsert on (snapshot_date,ticker)
    },
    body: JSON.stringify(payload),
  });
  return { saved: r.ok, count: payload.length };
}

module.exports = async (req, res) => {
  if (req.method !== 'POST' && req.method !== 'GET') {
    res.status(405).json({ error: 'method not allowed' });
    return;
  }
  const key = process.env.TWELVEDATA_KEY;
  if (!key) {
    res.status(500).json({ error: 'TWELVEDATA_KEY not set on server' });
    return;
  }

  // tickers from body (POST) or query (?tickers=NVDA,AMD)
  let tickers = DEFAULT_UNIVERSE;
  try {
    if (req.method === 'POST' && req.body) {
      const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
      if (Array.isArray(body.tickers) && body.tickers.length) tickers = body.tickers;
    } else if (req.query && req.query.tickers) {
      tickers = String(req.query.tickers).split(',');
    }
  } catch { /* use default */ }

  tickers = [...new Set(tickers.map((t) => String(t).trim().toUpperCase()).filter(Boolean))]
    .slice(0, 30);

  const tuned = await loadTunedWeights();
  const weights = tuned ? tuned.weights : undefined;
  const weightsVersion = tuned ? tuned.version : 'default';

  // Fetch sequentially with a small delay to respect free-tier limits.
  // On a commercial data plan you can parallelise this.
  const results = [];
  for (const t of tickers) {
    try {
      const ind = await fetchIndicators(t, key);
      if (ind.error) { results.push({ ticker: t, error: ind.error }); continue; }
      results.push(scoreTicker({ ...ind, weightsVersion }, weights));
    } catch (e) {
      results.push({ ticker: t, error: e.message });
    }
    await new Promise((r) => setTimeout(r, 250));
  }

  const scored = results.filter((r) => !r.error).sort((a, b) => b.score - a.score);
  const snap = await saveSnapshot(scored);

  res.status(200).json({
    asOf: new Date().toISOString(),
    weightsVersion,
    count: scored.length,
    errors: results.filter((r) => r.error),
    snapshot: snap,
    results: scored,
  });
};
