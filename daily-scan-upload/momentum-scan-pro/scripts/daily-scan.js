// scripts/daily-scan.js — the "not just 8 stocks" engine.
//
// Runs on GitHub Actions (free), once per weekday. It paces through the
// ENTIRE sector universe at 8 requests/minute (the free Twelve Data limit),
// scores each with the real momentum engine, tags its sector, and upserts
// everything into Supabase. The website then just READS this — so you open
// the page to the full universe already scored, filterable, no live limit.
//
// GitHub Actions has no 10s timeout (jobs can run hours), so pacing is fine.
//
// Secrets (set as GitHub repo secrets, see the workflow file):
//   TWELVEDATA_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY

const { fetchIndicators } = require('../lib/twelvedata');
const { scoreTicker } = require('../lib/scoring');
const { allTickers, sectorOf } = require('../lib/universe');

const KEY = process.env.TWELVEDATA_KEY;
const SB_URL = process.env.SUPABASE_URL;
const SB_KEY = process.env.SUPABASE_SERVICE_KEY;
const CHUNK = 8;            // free tier: 8 credits/minute
const PAUSE_MS = 62000;     // wait out the minute between chunks

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function saveBatch(rows) {
  const today = new Date().toISOString().slice(0, 10);
  const payload = rows.filter((r) => r.score != null && r.price != null).map((r) => ({
    snapshot_date: today,
    ticker: r.ticker,
    sector: sectorOf(r.ticker),
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
    entry: r.entry, target: r.target, stop: r.stop,
    weights_version: 'default',
  }));
  if (!payload.length) return 0;
  const res = await fetch(`${SB_URL}/rest/v1/daily_snapshots`, {
    method: 'POST',
    headers: {
      apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`,
      'Content-Type': 'application/json', Prefer: 'resolution=merge-duplicates',
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) console.error('Supabase write failed:', res.status, await res.text());
  return res.ok ? payload.length : 0;
}

async function main() {
  if (!KEY || !SB_URL || !SB_KEY) {
    console.error('Missing env: need TWELVEDATA_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY');
    process.exit(1);
  }
  const tickers = allTickers();
  const chunks = [];
  for (let i = 0; i < tickers.length; i += CHUNK) chunks.push(tickers.slice(i, i + CHUNK));
  console.log(`Scanning ${tickers.length} tickers in ${chunks.length} paced batches...`);

  let saved = 0;
  for (let ci = 0; ci < chunks.length; ci++) {
    const batch = chunks[ci];
    console.log(`Batch ${ci + 1}/${chunks.length}: ${batch.join(', ')}`);
    const scored = [];
    for (const t of batch) {
      try {
        const ind = await fetchIndicators(t, KEY);
        if (ind.error) { console.log(`  skip ${t}: ${ind.error}`); continue; }
        scored.push(scoreTicker(ind));
      } catch (e) { console.log(`  err ${t}: ${e.message}`); }
    }
    saved += await saveBatch(scored);
    if (ci < chunks.length - 1) {
      console.log(`  ...waiting ${PAUSE_MS / 1000}s for the free-tier window`);
      await sleep(PAUSE_MS);
    }
  }
  console.log(`Done. Saved/updated ${saved} rows for ${new Date().toISOString().slice(0, 10)}.`);
}

main().catch((e) => { console.error(e); process.exit(1); });
