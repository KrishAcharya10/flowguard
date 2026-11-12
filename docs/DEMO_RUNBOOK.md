# Demo runbook

Owner: Dev3. Rehearse five times with a stopwatch. Record a backup video of one clean run.

> **Easiest way to present:** coordinator → **Demo guide**. Pick a use case, press **Start** or **Jump to the
> decision point**, and follow the presenter panel. The script below is use case 1 done by hand.
> A real recorded run is in [FLOW.md](../FLOW.md).

## 1. Before the session (reset and verify, ~5 min)

| # | Step | Expected |
| --- | --- | --- |
| 1 | `cd backend` then `.venv\Scripts\python -m uvicorn app.main:app --port 8000 --workers 1` | "Application startup complete" |
| 2 | Open http://127.0.0.1:8000/health | `{"status":"ok","demo_mode":true}` |
| 3 | Tab A: log in as `coordinator`. Control Tower → **Reset demo** | "Demo data reset." |
| 4 | Check the Control Tower | Simulated time **16 Nov, 06:00 IST · paused**; 14 shipments; SHP-G1 "Loading at Plant X", risk **Low** |
| 5 | Tab B (new window): log in as `customer_a` | Order ORD-G1, "Delay risk: Low", original promise 16 Nov 17:00 IST |
| 6 | Tab C (new window): log in as `driver1` | SHP-G1 with button "Confirm: Loaded, waiting at plant gate" |
| 7 | Turn Wi-Fi **off** | Everything still works (no CDN, no tiles by default) |
| 8 | Optional: `cd backend; .venv\Scripts\python -m pytest -q tests/test_golden.py` | 4 passed |

Password for every demo account: `PlantX-demo-2026` (fictional). Log in manually in each tab: each tab keeps its
own session. **Do not advance the clock during the War Room step** (it correctly invalidates open scenarios).

## 2. The 10 minutes

| Time | Who | What |
| --- | --- | --- |
| 0:00–2:00 | Slides | Problem, users, key decision, where AI is / is not used |
| 2:00–6:00 | Live | Script below |
| 6:00–8:00 | Slides | Controls, risks, assumptions, pilot |
| 8:00–10:00 | Q&A | Drill in section 4 |

### Live script (4:00)

| Clock | Tab | Action | Say |
|---|---|---|---|
| 0:00 | A | Control Tower overview | "Tracking tells you where the truck is. FlowGuard tells you whether it matters and what to do." |
| 0:10 | B | Customer: ORD-G1, Low risk, original promise 17:00 | "The customer sees one honest view." |
| 0:20 | C | Driver presses **Confirm: Loaded, waiting at plant gate** | "Drivers update in one tap." |
| 0:30 | A | Refresh; SHP-G1 is at the plant gate | |
| 0:35 | A | Simulation controls → **Flooding – North Corridor river crossing** → Inject | "A river crossing floods." |
| 0:45 | A | SHP-G1 turns **High**, P(late) 100%, P(stock-out) 95% | |
| 0:55 | A | Open SHP-G1 detail | "P50 moved +5.4 hours: flooding event. Reason chips: road closure wait. The customer runs out of stock 1.5 h after the promise." |
| 1:10 | A | **Alerts** drawer: "Suggested action: REROUTE via North Bypass…" → **Open War Room** | "An alert is a warning, not an action." |
| 1:30 | A | **Run scenarios** | "Same simulated conditions for all three options." |
| 1:40 | A | Walk the table | "Continue: 95% stock-out, violates our 10% limit. Split: second truck can't reach in time. Reroute: Rs 8,131 extra freight, P(late) 20%, stock-out 4%. Expected total Rs 12k vs Rs 177k." |
| 2:20 | A | Stability card | "Holds in 16 of 16 stress cases: STABLE." |
| 2:50 | A | **Approve Reroute** | "A human approves. One transaction: route, prediction, customer message, audit." |
| 3:05 | B | Refresh customer | "Original promise beside the updated expected delivery. Rerouting initiated; no costs shown." |
| 3:25 | A | Analytics → Business impact (Panel A), then Audit trail | "Modelled 2.8 late hours avoided. Labelled MODELLED, not achieved." |
| 3:45 | A | Analytics → Performance | "O5: East Corridor congestion; Coastwise weak on South Coastal." |
| 4:00 | | Close | "Predict. Simulate. Deliver." |

Optional extras if time allows: SHP-G2 War Room → "NO JUSTIFIED INTERVENTION: late is not the same as
costly"; set α = 1% and freight cap 20,000 in Assumptions → SHP-G1 → "NO FEASIBLE OPTION – ESCALATE".

## 3. Slides (outline)

1. **Problem and approach** — Plant X customers learn of lateness at the breach. Users: customer, coordinator,
   driver. Key decision: *should we intervene, and how?*
2. **Where AI is used / not used** — Runtime: no generative AI, no trained model. ETA = transparent Monte Carlo.
   Development: Claude Code (declared in `AI_DISCLOSURE.md`).
3. **Responsible controls** — confidence ranges and data-confidence labels; human approval with override
   reasons; version checks; role + ownership checks (404); customer allow-list; append-only audit; limitations.
4. **Impact indicator (MODELLED)** — Panel B: affected = 6,000 × 18% = 1,080; mitigated = 1,080 × 40% = 432;
   interventions = 432 / 0.7 ≈ 617; gross = 432 × 3 h × Rs 15,000 = Rs 1.94 cr; cost = 617 × Rs 12,000 =
   Rs 74 lakh; **net ≈ Rs 1.20 cr per year, illustrative**. Break-even cost per late hour ≈ Rs 5,714.
   Plus warning lead time (hours of notice before the promise). All inputs are assumptions.
5. **Architecture** — `docs/architecture.svg`.
6. **Pilot** — shadow mode on one route for 6 weeks: predict, don't act; compare with actual arrivals;
   calibrate; then enable the War Room for coordinators only.

## 4. Q&A drill

| Question | Answer (owner) |
| --- | --- |
| Where is the AI? | See `AI_DISCLOSURE.md` closing paragraph (Dev3) |
| How is the ETA computed? | 500 simulated trips: remaining handling + gate queue + segment travel × shared route factor × segment factor, closure waits, repair waits. P50 = median; P(late) = share after the promise (Dev3) |
| Why should we trust the probabilities? | We don't claim accuracy; they show uncertainty under stated assumptions. A pilot runs in shadow mode to calibrate them (Dev3) |
| What if the prediction is wrong? | A human approves every action; the reason is visible; the customer only sees "updated expected delivery", never a new commitment; every prediction is stored, so we can measure errors (Dev3) |
| How is the stock-out cost calculated? | Rate × expected stock-out hours from a sequential lot model, never fixed cost × probability (Dev3) |
| Why Reroute and not Split? | The urgent split lot cannot load and travel before stock runs out: P(usable before stock-out) 22% < 90% (Dev3) |
| What does "stable" mean? | Same answer in all 16 combinations of ±25% on freight, SLA rate, stock-out rate, disruption duration (Dev3) |
| How do you protect customer data? | Separate response schemas; tests assert no cost/penalty/other-customer fields; other customers' shipments return 404 (Dev1) |
| What stops a stale decision? | Each case stores shipment, assumptions and clock versions; approval returns 409 if any changed (Dev1) |
| Can a driver fake progress? | Only their assigned shipment, only the next state, not in the future, idempotent, audited (Dev1) |
| Does it scale? | Engine is vectorised NumPy; overview with 80 live shipments ≈ 150–210 ms. A pilot moves to PostgreSQL and a job queue (Dev1) |
| Is the UI accessible? | Icons + text on every status, keyboard focus, labelled controls, loading/empty/error states (Dev2) |
| Why these numbers? | Every one is in `ASSUMPTIONS.md` with a reason; editable in the app (all) |

## 5. Fallbacks

| Problem | Fallback |
| --- | --- |
| Server won't start | `python -m app.seed.reset` then start again; or play the backup video |
| Something looks wrong mid-demo | Reset demo (Tab A), log in again in each tab, restart the script at 0:20 |
| Approve returns "out of date" | Expected if the clock moved; press **Re-run scenarios** then approve (and explain it as a control) |
| Projector resolution | Use browser zoom 90%; the table scrolls horizontally |
