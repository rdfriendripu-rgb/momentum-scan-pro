# MomentumScan Pro — Roadmap & Proof Gates

**What this document is:** the rulebook that decides when you're allowed to move
from one phase to the next. Each phase ends with a **Proof Gate** — specific,
measurable criteria that must ALL be met before you advance. The gates exist for
one reason: to stop a good week (or a run of confidence) from talking you into
risking money the results haven't earned.

**The one rule that makes the rest work:** *a good week is not evidence. Only the
gate criteria are evidence.* When you feel the urge to skip ahead, write the urge
down in the log at the bottom — don't act on it.

**Two things, kept separate in your head:**
1. *Research/discipline value* — near-certain. This tool makes you systematic and
   honest, whether or not it ever prints money.
2. *Money-making value* — unproven until a gate proves it. Never assume it; make
   it demonstrate it.

*Not financial or legal advice. I'm not a licensed advisor. Thresholds below are
sensible starting points — tighten them, never loosen them.*

---

## The benchmark you must always beat

Before anything else, fix the yardstick: **buy-and-hold your universe (or an index
like the S&P 500) over the same period, after costs.** If the system can't beat
just holding, the entire exercise is negative-value and the correct decision is to
index instead. Every gate below is measured *against this benchmark*, not against
zero.

---

## Phase 0 — Foundation  ✅ (essentially done)

**Built:** live web app (deployed), computed scoring engine, Python model,
walk-forward backtest harness, IG read-only connector, multi-source signals layer.

**Gate 0 — to leave this phase:**
- [ ] App deploys and returns live scores
- [ ] `run_backtest.py` runs on your real universe end-to-end
- [ ] `signals.py NVDA` returns sane data once keys are in

**You are here → moving into Phase 1.**

---

## Phase 1 — Is there ANY edge? (historical backtest)

**Objective:** find out whether the model beats the benchmark on history, after
realistic costs. This is cheap and fast — do it before spending on more data.

**Do:** run the walk-forward on your full universe, twice — once with share costs
(`FUNDING_BPS_PER_DAY=0`) and once with CFD/spread-bet funding on.

**🚦 PROOF GATE 1 — all must pass:**
- [ ] Out-of-sample ROC-AUC ≥ **0.55** (0.50 = coin flip)
- [ ] Top-K strategy beats the equal-weight/benchmark return **after costs**
- [ ] Calibration table: `actual` roughly tracks `predicted` (not wildly off)
- [ ] Edge holds across **at least two separate time windows** — not one lucky stretch
- [ ] Still positive after **CFD funding costs** *if* you intend to spread-bet

**If it fails:** do NOT proceed to anything live. Iterate the model, or accept
there's no edge in this universe/horizon and stop. **Failing here is the process
working — it just saved you real money.**

---

## Phase 2 — Does the edge survive live? (forward paper-trade)

**Objective:** catch overfitting. A backtest can look great and be a mirage;
out-of-sample forward results are the truth serum. **No money in this phase.**

**Do:** run `predict.py score` daily and `predict.py grade` on schedule. Log every
pick. Touch nothing else.

**Minimum duration — BOTH must be satisfied (no early exit):**
- At least **8–12 weeks** of real-time running, AND
- At least **30–40 non-overlapping graded trades** (so the win rate means something)

**🚦 PROOF GATE 2 — all must pass:**
- [ ] Live win rate & average return **roughly consistent with the backtest** (didn't collapse)
- [ ] Forward calibration still holds
- [ ] Beats buy-and-hold / index over the **same** window
- [ ] You logged honestly — no cherry-picking, no restarting the clock after a bad week

**If forward ≪ backtest:** that's overfitting. Back to Phase 1. This is common and
expected — most first models die here, and that's fine.

---

## Phase 3 — Do the extra signals actually help?

**Objective:** decide whether news/insider/WSB earn their place, or are just
decoration.

**Do:** wire the FRESH signals (insider buys, WSB chatter, news sentiment) into the
feature set. Keep congress/13F as display-only context.

**🚦 PROOF GATE 3:**
- [ ] Adding the signals **measurably improves** forward metrics vs your Phase-2 baseline, over a **fresh** window
- [ ] If they don't help → keep them as context panels only. Don't pretend they add edge.

---

## Phase 4 — First real money: semi-auto, tiny, ISA only

**"It suggests, you click."** You get ~90% of the benefit — speed, discipline, no
hesitation — while keeping a human circuit-breaker.

**Preconditions:** Gates 1 and 2 passed (ideally 3 too).

**Rules:**
- **ISA account only** (own the shares, no leverage, gains tax-free in-wrapper)
- **Tiny fixed size** per trade — an amount you'd shrug off losing entirely
- **You place every order manually.** The bot advises; your hand clicks.
- Keep logging every trade, including any time you override the system

**🚦 PROOF GATE 4 — all must pass, over months not weeks:**
- [ ] Real-money results (after **real commissions + slippage**) consistent with paper
- [ ] Slippage isn't quietly killing the edge
- [ ] You followed the system — or logged and measured every override
- [ ] Still beating the benchmark

**Why ISA, not spread betting:** unleveraged means a bad run or a bug can only dent
a position, never blow up the account. Prove it where mistakes aren't fatal.

---

## Phase 5 — Leverage / spread betting  (optional — many should skip)

**Backdrop:** UK brokers are required to disclose that **~70–80% of retail
spread-bet/CFD accounts lose money.** For a multi-day hold, overnight funding eats
returns while leverage magnifies momentum's inevitable drawdowns.

**Preconditions:** everything above passed, funding drag explicitly modelled in the
backtest, and size kept small.

**🚦 PROOF GATE 5:**
- [ ] Edge survives **after** realistic overnight funding, in small size
- [ ] You've sat through at least one real drawdown on the ISA without panicking
- [ ] You genuinely need leverage (most people don't) — written justification

Honestly: this phase is optional. Skipping it forever is a perfectly good outcome.

---

## Phase 6 — Limited auto-execution  (the highest-risk step — most guardrails)

**Objective:** remove the click, never the guardrails. Auto-execution is a
*different risk category*: a bug becomes an instant loss with no emotional brake.

**Preconditions:** a **long** proven track record beating the benchmark after costs,
AND every risk limit below enforced *in code* and tested.

**MANDATORY code-enforced limits before a single auto-trade:**
- [ ] Max position size (both £ and % of account)
- [ ] Max simultaneous open positions
- [ ] **Daily-loss kill-switch** — auto-halt at X% daily drawdown
- [ ] Max trades per day
- [ ] Whitelist of tradeable tickers (nothing off-list, ever)
- [ ] **Dead-man's switch** — if the bot can't verify its state/data, it does *nothing*
- [ ] Manual master kill-switch you can hit from your phone anytime
- [ ] Push alert on every single action

**🚦 PROOF GATE 6:**
- [ ] Run in **shadow / dry-run mode** (logs what it *would* do, places nothing) for a window; confirm it matches your manual decisions and **never** breaches a limit
- [ ] Only then enable live auto, on the **ISA**, with a **tiny fraction** of capital
- [ ] Scale size only with continued proof — never after a hot streak

---

## Red lines (never, regardless of how good things look)

- **Never** auto-execute on leverage without a long record *and* every limit above.
- **Never** disable the kill-switch to "let a good trade run."
- **Never** increase size right after a winning streak — that's peak overconfidence.
- **Never** restart the proof clock to erase a bad stretch. The bad stretch is data.
- **Never** let the fun of building outrun the question of whether the signal is real.

---

## Cross-cutting discipline

- **Data spend ∝ proof.** Upgrade one bottleneck at a time. Right now: Twelve Data
  only. Add Quiver when you want alt-data. Consolidated premium feeds only when
  you're trading real size and reliability is worth paying for.
- **Self-learning ≠ market-solving.** The re-tuning re-calibrates and scores itself
  honestly. Its guardrails (walk-forward, out-of-sample, forward validation) matter
  more than any model cleverness.
- **Fixed risk per trade** once live: decide a max % of account at risk per position
  and never exceed it.
- **Keep the two values separate:** discipline (proven) vs profit (unproven-until-gated).

---

## Gate log (fill this in — it's the record that keeps you honest)

| Gate | Date cleared | Key metric (e.g. AUC, forward win rate, vs benchmark) | Notes |
|------|--------------|-------------------------------------------------------|-------|
| 0    |              |                                                       |       |
| 1    |              |                                                       |       |
| 2    |              |                                                       |       |
| 3    |              |                                                       |       |
| 4    |              |                                                       |       |
| 5    |              |                                                       |       |
| 6    |              |                                                       |       |

## Temptation log (write the urge here instead of acting on it)

| Date | What tempted me to skip a gate | Which gate | Did I stick to the plan? |
|------|--------------------------------|------------|--------------------------|
|      |                                |            |                          |
