// ════════════════════════════════════════════════════════════════
// api/latest.js — instant read of the most recent stored scan
//
// The page calls this on load, so your whole watchlist appears
// already-scored with NO live scanning and NO rate limit — it just
// reads whatever the last scan wrote to Supabase. The scan (manual
// button or the daily job) is what WRITES; this only READS.
//
// ENV: SUPABASE_URL, SUPABASE_SERVICE_KEY
// ════════════════════════════════════════════════════════════════

function mapRow(x) {
  return {
    ticker: x.ticker,
    price: x.price,
    changePct: x.change_pct,
    score: x.score,
    pillars: { trend: x.pillar_trend, momentum: x.pillar_momentum,
               volume: x.pillar_volume, position: x.pillar_position, news: x.pillar_news },
    signal: x.signal,
    rsi: x.rsi,
    entry: x.entry, target: x.target, stop: x.stop,
  };
}

module.exports = async (req, res) => {
  const url = process.env.SUPABASE_URL, key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    res.status(200).json({ results: [], note: 'supabase not configured' });
    return;
  }
  try {
    // newest snapshot rows first; we keep only those from the latest date present
    const r = await fetch(
      `${url}/rest/v1/daily_snapshots?select=*&order=snapshot_date.desc,score.desc&limit=300`,
      { headers: { apikey: key, Authorization: `Bearer ${key}` } }
    );
    const rows = await r.json();
    if (!Array.isArray(rows) || !rows.length) {
      res.status(200).json({ results: [], note: 'no snapshots yet' });
      return;
    }
    const latest = rows[0].snapshot_date;
    const today = rows.filter((x) => x.snapshot_date === latest).map(mapRow);
    res.status(200).json({ asOf: latest, cached: true, count: today.length, results: today });
  } catch (e) {
    res.status(200).json({ results: [], note: 'read failed: ' + e.message });
  }
};
