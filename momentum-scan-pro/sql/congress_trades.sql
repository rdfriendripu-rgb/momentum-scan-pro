-- MomentumScan Pro: Congress trades (House PTRs), filled daily by
-- .github/workflows/congress-trades.yml -> scripts/congress_sync.py
-- Run once in the Supabase SQL editor.

create table if not exists congress_filings (
  doc_id      text primary key,
  member      text not null,
  district    text,
  filed       date,
  url         text,
  rows_read   int not null default 0,     -- 0 = scanned/handwritten PDF we could not read
  read_at     timestamptz default now()
);

create table if not exists congress_trades (
  id                bigserial primary key,
  doc_id            text not null references congress_filings(doc_id) on delete cascade,
  member            text not null,
  district          text,
  owner             text,          -- self / spouse / joint / dependent child
  ticker            text,
  asset             text,
  asset_type        text,          -- ST stock, OP option, etc.
  txn_type          text,          -- purchase / sale / partial sale / exchange
  trade_date        date,
  filed             date,
  amount            text,          -- always a range, e.g. "$1,001 - $15,000"
  amount_low        bigint,
  amount_high       bigint,
  option_info       jsonb,
  days_to_disclose  int,
  late              boolean,
  description       text,
  url               text,
  created_at        timestamptz default now(),
  unique (doc_id, ticker, asset, txn_type, trade_date, amount)
);

create index if not exists idx_congress_ticker on congress_trades (ticker);
create index if not exists idx_congress_filed  on congress_trades (filed desc);

alter table congress_filings enable row level security;
alter table congress_trades  enable row level security;
-- No policies: only the service key (GitHub job + Vercel API) reads/writes.
