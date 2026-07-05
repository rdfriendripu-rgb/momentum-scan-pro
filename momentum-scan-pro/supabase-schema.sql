-- ════════════════════════════════════════════════════════════════
-- MomentumScan Pro — Supabase schema
-- Run this in the Supabase SQL editor before first deploy.
-- ════════════════════════════════════════════════════════════════

-- Every day's scored scan. One row per (date, ticker).
-- outcome_return / outcome_date are filled in later by the learning
-- loop once the pick has had time to play out — that's the track record.
create table if not exists daily_snapshots (
  id                bigserial primary key,
  snapshot_date     date not null,
  ticker            text not null,
  price             numeric,
  change_pct        numeric,
  score             int,
  pillar_trend      int,
  pillar_momentum   int,
  pillar_volume     int,
  pillar_position   int,
  pillar_news       int,
  signal            text,
  rsi               numeric,
  entry             numeric,
  target            numeric,
  stop              numeric,
  weights_version   text,
  outcome_return    numeric,   -- filled by record-outcomes.js after HORIZON_DAYS
  outcome_date      date,
  created_at        timestamptz default now(),
  unique (snapshot_date, ticker)
);

create index if not exists idx_snap_date   on daily_snapshots (snapshot_date);
create index if not exists idx_snap_ticker on daily_snapshots (ticker);
create index if not exists idx_snap_ungraded on daily_snapshots (snapshot_date)
  where outcome_return is null;

-- Learned pillar weights written by the re-tune step. api/scan.js reads
-- the newest row; if none exist it uses the defaults in scoring.js.
create table if not exists model_weights (
  id           bigserial primary key,
  version      text not null,
  weights      jsonb not null,
  sample_size  int,
  created_at   timestamptz default now()
);

-- Optional convenience view: rolling 30-day hit rate by score bucket.
-- This is what powers a "does the score actually work?" panel.
create or replace view score_bucket_performance as
select
  case
    when score >= 80 then '80-100'
    when score >= 70 then '70-79'
    when score >= 60 then '60-69'
    when score >= 50 then '50-59'
    else '<50'
  end                                              as bucket,
  count(*)                                          as picks,
  round(avg(outcome_return)::numeric, 2)            as avg_return,
  round(100.0 * avg((outcome_return > 0)::int), 1)  as win_rate_pct
from daily_snapshots
where outcome_return is not null
  and snapshot_date >= current_date - interval '30 days'
group by 1
order by 1 desc;

-- ── Row Level Security note ──────────────────────────────────────
-- The serverless functions use the SERVICE ROLE key, which bypasses
-- RLS. Do NOT expose that key to the browser. When you add the public
-- read-only frontend (Phase 2), create a separate ANON policy that
-- only allows SELECT on the columns you want customers to see, e.g.:
--
--   alter table daily_snapshots enable row level security;
--   create policy read_public on daily_snapshots
--     for select using (true);
--
-- and gate premium columns/rows behind your auth + subscription check.
