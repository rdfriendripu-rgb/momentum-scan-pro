# MomentumScan Pro

A momentum stock screener rebuilt from the v7 single-file prototype into a
**secure, persistent, honestly-scored** web app you can deploy and grow into a
commercial product.

This repo is **Phase 1: the backbone.** It fixes the three things that made the
prototype a demo rather than a product, and lays the foundation for the
"learns from the market daily" behaviour.

---

## What changed vs the prototype

| Prototype (v7 HTML) | This rebuild |
|---|---|
| `sc:91` scores **hardcoded** in a `STOCKS` array | Scores **computed live** from trend / momentum / volume / range position (`lib/scoring.js`) |
| API keys in browser `localStorage`, called direct | Keys in **server env vars**; browser only ever calls `/api/scan` |
| Anthropic calls from browser (no auth, 401s) | Deferred to Phase 3, server-side |
| Nothing stored → no learning possible | **Daily snapshot** of every scored ticker in Supabase |
| No feedback loop | `record-outcomes.js` grades old picks and **re-tunes pillar weights** |

## On "predictive / learning" — read this

The app does **not** predict prices. Genuine price prediction is where funds burn
millions, and claiming it in a UK product you sell would be both false and a
regulatory problem. What it actually does, which is defensible and useful:

- **Transparent scoring** — a 0-100 momentum score decomposed into pillars you
  can inspect. It's rule-based technical analysis, not a black box.
- **A live track record** — every pick is stored and later graded against what
  the stock actually did. You can show "top-scored picks vs actual, last 30 days".
- **Adaptive weighting** — the daily job correlates each pillar with realised
  returns *in your own stored data* and nudges the weights toward what's been
  working. That's the honest meaning of "learns from the market".

Market it as an **adaptive research/screening tool with a published track
record**, never as a system that predicts stocks.

---

## Repo structure

```
momentum-scan-pro/
├─ api/
│  ├─ scan.js              # POST /api/scan — fetch, score, snapshot (browser calls this)
│  └─ record-outcomes.js   # daily cron — grade old picks, re-tune weights
├─ lib/
│  ├─ scoring.js           # the scoring engine (the core IP)
│  └─ twelvedata.js        # server-side data client + indicator math
├─ public/
│  └─ index.html           # Phase-1 frontend (screener, real scores)
├─ supabase-schema.sql     # run once in Supabase SQL editor
├─ vercel.json             # cron schedule
├─ .env.example
└─ package.json
```

## Deploy (about 20 minutes)

1. **Supabase** — create a project (London region, same as your other tools).
   Open the SQL editor and run `supabase-schema.sql`. Copy the project URL and
   the **service role** key from Project Settings → API.

2. **Twelve Data** — you already have a free key. For a *commercial* launch you
   will need a paid commercial-tier plan (the free tier prohibits redistributing
   data to paying users). Fine to build on free for now.

3. **GitHub** — push this folder to a new repo
   (`rdfriendripu-rgb/momentum-scan-pro`).

4. **Vercel** — import the repo. Add environment variables (Settings →
   Environment Variables):
   ```
   TWELVEDATA_KEY        = ...
   SUPABASE_URL          = https://xxxx.supabase.co
   SUPABASE_SERVICE_KEY  = ...  (service role — never expose to browser)
   ```
   Deploy. Open the URL, hit **Scan**. You should see live, computed scores and
   "snapshot saved".

5. **Let it run.** The cron in `vercel.json` scans every weekday pre-market and
   grades outcomes after the close. After ~2 weeks of snapshots the re-tune step
   has enough data to start adjusting weights, and the track-record tables fill in.

> **Vercel cron note:** the Hobby plan limits cron frequency/count. The two daily
> jobs here fit, but if you add more you'll want the Pro plan (which you'd be on
> for a commercial product anyway).

## Local dev

```
npm i -g vercel
vercel dev            # reads .env.local
```

---

## Roadmap

- **Phase 1 (this repo)** — secure data, real scoring, daily snapshots, screener UI.
- **Phase 2** — port the rest of the prototype's tabs (news, SEC EDGAR, congress
  via a *paid, licensable* source, alerts) onto the secure backend; add the
  **track-record page** (`score_bucket_performance` view is already there).
- **Phase 3** — news sentiment pillar + AI analysis, both server-side via the
  Anthropic API; wire the `news` pillar into the score.
- **Phase 4** — Supabase Auth, Stripe subscriptions, tiers (free = delayed top 3,
  paid = full scan + alerts + track record), public read-only RLS policies.

## Before you charge for it

Two things worth a proper look, not a footnote:

1. **FCA / regulated advice.** In the UK, giving paying customers specific
   buy/sell recommendations with entry and exit points can constitute regulated
   investment advice. Commercial screeners avoid this by presenting *data,
   scores and levels* framed as research, with clear "not financial advice"
   wording, and letting the user decide. The **output wording** matters legally,
   not just a disclaimer. Worth a short conversation with a solicitor before launch.

2. **Data licensing.** Free tiers of Twelve Data / Finnhub / any congress-data
   provider prohibit commercial redistribution. Budget for commercial data plans
   in your pricing.

Nothing in this app is investment advice.
