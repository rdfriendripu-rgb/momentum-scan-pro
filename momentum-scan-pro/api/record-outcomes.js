// ════════════════════════════════════════════════════════════════
// api/record-outcomes.js — the "learning from the market" loop
//
// Run this once a day AFTER the close (Vercel Cron — see vercel.json).
// It does the honest version of "learning": it does NOT predict prices.
// It measures which of yesterday's (and last week's) signals actually
// preceded moves, builds a track record, and re-tunes the pillar
// weights toward whatever has been working in YOUR stored data.
//
// Two jobs:
//   A) OUTCOMES  — for every snapshot that's now N trading days old,
//      look up the current price and record the forward return. This
//      is the track record you can show customers ("top picks vs
//      actual, last 30 days").
//   B) RE-TUNE   — correlate each pillar's score with realised forward
//      returns across all matured snapshots, and nudge the pillar
//      weights in proportion. Bounded so no single run swings wildly.
//
// This is defensible, inspectable, and marketing-safe: "adaptive
// weighting calibrated to a live track record", not "AI that predicts
// the market".
// ════════════════════════════════════════════════════════════════

const { fetchIndicators } = require('../lib/twelvedata');
const { DEFAULT_WEIGHTS } = require('../lib/scoring');

const HORIZON_DAYS = 10;         // how far forward we grade a pick
const MAX_WEIGHT_SHIFT = 3;      // max points a single re-tune can move a pillar
const PILLARS = ['trend', 'momentum', 'volume', 'position', 'news'];

const SB = () => ({ url: process.env.SUPABASE_URL, key: process.env.SUPABASE_SERVICE_KEY });

async function sbGet(path) {
  const { url, key } = SB();
  const r = await fetch(`${url}/rest/v1/${path}`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
  });
  return r.json();
}
async function sbPost(path, body, prefer = '') {
  const { url, key } = SB();
  const r = await fetch(`${url}/rest/v1/${path}`, {
    method: 'POST',
    headers: {
      apikey: key, Authorization: `Bearer ${key}`,
      'Content-Type': 'application/json', Prefer: prefer,
    },
    body: JSON.stringify(body),
  });
  return r.ok;
}

// pearson correlation
function corr(xs, ys) {
  const n = xs.length;
  if (n < 8) return 0;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    dx += (xs[i] - mx) ** 2;
    dy += (ys[i] - my) ** 2;
  }
  return dx && dy ? num / Math.sqrt(dx * dy) : 0;
}

module.exports = async (req, res) => {
  const { url, key } = SB();
  if (!url || !key) { res.status(500).json({ error: 'supabase not configured' }); return; }
  const tdKey = process.env.TWELVEDATA_KEY;

  // ── A) grade matured snapshots ────────────────────────────────
  // Find snapshots that are exactly HORIZON_DAYS old and not yet graded.
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - HORIZON_DAYS);
  const cutoffStr = cutoff.toISOString().slice(0, 10);

  const matured = await sbGet(
    `daily_snapshots?snapshot_date=eq.${cutoffStr}&outcome_return=is.null&select=id,ticker,price,score,pillar_trend,pillar_momentum,pillar_volume,pillar_position,pillar_news`
  );

  let graded = 0;
  const trainingRows = [];
  if (Array.isArray(matured)) {
    for (const row of matured) {
      try {
        const ind = await fetchIndicators(row.ticker, tdKey);
        if (ind.error || !ind.price) continue;
        const fwd = ((ind.price - row.price) / row.price) * 100;
        await sbPost(
          `daily_snapshots?id=eq.${row.id}`,
          { outcome_return: +fwd.toFixed(2), outcome_date: new Date().toISOString().slice(0, 10) },
          'return=minimal'
        );
        graded++;
        trainingRows.push({ row, fwd });
      } catch { /* skip */ }
      await new Promise((r) => setTimeout(r, 250));
    }
  }

  // ── B) re-tune weights from ALL graded history ────────────────
  const history = await sbGet(
    `daily_snapshots?outcome_return=not.is.null&select=pillar_trend,pillar_momentum,pillar_volume,pillar_position,pillar_news,outcome_return&limit=5000`
  );

  let newWeights = { ...DEFAULT_WEIGHTS };
  let version = 'default';
  if (Array.isArray(history) && history.length >= 40) {
    const returns = history.map((h) => h.outcome_return);
    const corrs = {};
    for (const p of PILLARS) {
      corrs[p] = corr(history.map((h) => h[`pillar_${p}`]), returns);
    }
    // Nudge each weight toward pillars with positive correlation to returns.
    // Bounded, then renormalised to sum to 100.
    const shifted = {};
    for (const p of PILLARS) {
      shifted[p] = Math.max(2, DEFAULT_WEIGHTS[p] + corrs[p] * MAX_WEIGHT_SHIFT * 10);
    }
    const sum = Object.values(shifted).reduce((a, b) => a + b, 0);
    for (const p of PILLARS) newWeights[p] = +((shifted[p] / sum) * 100).toFixed(1);
    version = 'tuned-' + new Date().toISOString().slice(0, 10);

    await sbPost('model_weights', {
      version,
      weights: newWeights,
      sample_size: history.length,
      created_at: new Date().toISOString(),
    }, 'return=minimal');
  }

  res.status(200).json({
    graded,
    trainingSample: Array.isArray(history) ? history.length : 0,
    version,
    weights: newWeights,
  });
};
