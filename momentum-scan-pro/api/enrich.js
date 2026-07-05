// ════════════════════════════════════════════════════════════════
// api/enrich.js — per-ticker detail panels (analyst + insider)
//
// Called lazily when the user EXPANDS a stock card, so the main scan
// stays fast and we only spend Finnhub calls on stocks you actually
// look at. Returns two panels, each with its own 0-100 sub-score and
// the raw numbers behind it (so nothing is a black box).
//
// ENV: FINNHUB_KEY   (free tier covers both endpoints)
//
// Freshness, so you know how much to trust each:
//   insider (Form 4) .... reported within ~2 business days  -> timely
//   analyst ratings ..... consensus, slow-moving, often lags -> context
// ════════════════════════════════════════════════════════════════

const FH = 'https://finnhub.io/api/v1';

async function getJSON(url) {
  const r = await fetch(url, { signal: AbortSignal.timeout(12000) });
  return r.json();
}

// Analyst consensus -> 0-100. Weights strong buys highest, strong sells lowest.
function scoreAnalyst(rows) {
  if (!Array.isArray(rows) || !rows.length) return null;
  const r = rows[0]; // newest period, Finnhub returns newest-first
  const sb = r.strongBuy || 0, b = r.buy || 0, h = r.hold || 0,
        s = r.sell || 0, ss = r.strongSell || 0;
  const total = sb + b + h + s + ss;
  if (!total) return null;
  const score = Math.round(((sb * 100 + b * 75 + h * 50 + s * 25 + ss * 0) / total));
  return { score, strongBuy: sb, buy: b, hold: h, sell: s, strongSell: ss,
           total, period: r.period };
}

// Insider Form-4 net buying over ~90 days -> 0-100.
// transactionCode 'P' = open-market purchase, 'S' = sale.
function scoreInsider(payload) {
  const data = payload && Array.isArray(payload.data) ? payload.data : [];
  const cutoff = Date.now() - 90 * 864e5;
  const recent = data.filter((d) => {
    const t = Date.parse(d.transactionDate || d.filingDate || '');
    return t && t >= cutoff;
  });
  let buys = 0, sells = 0, buyShares = 0, sellShares = 0;
  const notable = [];
  for (const d of recent) {
    const code = (d.transactionCode || '').toUpperCase();
    const sh = Math.abs(Number(d.share || d.change || 0));
    if (code === 'P') { buys++; buyShares += sh; }
    else if (code === 'S') { sells++; sellShares += sh; }
    if (code === 'P' || code === 'S') {
      notable.push({ name: d.name, code, shares: sh,
                     date: d.transactionDate || d.filingDate });
    }
  }
  // Score: neutral 50, tilt up for net buying (rare and meaningful),
  // gently down for heavy net selling (common, less informative).
  let score = 50;
  const net = buys - sells;
  if (buys > 0 && sells === 0) score = 85;
  else if (net >= 2) score = 78;
  else if (net === 1) score = 66;
  else if (net === 0 && buys > 0) score = 58;
  else if (net < 0) score = Math.max(30, 50 + net * 4);
  return { score, buys, sells, buyShares, sellShares,
           notable: notable.slice(0, 6) };
}

module.exports = async (req, res) => {
  const key = process.env.FINNHUB_KEY;
  const ticker = String((req.query && req.query.ticker) || '').toUpperCase().trim();
  if (!ticker) { res.status(400).json({ error: 'ticker required' }); return; }
  if (!key) { res.status(200).json({ ticker, analyst: null, insider: null,
                                      note: 'FINNHUB_KEY not set on server' }); return; }

  const today = new Date().toISOString().slice(0, 10);
  const from = new Date(Date.now() - 120 * 864e5).toISOString().slice(0, 10);

  const [recRows, insPayload] = await Promise.all([
    getJSON(`${FH}/stock/recommendation?symbol=${ticker}&token=${key}`).catch(() => null),
    getJSON(`${FH}/stock/insider-transactions?symbol=${ticker}&from=${from}&to=${today}&token=${key}`).catch(() => null),
  ]);

  res.status(200).json({
    ticker,
    analyst: recRows ? scoreAnalyst(recRows) : null,
    insider: insPayload ? scoreInsider(insPayload) : null,
  });
};
