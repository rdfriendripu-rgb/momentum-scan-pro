#!/usr/bin/env python3
"""Daily Congress-trades sync for MomentumScan Pro.

Reads the House Clerk's public Periodic Transaction Reports (PTRs) with the
MIT-licensed parser from github.com/Jakeschincariol/day-trader-skill
(vendor/trader_pelosi/ptr.py) and stores every readable trade in Supabase
(congress_filings + congress_trades). Each filing is read once.

ENV: SUPABASE_URL, SUPABASE_SERVICE_KEY
Optional: CONGRESS_DAYS (look-back for filings, default 60),
          CONGRESS_MAX (max new PDFs per run, default 60)
Needs `pdftotext` (poppler-utils) to read PDFs.
"""

import datetime as dt
import json
import os
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vendor", "trader_pelosi"))
import ptr  # noqa: E402

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
DAYS = int(os.environ.get("CONGRESS_DAYS", "60"))
MAX = int(os.environ.get("CONGRESS_MAX", "60"))


def sb(path, method="GET", body=None, prefer=None):
    headers = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + "/rest/v1/" + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        txt = r.read().decode() or "null"
        return json.loads(txt)


def known_doc_ids(since):
    out, start = set(), 0
    while True:
        rows = sb("congress_filings?select=doc_id&filed=gte.%s&order=doc_id&offset=%d&limit=1000" % (since, start))
        out.update(r["doc_id"] for r in rows or [])
        if not rows or len(rows) < 1000:
            return out
        start += 1000


def trade_row(f, r, url):
    return {
        "doc_id": f["doc_id"], "member": f["name"], "district": f.get("district"),
        "owner": ptr.OWNERS.get(r.get("owner") or "", r.get("owner")),
        "ticker": r.get("ticker"), "asset": r.get("asset"), "asset_type": r.get("asset_type"),
        "txn_type": ptr.TXN_TYPES.get(r.get("type"), r.get("type")),
        "trade_date": r.get("date"), "filed": f.get("filed"),
        "amount": r.get("amount"), "amount_low": r.get("amount_low"), "amount_high": r.get("amount_high"),
        "option_info": r.get("option"), "days_to_disclose": r.get("days_to_disclose"),
        "late": r.get("late"), "description": r.get("description"), "url": url,
    }


def main():
    if not URL or not KEY:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
        return 1
    today = dt.date.today()
    since = (today - dt.timedelta(days=DAYS)).isoformat()
    years = {today.year} | ({today.year - 1} if today.month == 1 else set())
    filings = []
    for y in sorted(years):
        filings += ptr.select(ptr.load_index(y), kind="P", since=since)
    seen = known_doc_ids(since)
    todo = [f for f in filings if f["doc_id"] not in seen][:MAX]
    print("PTRs since %s: %d, new: %d (reading %d)" % (since, len(filings), len(filings) - len(seen & {f['doc_id'] for f in filings}), len(todo)))
    pdf_dir = tempfile.mkdtemp(prefix="ptr-")
    added = 0
    for f in todo:
        try:
            _, report = ptr._fetch_and_read(f["doc_id"], f["year"], pdf_dir, filed=f["filed"])
        except ptr.PtrError as e:
            print("skip %s: %s" % (f["doc_id"], e))
            continue
        rows = (report or {}).get("rows") or []
        sb("congress_filings?on_conflict=doc_id", "POST", [{
            "doc_id": f["doc_id"], "member": f["name"], "district": f.get("district"),
            "filed": f.get("filed"), "url": f["url"], "rows_read": len(rows)}],
            prefer="resolution=merge-duplicates,return=minimal")
        if rows:
            uniq = {}
            for r in rows:
                t = trade_row(f, r, f["url"])
                uniq[(t["ticker"], t["asset"], t["txn_type"], t["trade_date"], t["amount"])] = t
            sb("congress_trades?on_conflict=doc_id,ticker,asset,txn_type,trade_date,amount", "POST",
               list(uniq.values()), prefer="resolution=ignore-duplicates,return=minimal")
            added += len(uniq)
        print("%s %s filed %s: %d trades" % (f["doc_id"], f["name"], f["filed"], len(rows)))
    print("done: %d trades added" % added)
    return 0


if __name__ == "__main__":
    sys.exit(main())
