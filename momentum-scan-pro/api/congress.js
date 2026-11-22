// ════════════════════════════════════════════════════════════════
// api/congress.js — Congress (House) stock trades from public PTRs
//
//   /api/congress?ticker=NVDA  -> trades in that stock (last 365 days)
//   /api/congress              -> the 40 most recently filed trades
//
// Read-only. Rows are written daily by scripts/congress_sync.py
// (GitHub Actions). Disclosures arrive up to 45 days after the trade
// and amounts are ranges — context, not a signal.
//
// ENV: SUPABASE_URL, SUPABASE_SERVICE_KEY
// ════════════════════════════════════════════════════════════════

const COLS = 'member,district,owner,ticker,asset,asset_type,txn_type,trade_date,filed,amount,option_info,days_to_disclose,late,url';

module.exports = async (req, res) => {
  const url = process.env.SUPABASE_URL, key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) { res.status(200).json({ trades: [], note: 'supabase not configured' }); return; }
  const ticker = String((req.query && req.query.ticker) || '').toUpperCase().trim();
  if (ticker && !/^[A-Z][A-Z0-9.\-]{0,9}$/.test(ticker)) { res.status(400).json({ error: 'bad ticker' }); return; }
  const since = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
  const q = ticker
    ? `congress_trades?select=${COLS}&ticker=eq.${encodeURIComponent(ticker)}&trade_date=gte.${since}&order=trade_date.desc&limit=25`
    : `congress_trades?select=${COLS}&ticker=not.is.null&order=filed.desc,trade_date.desc&limit=40`;
  try {
    const r = await fetch(`${url}/rest/v1/${q}`, { headers: { apikey: key, Authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(12000) });
    const rows = await r.json();
    if (!Array.isArray(rows)) { res.status(200).json({ trades: [], note: 'not set up yet' }); return; }
    const buys = rows.filter((x) => x.txn_type === 'purchase').length;
    const sells = rows.filter((x) => /sale/.test(x.txn_type || '')).length;
    res.setHeader('Cache-Control', 's-maxage=1800');
    res.status(200).json({ ticker: ticker || null, buys, sells, trades: rows });
  } catch (e) {
    res.status(200).json({ trades: [], note: 'read failed: ' + e.message });
  }
};
