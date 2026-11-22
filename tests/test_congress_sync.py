"""Tests for the Congress-trades sync (scripts/congress_sync.py).

Fixtures are from github.com/Jakeschincariol/day-trader-skill (MIT):
a real 2026 House index excerpt and a real PTR read with pdftotext -layout.
"""
import os
import sys

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..", "momentum-scan-pro")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "vendor", "trader_pelosi"))

import congress_sync as cs  # noqa: E402
import ptr  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def test_index_selects_only_ptrs_since_date():
    rows = ptr.select(ptr.load_index(2026, offline=os.path.join(FIX, "2026FD.zip")),
                      kind="P", since="2026-10-01")
    assert rows, "expected PTR filings in the fixture index"
    assert all(r["type"] == "P" and r["filed"] >= "2026-10-01" for r in rows)
    assert all(r["url"].endswith(r["doc_id"] + ".pdf") for r in rows)


def test_trade_row_maps_ptr_fields_for_supabase():
    rep = ptr.parse_ptr_text(open(os.path.join(FIX, "ptr-20035590.txt")).read(), filed="2026-10-20")
    assert len(rep["rows"]) == 2
    f = {"doc_id": "20035590", "name": "Hon. Nancy Pelosi", "district": "CA11", "filed": "2026-10-20"}
    t = cs.trade_row(f, rep["rows"][0], "https://example/ptr.pdf")
    assert t["ticker"] == "AMAT"
    assert t["owner"] == "joint"          # JT -> readable owner
    assert t["txn_type"] == "sale"        # S -> readable type
    assert t["trade_date"] == "2026-09-15"
    assert t["amount"] == "$1,001 - $15,000" and t["amount_low"] == 1001 and t["amount_high"] == 15000
    assert t["days_to_disclose"] == 35 and t["late"] is False
    expected = {"doc_id", "member", "district", "owner", "ticker", "asset", "asset_type", "txn_type",
                "trade_date", "filed", "amount", "amount_low", "amount_high", "option_info",
                "days_to_disclose", "late", "description", "url"}
    assert set(t) == expected  # exactly the congress_trades columns the sync writes


def test_main_refuses_without_supabase_env(monkeypatch):
    monkeypatch.setattr(cs, "URL", "")
    monkeypatch.setattr(cs, "KEY", "")
    assert cs.main() == 1
