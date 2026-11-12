# GG.md: Complete project overview of FlowGuard (for an AI assistant)

> **How to use this file.** It describes one finished software project in full. Treat it as ground truth about the
> project. Everything here was checked against the real code and test runs (numbers are measured, not estimated).
> If a user asks you anything about "FlowGuard", "Plant X", "the LYB hackathon project" or "the control tower", answer
> from this file. Where something is *not* built or *not* known, this file says so; do not invent features.
>
> **Repository:** https://github.com/KrishAcharya10/flowguard (public) · **Owner:** KrishAcharya10
> **Everything is fictional.** "Plant X", its customers, transporters, trucks, routes and all money values are invented.

---

## 0. One-paragraph summary

**FlowGuard ("Predict. Simulate. Deliver.")** is a working web application: an *Order-to-Delivery Control Tower* for a
fictional polymer manufacturer, **Plant X**. It tracks bulk-polymer truck shipments from the plant to business
customers, **predicts delays before they happen** (ETA range + probability of being late + probability the customer
runs out of material), **explains why**, warns the right people, and lets a **logistics coordinator compare three
options (Continue / Reroute / Split shipment)** with costs and hard rules before a **human approves**. Three role-based
portals (Coordinator, Driver, Customer) share one backend and update live. It also implements all three bonus features
of the hackathon brief: **truck gate-slot booking**, a **"Where is my order?" chatbot**, and **invoice / proof-of-delivery
upload & download**. It was built for the **LYB Mumbai Hackathon 2026, Round 2, Problem Statement 3**
(Supply Chain and Logistics: Order-to-Delivery Control Tower).

**Key design stance:** there is **no runtime generative AI and no trained ML model**. ETA and risk come from a
*transparent Monte Carlo simulation* with declared assumptions; decisions come from readable deterministic rules; a
human approves every intervention. Generative AI was used only as a *development assistant* and is declared.

---

## 1. Context: the hackathon

| Item | Fact |
| --- | --- |
| Event | LYB Mumbai Hackathon 2026, Round 2 ("Build It. Demo It. Defend It.") |
| Task | Pick **one of four** problem statements; build a working web/mobile prototype; demo live; defend it |
| Chosen | **Problem Statement 3: Order-to-Delivery Control Tower** (others were: circular plastics exchange, SafeSite safety app, smart procure-to-pay) |
| Rules | Fictional data only; team runs its own demo (judges give no inputs); **generative AI allowed but must be declared (undeclared use costs 10 points)**; every member must explain all code/data/design |
| Presentation | 10 min: ~2 problem & approach, ~4 live demo, ~2 defend, ~2 judges' Q&A |
| Scoring (100) | Working prototype **20**, business/user value & impact **15**, then 10 each: problem understanding & user fit, innovation, technical design, feasibility & scalability, responsible AI/security/data; then 5 each: UX & accessibility, presentation & demo, Q&A & team understanding |

### The official requirements for Problem Statement 3 (PDF p.7)
**Context:** Plant X ships polymer in bulk to business customers. An order passes through planning → dispatch →
transport → delivery, yet customers and sales teams often learn an order is late only after it already is.

| ID | Mandatory requirement | Where FlowGuard satisfies it |
| --- | --- | --- |
| **O1** | Separate logins for customer, logistics coordinator, transporter/driver | Three roles, JWT auth, per-role pages and API access |
| **O2** | Track orders and shipments on a map with status milestones | Leaflet map + six-step milestone timeline everywhere |
| **O3** | Predict an ETA and delay risk per shipment and **show the reason** | ETA range, P(late), risk, "reason chips" (hours per cause) |
| **O4** | Alert customer and coordinator on delay risk with a **suggested action** (reroute or split) | Alerts + War Room recommendation |
| **O5** | Dashboard: on-time performance and delay causes **by route and transporter** | Analytics page computed from the database |
| Bonus | Truck slot booking at the plant gate · "Where is my order?" chatbot · invoice and POD upload/download | **All three built** (section 13) |

The team added four differentiators: **D1** single probabilistic ETA engine · **D2** three-option War Room ·
**D3** customer stock cover · **D4** editable assumptions + recommendation stability.

---

## 2. Roles and demo credentials

Three roles only (no fourth operational role). **Password for every account: `PlantX-demo-2026`** (fictional).

| Role | What they do | Accounts |
| --- | --- | --- |
| **Logistics coordinator** (also "admin") | Control tower, War Room, simulation control, new orders, gate slots, documents, analytics | `coordinator`, `coordinator2` |
| **Customer** | See only their own orders, delay explanations, documents, ask the chatbot | `customer_a` (Sharma Mouldings Pvt Ltd), `customer_b` (Vidarbha Flexi Films Pvt Ltd), `customer_c` (Sahyadri Packaging Industries) |
| **Transporter / driver** | Phone-first app: update milestones, gate check-in, proof of delivery, report problems | `driver1`…`driver14` (one per seeded live shipment), `driver15`–`driver17` (spare, one per transporter, used for newly created orders), `relief_tr1`–`relief_tr3` (reserved as the second driver when a shipment is split) |

Useful accounts: `driver1` (SHP-PTH-1116-01, has a gate appointment), `driver11` (SHP-BHW-1116-02 has arrived: proof-of-delivery demo),
`driver14` (SHP-AMV-1116-05 in transit: breakdown demo), `driver15` (free: new orders).

---

## 3. Technology and architecture

| Layer | Choice |
| --- | --- |
| Backend | Python 3.11, **FastAPI 0.162**, SQLAlchemy 2.1, Pydantic 2.14, NumPy 2.4, argon2-cffi (password hashing), PyJWT (HS256) |
| Database | **SQLite** (WAL mode, foreign keys ON, 5 s busy timeout). `create_all` + a seed script. **No Alembic migrations** |
| Frontend | React 18 + Vite + **TypeScript** + Tailwind CSS 3 + Recharts + Leaflet + react-router 6. API types are **generated** from `contracts/openapi.json` |
| Tests | pytest (217), Playwright (15 browser tests + 3 live-site checks) |
| Run | **One Uvicorn worker.** FastAPI serves both the API and the **built** React site (`frontend/dist`) on port 8000 |
| Offline | No CDN, no paid API, no live traffic/weather/GPS. The demo works with Wi-Fi off (map = labelled vector grid; OSM tiles optional) |

Size: ~7,300 lines backend app code, ~2,000 lines tests, ~3,400 lines frontend TypeScript, 68 API endpoints, 21 database tables.

### Layering (very important mental model)
```
Browser (React, one tab per role, JWT in sessionStorage)
   │ JSON over HTTP, polls /api/sync/state every 2.5 s
FastAPI  ── security.py (JWT + Argon2, role + ownership check on EVERY request)
   ├─ api/        routers: public.py (auth, customer, driver), coordinator.py (everything coordinator), extras.py (gate, documents, chat)
   ├─ services/   business logic touching the DB (mapping, predictions, alerts, warroom, analytics, gate, documents, chat, orders, reports, activity…)
   ├─ engine/     PURE maths, NumPy only (eta, stock, risk, warroom). No DB, no web framework
   └─ simulator/  hidden "truth" + simulation clock + optional auto-run  (engine and services NEVER import it)
SQLite (one file)  + private document folder on disk
```

### "Truth versus belief" (a core idea)
To make a demo where "the clock moves trucks", there must be a hidden reality. The **simulator** derives what *really*
happens (loading durations, per-route travel factors, true disruption end times) from a separate seed
(`seed_truth`), re-derived on demand and **never stored**. The **prediction engine** (`seed_pred`) sees only what a
real control tower could observe: recorded milestones, the last **reported** position, active disruptions and declared
distributions. The simulator writes only observable facts (milestones, a reported position, disruption ends). A test
scans imports to enforce that `engine/` and the mapping layer never import the simulator, and that
`seed_pred != seed_truth` for every shipment.

---

## 4. Domain model and definitions

### Shipment milestones (canonical, forward-only, exact names)
```
PLANNED → LOADING → AT_PLANT_GATE → IN_TRANSIT → ARRIVED_AT_CUSTOMER_GATE → DELIVERED
```
- `AT_PLANT_GATE` = loaded, waiting to leave Plant X. `ARRIVED_AT_CUSTOMER_GATE` = reached the customer's receiving gate.
  **Never** use the old aliases `AT_GATE` / `ARRIVED`.
- A split order's original shipment gets a separate terminal **disposition `SPLIT_PARENT`** (not DELIVERED, excluded from
  delivery KPIs); two child lots (`URGENT`, `REMAINDER`) are created under the same order.

### Key definitions
| Term | Meaning |
| --- | --- |
| `promised_at` | Delivery deadline promised to the customer at their receiving gate. **Immutable.** Customer wording: "Original promise" and "Updated expected delivery", **never** "new commitment" |
| `planned_arrival_at` | The operational plan (promise minus a buffer) |
| `arrived_at` | Gate-arrival event. **On-time = arrived_at ≤ promised_at + grace (0)** |
| `delivered_at` | Later proof-of-delivery completion. On-time is judged at gate arrival, **not** at POD |
| Realised delay | `max(0, arrived_at − planned_arrival_at)`; delay-event hours sum to this (tolerance 0.001 h); early arrivals create no delay rows |
| On-time % | Per **order**: every non-parent lot reached the customer gate by the promise. Orders still in transit are excluded; "predicted on-time" is shown separately and never mixed into the denominator |
| Buckets (active lots) | LATE (promise passed), AT_RISK (not late, risk Medium/High), ON_TRACK (not late, Low); they sum to the active total. `ARRIVED_PENDING_POD` and `DELIVERED` are separate |
| Units | hours (durations), km, tonnes, t/h, Rs. Timestamps stored in **UTC**, displayed in **Asia/Kolkata (IST, UTC+5:30)** |
| Versions | `shipment.state_version` (bumps on material events: milestone, disruption, intervention; **not** on clock ticks), `assumptions_version`, `clock_version` (bumps on every clock advance) |

### Business intuition worth remembering
**Late is not the same as costly.** A shipment can be almost certainly late yet the best action is to do nothing,
if the customer has plenty of stock and the penalty is small. FlowGuard models the customer's *stock cover* so it can
tell "late and it matters" from "late but harmless".

---

## 5. The prediction engine (D1)

**One function** produces arrival-time samples: `engine/eta.py::simulate_arrival(inputs, n_samples, seed)`. Current ETA,
risk, and every War Room option call it (a test checks there is exactly one).

For each of N = **500** samples:
```
arrival_i = planned_wait + dispatch_delay + handling_i + gate_queue_i + repair_wait_i      (= departure time)
            + Σ over remaining road segments j of  (d_j / v_j) × R_i × S_ij × m_ij
              + closure waits (entry-time rule)
R_i  = exp(σ_route·Z − σ_route²/2)     one factor for the whole trip       (σ_route = 0.10)
S_ij = exp(σ_seg·Z_j − σ_seg²/2)       one factor per segment              (σ_seg   = 0.05)
m_ij = slowdown multiplier if the truck ENTERS segment j inside a slowdown window (overlaps use max, never sum)
d_j  = haversine(waypoints) × 1.2 circuity (distances are computed, never typed in)
```
- **Mean-one factors** widen the range without shifting the mean. Transporter factor (1.0 / 1.15 / 1.3) and a
  stale-data factor scale **σ only**, never the mean.
- **Handling** only counts stages not yet completed (no double counting). **Gate queue** applies only while still queued.
- **Closure** blocks *entry* to a segment (a truck already inside is unaffected). Residual duration of an *already active*
  closure is sampled conditionally (`u' = F(e) + u(1−F(e))`, inverse triangular CDF) so it can never imply the closure
  already ended; if overdue (F ≥ 0.999) the residual is `u × 0.5 h`.
- **Breakdown** is a `VEHICLE_STOPPAGE` at the current position (repair wait), **not** a route closure.
- **Common random numbers:** one named-column variate matrix per shipment seed is reused by Continue/Reroute/Split, so
  option differences are real, not noise. Split lots get lot-specific columns (`lot:URGENT|…`) plus shared route factors.
- **Outputs:** nearest-rank P10/P50/P90, mean, `P(late) = mean(T_i > promise)`, expected late hours. Displayed ETAs are
  rounded to 5 min, probabilities to whole percent (Monte Carlo error ≤ ~2.2 percentage points at N = 500; the UI says so).
- **Stored, immutable predictions:** each recompute inserts a row (seed, n, p10/p50/p90, p_late, p_stockout, risk, trigger,
  reasons, versions). Recomputed on: milestone, disruption start/end, telemetry outage, intervention applied,
  assumptions change, clock advance, new order. **GET endpoints never run Monte Carlo.**
- This measures uncertainty *under assumed distributions*. It is **not** an empirical-accuracy claim and **not** ML.

### Reason decomposition ("reason chips")
Explains the **mean** arrival versus a deterministic baseline (reference handling + base travel, no queue/disruption):
`handling deviation, gate queue, dispatch delay, slowdown, closure wait, repair wait`, plus a **residual**
"travel variability / interactions" so the chips sum exactly to `mean(T) − baseline`. "Why did P50 change": same seed ⇒
same variates, so the P50 difference between consecutive predictions is attributed to the trigger
(e.g. *"P50 moved +5.4 h: flooding event DSR-001"*).

### Data confidence (stale telemetry)
Age of the last **reported** position: Fresh ≤ 15 min, Aging, Stale ≥ 45 min. If Stale, both σ are multiplied by
`1 + min(age/45min, 2)`. The map always shows the last *reported* position (faded/dashed if stale); a hidden position is
never shown as observed.

### Stock model (D3) and risk index
Customer inventory `I0` at `t0`, consumption `r` t/h, unloading `u` h. Stock runs out at `S = t0 + I0/r`; a lot's usable
arrival is `A = T + u`. **Sequential lot model** (any number of lots, any arrival order):
```
cover_end = S; stockout = 0
for lots sorted by A:  stockout += max(0, A − cover_end);  cover_end = max(cover_end, A) + q/r
P(stock-out) = mean(stockout > 0)
```
If a customer has no stock data: stock terms omitted, risk = P(late) only, labelled "Stock data unavailable".

**Risk index** = `round(100 × (0.6·P(late) + 0.4·P(stockout)))` (editable weights). Bands LOW 0–29, MEDIUM 30–59,
HIGH 60–100. Floors: MEDIUM if P(late) ≥ 25%; HIGH if P(late) ≥ 50% or P(stock-out) ≥ 30%. A ranking score, not a probability.

### Alerts (O4)
Fired when the displayed risk category moves **up** to MEDIUM/HIGH (also: P(late) crosses 50%, P(stock-out) crosses 20%,
disruption wait ≥ threshold, high-priority shipment goes stale); only on a category change or index move ≥ 10;
de-duplicated by a unique `dedupe_key`. **Coordinator** gets the specific suggestion and numbers ("REROUTE via North
Bypass. P(late) falls from 100% to 20% for Rs 8,131 extra freight"). **Customer** gets a plain-language message with
**no costs/penalties/rates** ("Our logistics team is evaluating an alternate route; no action is required from you").
After approval the customer message changes to "Rerouting has been initiated…". An alert is **not** an executed action.

---

## 6. The War Room (D2) and approval lifecycle

Single-shipment decision support (explicitly **not** fleet optimisation).

| Option | Eligible when | Cost model |
| --- | --- | --- |
| **Continue** | always | freight 0 |
| **Reroute** | an alternative route explicitly names its primary route, **entry decision node** and **rejoin waypoint** (never inferred from names), and the truck's last reported position is before the entry node | extra km × route Rs/km + Rs 5,000 fixed |
| **Split** | shipment not yet departed (PLANNED/LOADING/AT_PLANT_GATE), single lot, urgent qty < load | second vehicle Rs 18,000 fixed (+ lead 1.5 h) + route cost × km. Urgent lot = max(min priority qty, consumption × 4 h) capped at load; takes the alternative if a closure is on the path. The remainder keeps the **original truck's own delay**. The second vehicle is a *separate* fictional vehicle and driver (a `relief_*` driver) |

Ineligible options stay visible, greyed, with the reason.

```
Total_k = Freight_k + SLA_k + Stockout_k
SLA_k      = penalty_per_late_hour × Σ_lots (q_lot/Q) × E[max(0, T_lot − promise)]
Stockout_k = stockout_cost_per_hour (Rs 60,000) × E[stockout hours]          (never "fixed × probability")
```
**Hard constraints** (configurable): max P(stock-out) α = 10%; for Split, P(urgent lot usable before stock runs out) ≥ 1 − α;
optional max freight cap; min urgent quantity; optional max P(late) β. **Infeasible options are never recommended.**

**Recommendation:** cheapest *feasible* option, unless it beats Continue by less than `max(2% of Continue's total, Rs 2,000)`
⇒ **"NO JUSTIFIED INTERVENTION – CONTINUE CURRENT PLAN"**. If nothing is feasible ⇒ **"NO FEASIBLE OPTION – ESCALATE"**
(least-violating option shown for information only, never "Recommended", CRITICAL alert to **all** coordinators).

**Stability:** stress freight cost, SLA rate, stock-out rate and disruption duration each at −25% / +25% (**16 full-factorial
cases**; duration changes re-run the engine with the same variates). `STABLE` = same answer in 16/16, `SENSITIVE` = 8–15,
`NO ROBUST RECOMMENDATION` = < 8 or none feasible. Also reports a break-even multiplier.

**Lifecycle:** `AWAITING_APPROVAL → APPROVED → APPLIED → COMPLETED`, or `REJECTED` / `SUPERSEDED`. Each case snapshots
`shipment.state_version`, `assumptions_version` and `clock_version`. **Approve returns HTTP 409** (and supersedes the case)
if any changed ("scenarios are out of date, re-run"). Approve/reject are idempotent. Approving a non-recommended or
infeasible option needs a written reason and logs `CONSTRAINT OVERRIDE`. Applying is **one DB transaction**: route change
or split, event, new prediction, customer + coordinator alerts, audit. Because the clock bumps `clock_version`, the UI
blocks "Run scenarios"/"Approve" while the simulation clock is running (a decision needs a frozen situation).

**Panel A impact** (per approval): modelled late hours avoided and modelled cost difference vs Continue. **Panel B**: an
editable annual illustration (annual shipments × delay rate × mitigable share … = modelled net benefit and break-even).
Everything is labelled **MODELLED – ILLUSTRATIVE SCENARIO, NOT VERIFIED PLANT X OR LYB PERFORMANCE**.

---

## 7. Simulation, clock and live operations

| Feature | Behaviour |
| --- | --- |
| Clock | `simulation_state`: `sim_now`, `speed`, `paused`, `clock_version`, `global_seed`. **Paused by default.** Start = 2026-11-16 00:30 UTC = **06:00 IST**. Business logic never calls the wall clock (a test forbids `datetime.now()`/`time.time()`; only token expiry and the login throttle are exempt) |
| Advance | `POST /api/simulation/clock/advance` runs ≤ 5-min ticks chronologically (disruption ends, milestones, telemetry), then recomputes predictions **once** |
| Auto-run | ONE asyncio task. Start/Pause + speed 1×/5×/15×/30× (simulated minutes per real second; tick every 2 s). **Auto-pause on a new HIGH/CRITICAL alert** (toggle). One audit row per Start/Pause, not per tick |
| Position events | One "vehicle position updated" event per moving truck per 30 simulated minutes (throttled) |
| Disruption presets | FLOODING (closure; R1 river crossing or R2 market town), ROUTE_CONGESTION (slowdown ×1.6), GATE_CONGESTION, SLOW_LOADING, LATE_DISPATCH (departure offset), BREAKDOWN (vehicle stoppage), TELEMETRY_OUTAGE (data-quality event, **not** a delay cause), plus driver-reported ROAD_HAZARD (slowdown ×1.8). Custom durations are supported |
| Live sync | Every open screen polls `GET /api/sync/state` (a hashed change fingerprint) every **2.5 s** and reloads data only when it changes; "Live · updated hh:mm:ss" badge; no duplicates |
| Activity feed | Built from real rows: shipment events, alerts, prediction changes (risk LOW→HIGH, ETA recalculated), audit (approvals, overrides, gate and document events). Each line has a stable id (`ev:`, `al:`, `pr:`, `au:`) |
| New order | Coordinator creates an order → assigned to a transporter, a **free driver**, a vehicle; promise = expected arrival + 2 h buffer (or typed); first prediction + audit |
| Driver reports | Breakdown / road hazard → a real disruption → recompute → alerts. The driver's note stays internal (never shown to customers) |

---

## 8. Seed data (deterministic, fictional)

**Naming (realistic, still fictional).** Real Maharashtra places around Plant X (Waluj MIDC): routes Waluj to Pithampur (R1, bypass R1A "Dhule Bypass"), Waluj to Amravati (R2, alt R2A "Jalna Ring Road"), Waluj to Satara (R3), Waluj to Bhiwandi (R4); waypoints such as Chalisgaon Junction, Tapi River Bridge, Sendhwa Toll Plaza, Jalna Junction, Purna River Bridge, Ahmednagar Junction, Supa Toll Plaza, Nashik Junction, Kasara Ghat. Order and shipment ids are `ORD-<dest>-<MMDD>-<nn>` / `SHP-<dest>-<MMDD>-<nn>` with dest codes PTH, AMV, SAT, BHW (e.g. `SHP-PTH-1116-01` is the golden G1 truck); new orders use the same scheme with the next free number for the IST day; splits append `-U` / `-R`. Vehicles are plates like `MH20 GH 4101`. Drivers have names (driver1 Ramesh Patil, driver3 Imran Shaikh, driver11 Santosh Bhosale; logins unchanged). History rows keep `ORD-H###`.

**Completing a delivery.** At `ARRIVED_AT_CUSTOMER_GATE` the driver card shows a hand-over block (receiver name + photo/signed note, or "Complete delivery without a document"). The coordinator can do the same on the driver's behalf (`POST /api/shipments/{id}/pod-document`, `POST /api/shipments/{id}/complete-delivery`; Documents page and a Control Tower row action). Both paths use `services/shipments.py::record_delivery`/`documents.upload_pod`, audit the actor, and mark the history "recorded by the control tower".

Seed `20261116`; one command reset: `python -m app.seed.reset` (also `POST /api/admin/reset`, only when `DEMO_MODE=true`).

- **3 customers:** CUST-A Sharma Mouldings Pvt Ltd (route R1), CUST-B Vidarbha Flexi Films Pvt Ltd (R2), CUST-C Sahyadri Packaging Industries (R3, R4).
- **3 transporters:** TR-1 Sai Krupa Roadlines (σ×1.0), TR-2 Deccan Bulk Carriers (×1.15), TR-3 Konkan Express Logistics (×1.3).
- **4 routes + 2 alternatives** (generic coordinates): R1 Waluj to Pithampur (354 km; alt **R1A Dhule Bypass**, entry Chalisgaon Junction, rejoin Sendhwa Toll Plaza, 411 km on the reroute, bypass speed 42 km/h), R2 Waluj to Amravati (alt **R2A Jalna Ring Road**), R3 Waluj to Satara, R4 Waluj to Bhiwandi (R3 and R4 have **no** alternative).
- **14 live shipments** in different stages (IDs `SHP-PTH-1116-01`, `SHP-PTH-1116-02`, `SHP-AMV-1116-01` … `SHP-AMV-1116-05`), different priorities, some LATE/at-risk, one with a seeded telemetry outage (SHP-AMV-1116-04 = stale), one already arrived (SHP-BHW-1116-02, awaiting POD).
- **160 historical delivered shipments over 8 weeks** with deliberate patterns: Konkan Express weak on Waluj to Satara, Waluj to Amravati recurring congestion, Pithampur often urgent. Historical shipments are owned by drivers (deterministically) so drivers have history.
- **Customer stock (fictional):** G1's product 25 t at 2 t/h (runs out 1.5 h after the promise); G2's product 120 t (80 h of cover); SHP-BHW-1116-03's product 10 t; others have none ("Stock data unavailable").
- **Gate slots:** hourly, 5 days; seeded bookings (07:00 IST slot is FULL, 13:00 is closed for "Weighbridge calibration").
- **4 seeded invoices** (valid generated PDFs) for ORD-AMV-1116-01, 1007, 1010, 1011.

---

## 9. The golden scenarios (the demo stories; targets were fixed *before* tuning)

Only distribution parameters may be tuned; target ranges are never edited. One parameter was tuned (bypass speed 44→42 km/h) and logged.

| | Situation | Measured result (real API) |
| --- | --- | --- |
| **G1** | SHP-PTH-1116-01 (24 t, promise 17:00 IST, customer stock runs out 18:30) hit by a flood on the river crossing | Before: P(late) 0.6%, LOW. After: Continue P(late) 100%, **P(stock-out) 95%**, HIGH, total **Rs 176,660** (breaks the 10% limit). **Reroute** P(late) 20%, P(stock-out) 4%, freight Rs 8,131, total **Rs 12,095** ⇒ **RECOMMENDED REROUTE**, **STABLE 16/16**. Split Rs 142,551 (stock-out 76%, infeasible). Modelled benefit ≈ 2.8 late hours, Rs 164,564 |
| **G2** | Same flood for SHP-PTH-1116-02 (customer has 80 h of stock, low penalty) | Continue Rs 7,175 beats Reroute Rs 8,564 ⇒ **NO JUSTIFIED INTERVENTION** ("late is not the same as costly"); stability SENSITIVE 10/16 |
| **G3** | G1 with α = 1% and a Rs 20,000 freight cap | Every option violates a rule ⇒ **NO FEASIBLE OPTION – ESCALATE**; least-violating (Reroute) is info only; CRITICAL alert to all coordinators; any approval needs a reason ⇒ `CONSTRAINT OVERRIDE` |
| Split use case | SHP-BHW-1116-03 (not departed, no alternative road) after a 4 h late dispatch | Continue Rs 153,897 (stock-out 100%); Reroute ineligible; **Split** Rs 34,847 (6 t urgent on a second truck, stock-out 4%) ⇒ RECOMMENDED SPLIT, STABLE 16/16 |

---

## 10. Data model (21 tables)

`users`, `customers`, `transporters`, `routes`, `route_waypoints`, `orders` (immutable `promised_at`, SLA rate, priority),
`shipments` (state, disposition, `state_version`, last reported position/progress, parent link, lot type, driver, vehicle),
`shipment_events`, `delay_events`, `disruptions`, `predictions` (immutable), `customer_inventory`, `alerts` (unique
`dedupe_key`), `interventions` + `intervention_scenarios`, `audit_events` (append-only), `simulation_state`,
`business_assumptions` (JSON + version), **`gate_slots`**, **`gate_bookings`** (partial unique index: one ACTIVE booking per
shipment), **`documents`**. All have PKs/FKs/CHECK constraints and timestamps. Generated reference: `docs/DB_REFERENCE.md`.

---

## 11. API (68 endpoints; Pydantic is the single source; `contracts/openapi.json` is generated and tested for staleness)

| Group | Endpoints (all under `/api`) |
| --- | --- |
| Auth | `POST /auth/login`, `GET /auth/me` |
| Customer | `GET /customer/me/orders`, `/shipments`, `/shipments/{id}`, `/alerts`, `/history`, `/documents`; `POST /customer/me/alerts/{id}/acknowledge`; `POST /customer/me/chat` |
| Driver | `GET /transporter/me/shipments`, `/history`, `/gate`; `POST /transporter/shipments/{id}/milestones`, `/pod`, `/pod-document`, `/report`; `POST /transporter/gate/bookings/{id}/check-in` |
| Control tower | `GET /control-tower/overview`, `/map-data`, `/activity`, `/sync/state`, `/reference-data` |
| Orders / shipments | `POST /orders`, `GET /orders/{id}`, `GET /shipments`, `/shipments/{id}`, `/events`, `/prediction?history=true`, `POST /shipments/{id}/recalculate` |
| Simulation | `GET /simulation/clock`, `POST /simulation/clock/advance`, `POST /simulation/clock/control`, `GET/POST /simulations/disruptions`, `POST /simulations/disruptions/{id}/end` |
| War Room | `POST/GET /shipments/{id}/scenarios`, `GET /interventions`, `POST /interventions/{id}/approve`, `/reject` |
| Alerts / audit | `GET /alerts`, `POST /alerts/{id}/acknowledge`, `GET /audit-events` |
| Analytics | `GET /analytics/overview`, `/delay-causes`, `/routes`, `/transporters`, `/business-impact` |
| Assumptions | `GET/PUT /assumptions` (bumps version, recalculates, supersedes open cases, audits) |
| Gate | `GET /gate/overview`, `/gate/summary`, `/gate/bookings`; `POST /gate/bookings`, `/{id}/reschedule`, `/{id}/cancel`, `/{id}/complete`; `PUT /gate/slots/{id}` |
| Documents | `GET /documents/overview`, `/orders/{id}/documents`, `/documents/{id}/download`; `POST /orders/{id}/invoice`, `/documents/{id}/verify` |
| Demo/admin | `GET /demo/use-cases`, `POST /demo/use-cases/{code}/setup`, `POST /admin/reset`, `GET /health` |

Conventions: 401 not logged in · 403 wrong role · **404 for someone else's resource (never 403, so existence never leaks)** ·
409 conflict (invalid transition, stale scenarios, full slot…) · 422 validation · 413 file too big · 415 bad file type · 429 login throttle.
Note: this FastAPI version keeps included routers nested (`_IncludedRouter`); the access matrix is derived from the OpenAPI schema / `original_router`.

---

## 12. Security, privacy and responsible-AI controls

- **Auth:** Argon2 hashes, JWT HS256 60 min, secret from env (random per process in demo mode; required otherwise). Role and active flag **re-read from the DB on every request**. Login throttle 5 failures/min per username+IP. Token in `sessionStorage` (one login per tab; XSS trade-off documented).
- **Access:** one central dependency checks role; ownership checks return 404. A parameterised test covers every endpoint × (anonymous + 3 roles).
- **Customer privacy:** customers get separate **allow-list schemas** (no freight, penalties, rates, risk weights, option costs, transporter details, other customers). A test walks every key of every customer response; chat text is also checked.
- **Human in the loop:** nothing changes a shipment until a coordinator approves; overrides need a reason; approval is rejected if the situation changed.
- **Honesty labels:** every assumption-based money figure is labelled MODELLED; customers see "an estimate, not a guarantee"; map caption "Illustrative routes. Positions are simulated."
- **Audit:** append-only log (actor, role, action, entity, before/after, simulated time, wall time).
- **Generative AI:** none at runtime. Development used Claude Code (models Claude Fable 5.2, Opus 5.5, Sonnet 5.5); declared in `docs/AI_DISCLOSURE.md` (the team must still add any other tools, e.g. for slides/prompt drafting, and sign off).

---

## 13. The three bonus features

### 13.1 Truck slot booking at the Plant X gate
- **Slots:** hourly, a 5-day window around the *simulated* today (IST), default capacity **3** (assumption `gate_slot_capacity`, editable per slot). States: **OPEN, FULL, OVERBOOKED** (capacity lowered below bookings), **UNAVAILABLE** (closed, e.g. maintenance), **PAST**.
- **Booking lifecycle (separate from the shipment):** `BOOKED → CHECKED_IN → COMPLETED`, plus `CANCELLED` and `MISSED`.
- **Rules:** no booking beyond capacity; no second *active* booking per shipment (also enforced by a partial unique index); no past/closed slots; shipment must not have left the plant; transporter must match the shipment; driver must belong to that transporter. **Reschedule** releases the old place and takes the new one atomically; **cancel** releases capacity; all under one in-process lock with the commit inside it (two simultaneous requests cannot both take the last place; tested with threads).
- **Driver:** sees the appointment, gate name/instructions (*Plant X Main Gate, Gate 2, weighbridge lane B*), status, and a **Check in** button that opens **60 simulated minutes before** the slot.
- **Automatic:** departing Plant X completes the booking; an unused BOOKED slot whose time passed becomes **MISSED** at the next clock advance (capacity released).
- **Time:** only the **simulation clock** (displayed in IST) is used, never the wall clock. All changes are audited and appear in the activity feed.

### 13.2 "Where is my order?" chatbot (customer portal, bottom-right button)
- **Deterministic and read-only, no language model.** Keyword rules classify the question into an intent; the answer is assembled from the same customer-safe objects the portal uses, so it cannot invent a position/ETA and cannot see other customers' data.
- **Intents:** WHERE, STATUS, ETA, DISPATCH, DELAY, PROMISE, UPDATED_ETA, GATE, POD, INVOICE, HELLO/HELP/UNKNOWN, and **COMMERCIAL** (refuses costs, penalties, transporter details, other customers).
- **Answers include:** current status; latest reported position as "near <route point>, about N% of the route" **with the report timestamp**; ETA range ("most likely between … and …, an estimate not a guarantee"); original promise; updated expected delivery; delay explanation plus a **next step**; links to the order and to downloadable documents.
- **Isolation:** asking for another customer's order returns exactly the same "I could not find an order … on your account" as a non-existent id. Tested for read-only behaviour (no DB rows change).
- **UI:** floating launcher, message bubbles with timestamps (user: local time; assistant: "Data as of <simulated time>"), typing indicator, suggested-question chips, "Ask about <order>" selector.

### 13.3 Invoices and proof of delivery
| Who | Can |
| --- | --- |
| Coordinator | Upload an invoice; **replace** it with a new **audited version** (reason required); download; see POD status; download and **verify** a POD (checkbox confirming it belongs to the right shipment) |
| Driver | After reaching the customer gate: recipient name + signed note or photo ⇒ completes the delivery (delivered time = **simulation clock**); can replace the document; can still record delivery *without* a document (shown as "Delivered · no document") |
| Customer | See and download only their **own current** invoice and POD; availability shown on each order; notified when one arrives |

**Document security:** PDF/JPG/JPEG/PNG only; type decided from **file content (magic bytes)**, extension must match; **10 MB** limit (`FLOWGUARD_MAX_UPLOAD_MB`) enforced while streaming; display names sanitised, stored names are random hex (no path traversal); files in **private** storage (`backend/storage/documents`), never static; metadata in the `documents` table (sha256, size, version, status); **every download goes through an ownership-checked endpoint** (wrong owner ⇒ 404) and is audited; uploads/replacements/verifications audited. Uploads are sent as the **raw request body** with metadata in the query string (no multipart dependency). Sample files: `docs/demo_files/`.

---

## 14. Frontend

Seven original views + new pages. Navy/white/slate palette with status colours; **never colour alone** (icon + text on every status); loading, empty, error (with retry) and stale states everywhere; keyboard focus ring, labelled controls.

| Route | Role | Content |
| --- | --- | --- |
| `/login` | all | Role cards, manual password entry |
| `/tower` | coordinator | **Simulation control** (start/pause/speed/advance/reset), 6 KPI cards (active orders, active shipments, on-time %, delayed, high-risk, avg predicted delay), gate-slots-today card, live map, live activity feed, open alerts, disruption injector (custom durations) + active disruptions, active shipments table (filters, row click opens a detail panel), interventions & approvals, **New order** dialog |
| `/shipments/:id` | coordinator | Milestones, ETA intelligence, reason chips, prediction history chart, stock cover, events, gate appointment, **Documents** panel |
| `/shipments/:id/war-room` | coordinator | Recommendation banner, 3-option comparison table, violations, approve/override/reject, stability card (16 cases), clock-running guard |
| `/analytics` | coordinator | Tabs: Performance (O5 charts), Business impact (Panel A+B), Intervention history, Assumptions (editable), Audit trail, Responsible AI |
| `/gate` | coordinator | Day tabs, KPI row, hourly schedule with capacity bars and statuses, book / reschedule / cancel / edit slot, upcoming + history lists |
| `/documents` | coordinator | Orders table with invoice/POD status; per-order panel to upload/replace/verify/download |
| `/demo` | coordinator | **Demo guide**: 8 use cases, one-click setup, floating presenter panel |
| `/customer` | customer | Hero, summary cards, orders list/detail (promise vs updated delivery, range, progress, delay explanation, timeline, map, POD status, documents), tabs: Active, History, Documents, Updates; **chat widget** |
| `/driver` | driver | Mobile-first: gate appointment + check-in, progress, milestone list, big "Confirm: <next milestone>" button, proof-of-delivery upload, report breakdown/hazard, History tab |

Engineering notes: types generated by `openapi-typescript`; one `useApi` hook that keeps old data if the JSON is unchanged (no flicker/map redraw); a global `refreshAll()`; a 401 is confirmed for ~5 s before logging out (so a data reset never logs anyone out); a build timestamp in the footer shows which build you are viewing; Leaflet uses vector layers only (no default marker images), offline labelled grid by default, OSM tiles optional and auto-removed after 3 tile errors.

---

**Visual redesign and map (latest).** Design tokens in `tailwind.config.js` / `src/index.css` (navy, slate, white, restrained teal; one button/card/table style; shared `PageHeader`). The Control Tower is map-first: compact simulation toolbar, one KPI strip, a large map (`components/FleetMap.tsx` over `components/MapView.tsx`) with a sidebar (high-risk shipments, alerts, gate summary, live activity), then the shipment table, disruption management and interventions. Map: OpenStreetMap tiles by default when online (attribution always shown; no key), automatic fallback to a locally drawn "Illustrative logistics network - not to scale" when tiles fail or the browser is offline, a Map/Network switch, retry, custom truck markers (status colour + glyph + freshness dot, grey dashed ring when stale), pixel-distance clustering with fan-out, label decluttering, primary routes solid, alternatives dashed, an approved reroute drawn as the solid "active reroute" with the bypassed section dimmed, red disruption overlays, a legend, zoom / fit / centre-on-plant / centre-on-selected / full-screen, filters (status, risk, transporter), shipment search and a vehicle detail panel. Layers are rebuilt only when their own data changes; the view is fitted once per `fitKey`, never reset by the 2.5 s sync; `ResizeObserver` calls `invalidateSize`. The War Room shows three scenario cards with a stability meter and an approval/audit panel. The only external call anywhere is the optional map tiles (the e2e suite blocks them and proves everything still works).

## 15. The Demo guide: 8 use cases (in-app, coordinator → "Demo guide")

Each has a story, requirements it proves, windows to open, steps, and **Start from the beginning** or **Jump to the decision point** (setup done through the real services; audited). A floating presenter panel shows the NEXT step on every page.

1. **Flood + customer about to run out → Reroute** (main story, proves O1–O5, D1–D4)
2. **Same flood, plenty of stock → do nothing** ("late is not costly")
3. **Every option breaks a rule → escalate / human override**
4. **Truck late at the plant, no alternative road → Split**
5. **Truck breaks down** (vehicle stoppage ≠ road closure)
6. **Lost GPS signal** (stale data widens the range, alert, no invented position)
7. **Watch the day unfold** (clock advance, arrivals, POD, KPIs)
8. **Dashboard insights + privacy tour**

`FLOW.md` contains a click-by-click recorded run of two of these with real numbers and screenshots.

---

## 16. Testing and evidence (all run and passing at time of writing)

| Suite | Count | Covers |
| --- | --- | --- |
| Backend pytest | **217** | Engine metamorphic/unit tests (monotonicity, ordering, determinism across processes, chips sum, residual closure), hand-calculated stock examples, golden G1–G3 through the real stack, role × endpoint × ownership matrix, customer key-absence, approval lifecycle and 409 rules, split rules, simulator, analytics/KPI correctness, 80-shipment performance (overview ≈ 150–210 ms < 300 ms), contract staleness, live ops (orders, driver reports, activity, sync stamp, auto-run, auto-pause), **gate booking rules/concurrency**, **document validation/security/versioning/isolation**, **chatbot intents/isolation/read-only**, demo-guide setups, architecture rules (no wall clock, engine imports) |
| Playwright browser | **12** | Full cross-role vertical slice; **order created → assigned → driver loads → departs → disruption → alert → War Room → approve → customer notified → simulation runs → position events → arrival → proof-of-delivery upload → customer history**; driver breakdown report; demo-guide jump/start; **gate booking (book, reschedule, driver check-in, overbooking)**; **chatbot**; **invoice + POD upload/replace/verify/download with other-customer refusals**; health sweep (no console errors/failed API calls for any role/page); mobile no-horizontal-scroll. The e2e run also asserts **zero requests leave localhost** |
| Live-site check | 3 | Read-only check of the running site for all three roles (`playwright.live.config.ts`); works on any data state |
| Phase 0 hand-check | 29 checks | G1/G2/G3 targets are mutually compatible before any tuning |

Isolation notes: tests use a temp DB and a temp document folder; e2e runs on port 8010 with `e2e.db` and `storage-e2e`. Scripts that reset data must never share the live server's document folder (set `FLOWGUARD_DOC_DIR`).

---

## 17. Repository map

```
LYB/
├─ README.md  FLOW.md  GG.md  CLAUDE.md  PROGRESS.md  start-flowguard.cmd  .env.example  .gitignore  .gitattributes
├─ backend/
│  ├─ app/  main.py  config.py  db.py  models.py  schemas.py  security.py  assumptions.py  seeds.py
│  │  ├─ engine/     contracts.py eta.py variates.py stock.py risk.py warroom.py geo.py     (pure maths)
│  │  ├─ services/   mapping predictions alerts warroom analytics shipments disruptions orders reports activity
│  │  │              gate documents docgen chat views core paths settings demo runtime
│  │  ├─ simulator/  clock.py runner.py truth.py
│  │  ├─ api/        public.py coordinator.py extras.py
│  │  └─ seed/       network.py reset.py
│  ├─ tests/         conftest + 8 test modules       requirements.lock.txt (pinned)
├─ frontend/  src/{pages,components,lib,api}  e2e/ (5 specs)  e2e-live/  playwright*.config.ts  vite.config.ts
├─ contracts/  openapi.json (generated)  fixtures/ (real responses)
├─ scripts/    phase0_handcheck.py  export_openapi.py  gen_reference_docs.py  record_flow.py  make_sample_files.py  render_diagram.mjs
└─ docs/       source/ (official PDF + extracted requirements)  spec/ (engine, api, ui, qa)  walkthroughs/  screenshots/  demo_files/
               ARCHITECTURE  ASSUMPTIONS  TRACEABILITY  GOLDEN_*  KNOWN_LIMITATIONS  AI_DISCLOSURE  DEMO_RUNBOOK  FINAL_AUDIT
               DEFENCE_BRIEF_DEV1/2/3  API_ACCESS_MATRIX  DB_REFERENCE  architecture.svg
```

---

## 18. How to run (Windows)

```
start-flowguard.cmd            # builds the website, then starts the server on http://127.0.0.1:8000   (add "reset" to rebuild demo data)
```
By hand: `cd backend` → `.venv\Scripts\python -m uvicorn app.main:app --port 8000 --workers 1`; the website must be built first
(`cd frontend && npm install && npm run build`). Backend tests: `cd backend && .venv\Scripts\python -m pytest -q`.
Browser tests: `cd frontend && npx playwright test` (first time `npx playwright install chromium`). Env vars (`.env.example`):
`DEMO_MODE`, `FLOWGUARD_DB`, `FLOWGUARD_GLOBAL_SEED`, `FLOWGUARD_JWT_SECRET`, `FLOWGUARD_DEMO_PASSWORD`, `FLOWGUARD_DOC_DIR`, `FLOWGUARD_MAX_UPLOAD_MB`.

**Important operational caveat (the #1 cause of "my change doesn't show"):** the server shows the **built** site
(`frontend/dist`) and Python does **not** auto-reload. After changing code: rebuild the frontend and **restart** the server.
`index.html` is served with `no-cache`; hashed assets are `immutable`.

---

## 19. Hard rules the codebase follows (do not break these when modifying)

1. No `datetime.now()` / `time.time()` in business logic; time comes from `simulation_state` (token expiry and the login throttle are the only exceptions). Never Python `hash()`; seeds use `zlib.crc32`.
2. `engine/` imports NumPy only; `engine/` and the mapping layer **never import `simulator/`**; exactly one ETA function.
3. Pydantic schemas are the API source of truth; regenerate `contracts/openapi.json` (`scripts/export_openapi.py`) then `npm run types`.
4. Customer endpoints use separate allow-list schemas; never add costs, penalties, rates or weights.
5. Canonical states only; `promised_at` immutable; customer wording "Updated expected delivery".
6. Infeasible options are never recommended; overrides need a reason and a `CONSTRAINT OVERRIDE` audit row; GET endpoints never run Monte Carlo.
7. Golden target ranges are never edited (only distribution parameters, logged in `docs/GOLDEN_BASELINE.md`).
8. Every modelled money figure is labelled MODELLED; fictional data only; no paid API/secret/CDN/live external service in the demo path.
9. Never claim a test passed without running it; declare any new AI use in `docs/AI_DISCLOSURE.md`.

---

## 20. Known limitations (honest list)

- All distributions/costs are **assumptions**; probabilities show uncertainty *under those assumptions*, not proven accuracy. A real pilot would run in **shadow mode** first and calibrate.
- Simplified road rules (closure blocks entry only; slowdown by entry time); single-shipment decisions (no fleet optimisation); a fixed 1.5 h second-vehicle lead time.
- SQLite + one worker; live updates are polling (2.5 s); the auto-run clock stores one prediction set per tick; gate rules rely on an in-process lock (several servers would need DB-level locks); routes are illustrative polylines on a grid.
- The chatbot is keyword-based ("I'm not sure" for unusual wording); documents are on local disk without antivirus or encryption at rest; POD document is optional; POD "verification" is a human confirmation.
- Token in `sessionStorage` (XSS trade-off); no HTTPS in the local demo; the demo password is shared and fictional.
- Not built: alert escalation timers, an offline driver queue, QR/OTP proof of delivery and carbon metrics (optional "X"/"E" ideas from the build specification). Driver-reported hazards, custom disruption durations and the auto-running clock **were** built.
- The design-phase approval stop required by the master prompt was skipped at the user's instruction ("start now and complete"); Phase 0 documents exist for review.
- Not yet done by humans: each developer must read the walkthroughs and sign the AI disclosure, build slides, rehearse, record a backup video.

---

## 21. Process history (so you can explain how it was built)

Specified by a long master prompt (**V3.2**) that defined the official requirements, engine maths, contracts, security and
acceptance gates. Built by **Claude Code** in one integrated session: Phase 0 (requirements extract, assumptions, golden
scenarios, contracts, hand-check) → backend (models, seed, auth, engine, services, API) → frontend → tests → docs →
**Demo guide** (8 use cases) → **live operations + portal redesign** (live sync, simulation control, new orders, driver
reports, activity feed) → **three bonus features**. Bugs found and fixed along the way include: a stale server/build serving old
code; live polling logging users out during a data reset (fixed with a confirm-401-for-5 s rule); a feed window filled by
historical events; a split remainder wrongly leaving at time 0; a generated access matrix that missed nested routers; and
scripts that could have deleted the live server's document folder (now isolated).

---

## 22. Quick answers to likely questions

| Question | Answer |
| --- | --- |
| "Where is the AI?" | No generative AI or ML at runtime. ETA = transparent Monte Carlo over assumed distributions (there is no real telemetry history to train on; training on self-generated data would be circular). Decisions = readable rules. AI helped *write* the code and is declared |
| "How is the ETA computed?" | 500 simulated trips: remaining handling + gate queue + Σ(segment km ÷ speed × shared trip factor × segment factor × slowdown) + closure/repair waits. P50 = median; P(late) = share after the promise |
| "Why recommend Reroute in G1?" | Continue breaks the 10% stock-out limit (95%); Split's second truck cannot arrive before stock runs out (22% < 90%); Reroute costs Rs 8,131 extra freight, cuts P(late) 100%→20% and stock-out 95%→4%; expected total Rs 12,095 vs Rs 176,660; holds in 16/16 stress cases |
| "Why 'no intervention' in G2?" | Customer has 80 h of stock and a small penalty: rerouting (Rs 8,564) costs more than the lateness (Rs 7,175) |
| "How do you protect customer data?" | Separate allow-list response schemas, 404 for others' records, key-absence tests, chatbot built only from customer-safe objects, private document storage with ownership-checked, audited downloads |
| "What stops an out-of-date approval?" | Each case stores shipment/assumptions/clock versions; mismatch ⇒ 409 and re-run; UI blocks approval while the clock runs |
| "What's the measurable impact?" | Panel A: modelled late hours avoided and cost difference per approval (e.g. ≈ 2.8 h, Rs 164,564 in G1). Panel B: editable annual illustration (6,000 shipments × 18% delayed × 40% mitigable … ≈ Rs 1.2 crore net/yr, **illustrative, MODELLED**). Warning lead time is also reported |
| "Does it scale?" | Vectorised NumPy; overview with 80 live shipments ≈ 150–210 ms. A pilot: PostgreSQL, job queue, SSE/WebSockets |
| "What would a pilot look like?" | Shadow mode on one route for ~6 weeks (predict, don't act), compare with actual arrivals, calibrate σ and durations, then enable the War Room for coordinators only |
