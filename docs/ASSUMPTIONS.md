# Assumptions register

Every number below is **invented** for the fictional Plant X. None is LYB or Plant X policy or performance.
Editable values live in `backend/app/assumptions.py` and can be changed in the app (Analytics → Assumptions);
the table shows the defaults. Units: hours, km, tonnes, t/h, Rs.

## Engine (ETA)

| Assumption | Default | Why this value |
| --- | --- | --- |
| Monte Carlo samples N | 500 | Fast enough for an interactive War Room (< 100 ms per option); sampling error of a probability ≤ ~2.2 percentage points |
| Route-level variability σ_route | 0.10 | A whole trip runs ±10% (one standard deviation) — traffic/weather affect every segment together |
| Segment variability σ_segment | 0.05 | Smaller, independent per-segment noise |
| Factor formula | exp(σZ − σ²/2) | Mean-one lognormal: adds spread without moving the average |
| Road distance | haversine × 1.2 | Roads are ~20% longer than straight lines (circuity). Distances are computed, never typed in |
| Segment speeds | 38–50 km/h | Loaded bulk trucks on mixed roads |
| Dhule Bypass speed | 42 km/h | **Tuned** (see `GOLDEN_BASELINE.md`): the only parameter tuned to meet G1 targets |
| Loading reference / distribution | 1.0 h; Triangular(0.8, 1.0, 1.5) | Bulk polymer loading |
| Plant-gate queue | Triangular(0.2, 0.5, 1.0) h | Paperwork, weighbridge, gate-out |
| Telemetry Fresh / Stale | ≤ 15 min / ≥ 45 min | Typical GPS ping interval is minutes; 45 min of silence is meaningful |
| Stale widening | σ × (1 + min(age/45 min, 2)) | Up to 3× wider; staleness widens the range, it is not a separate risk term |
| Overdue disruption residual | u × 0.5 h | If a closure outlasts its stated maximum, assume it ends soon |
| Transporter variability factor | Sai Krupa 1.00, Deccan Bulk 1.15, Konkan Express 1.30 | Scales spread only, never the mean |

## Risk and alerts

| Assumption | Default | Why |
| --- | --- | --- |
| Risk weights w_late / w_stock | 0.6 / 0.4 | Lateness matters more often; stock-out matters more when it happens. Must sum to 1 |
| Bands | LOW 0–29, MEDIUM 30–59, HIGH 60–100 | Simple thirds-like split |
| Floors | MEDIUM if P(late) ≥ 25%; HIGH if P(late) ≥ 50% or P(stock-out) ≥ 30% | A coin-flip chance of lateness must never show as Low |
| Alert triggers | category up to MEDIUM/HIGH; P(late) crosses 50%; P(stock-out) crosses 20%; disruption wait ≥ 2 h; high-priority shipment goes Stale | From the spec; fire only on category change or index move ≥ 10, deduplicated |
| Grace period | 0 h | On time means by the promised time |

## War Room

| Assumption | Default | Why |
| --- | --- | --- |
| α = max P(stock-out) | 10% | Customer line stoppage should be rare |
| β = max P(late) | off | Lateness is priced through the SLA cost instead |
| Max incremental freight | off | Set in G3 to show escalation |
| Minimum urgent quantity | 6 t | A part-load smaller than this is not worth a truck |
| Stock-out cost | Rs 60,000 per hour | Incremental cost beyond the SLA penalty (customer line stopped) |
| SLA penalty | per order: Rs 2,500 – 20,000 per late hour | Contract-specific; high-priority orders pay more |
| Reroute fixed cost | Rs 5,000 | Re-planning, permits, driver briefing |
| Route cost | Rs 50–58 per km | Fuel, tolls, driver time |
| Second vehicle | Rs 18,000 fixed, available after 1.5 h | Spot hire of a separate fictional vehicle and driver |
| Split urgent quantity | max(min priority qty, consumption × 4 h), capped at load | Enough to keep the customer running ~4 h |
| Tie-break | max(2% of Continue total, Rs 2,000) | Do not intervene for a negligible modelled saving |
| Stability stress | ±25% on freight, SLA rate, stock-out rate, disruption duration (16 cases) | Typical uncertainty band for planning numbers |

## Stock (customer inventory, fictional)

| Customer / product | Inventory | Consumption | Unloading | Note |
| --- | --- | --- | --- | --- |
| Pithampur / PP-H110 (G1) | 25 t | 2.0 t/h | 0.5 h | Runs out 12.5 h after start: 1.5 h after the promise (S − D = 1.5 h, S − u ≥ D) |
| Pithampur / HDPE-B52 (G2) | 120 t | 1.5 t/h | 0.5 h | 80 h of cover: late is not costly |
| Amravati / FILM-L30 | 60 t | 1.2 t/h | 0.75 h | |
| Satara / PACK-P40 | 18 t | 1.0 t/h | 0.5 h | |
| Others | — | — | — | No stock data: risk uses P(late) only, labelled "Stock data unavailable" |

A real deployment needs customer consent to share coarse stock-cover data.

## Business impact Panel B (illustrative, editable)

| Input | Default |
| --- | --- |
| Annual shipments | 6,000 |
| Delay rate | 18% |
| Mitigable share | 40% |
| Intervention success rate | 70% |
| Avoidable hours per mitigated shipment | 3 h |
| Cost per late hour | Rs 15,000 |
| Average intervention cost | Rs 12,000 |

## Data and simulation

| Assumption | Value | Why |
| --- | --- | --- |
| Simulation start | 16 Nov 2026 06:00 IST (00:30 UTC) | Fixed so the demo is identical every run; nothing depends on the wall clock |
| Global seed | 20261116 | |
| Active shipments | 14 (incl. G1, G2) | Spec: 12–14 |
| History | 160 delivered shipments over 8 weeks, 4 routes, 3 customers, 3 transporters | Spec: ≥ 150 |
| Deliberate patterns | Konkan Express weak on Waluj to Satara; Waluj to Amravati recurring congestion; Pithampur often urgent | So the dashboard has something real to find |
| Unexplained delay | Classed as ROUTE_CONGESTION | So attributed hours always sum to realised delay |
| Planned arrival | Promise minus a buffer (0.25–3 h) | Spec 4.1 |
| Baseline for warning lead time | Without FlowGuard, the customer learns at the breach (lead time 0) | Labelled assumption |
