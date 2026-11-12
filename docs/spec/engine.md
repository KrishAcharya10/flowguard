# Engine specification (as built)

Derived from master prompt V3.2 §4.2–4.8. Code: `backend/app/engine/` (imports NumPy only; a test enforces it).
All engine times are **relative hours from t_now = 0**; `services/mapping.py` converts timestamps.

## 1. The single ETA function

`simulate_arrival(inputs: EngineInputs, n_samples, seed) -> EngineResult` in `engine/eta.py` is the only
function that produces arrival samples. Current ETA, risk and every War Room option call it.

For each sample i (N = 500):

```
T_i = planned_wait + dispatch_delay + handling_i + gate_queue_i + repair_wait_i      (= departure)
      + travel along remaining segments, with closure waits and slowdowns (entry-time rule)
travel on segment j = (d_j / v_j) × R_i × S_ij × m_ij
R_i  = exp(σ_route Z − σ_route²/2)      one factor shared by the whole trip
S_ij = exp(σ_seg Z_j − σ_seg²/2)        one factor per segment
m_ij = slowdown multiplier if the vehicle ENTERS segment j inside the slowdown window (overlaps: max)
d_j  = haversine(waypoints) × circuity (1.2)
```

- Handling: only stages not yet completed: `max(0, sampled_stage_duration − elapsed)`.
- Gate queue: Triangular, only while the vehicle has not yet left the plant.
- Transporter factor and stale-data factor scale **σ only** (`sigma_scale`), never the mean.
- Closure: `wait = max(0, end − t_reach)` if `t_reach ≥ start`, else 0. A closure blocks **entry**; a vehicle
  already inside the segment is unaffected (`SegmentInput.already_inside`). Simplification shown in docs.
- Active disruption residual: elapsed e, F = Triangular CDF:
  `u' = F(e) + u(1 − F(e)); duration = F⁻¹(u')`. If F(e) ≥ 0.999: residual = u × 0.5 h.
  A not-yet-started disruption uses the unconditional u.
- Breakdown = `VEHICLE_STOPPAGE` at the current position (repair wait), never a route closure.

### Outputs
Nearest-rank P10/P50/P90; mean; `P(late) = mean(T_i > D)`; expected late hours; baseline; components.
Display: ETA rounded to 5 min, probabilities as whole percent (MC error up to ~2.2 pp at N = 500).

## 2. Common random numbers (`engine/variates.py`)

A `VariateMatrix(seed, n)` returns named columns; each column is a deterministic function of
(seed, column name). Shared names: `route`, `seg:<route>:<waypoint>`, `closure:<id>`, `slowdown:<id>`.
Lot-specific names are prefixed (`lot:URGENT|handling:loading`, `lot:REMAINDER|gate`, …).
So Continue/Reroute/Split see the **same** route factor, the **same** factors on shared segments and the
**same** closure duration, while the two split lots get their own handling/queue draws. Prediction seeds
(`seed_pred = crc32("{global}|pred|{shipment}")`) never equal truth seeds (`…|truth|…`).

## 3. Reason decomposition (explains the MEAN)

```
baseline = t_now + planned_wait + base_handling(remaining) + Σ d_j / v_j
handling deviation = mean(handling) − base_handling
gate queue        = mean(gate_queue)
dispatch delay    = fixed offset (late dispatch or second-vehicle lead)
slowdown          = mean(Σ base_j (m_ij − 1))
closure wait      = mean(closure_wait)
repair wait       = mean(repair_wait)
variability       = mean(T) − baseline − Σ(above)      ← residual, closes the sum exactly
```
The residual may be non-zero (multiplicative interactions); it is ≈ 0 in a deterministic no-disruption test.
"Why did P50 change": the same shipment seed means the same variate matrix, so the P50 difference between
consecutive stored predictions is attributed to the trigger (`trigger_event_id`).

## 4. Stock (`engine/stock.py`)

```
S = t0 + I0 / r            A = T + u (usable arrival)
cover_end = S; stockout = 0
for lots sorted by A:  stockout += max(0, A − cover_end);  cover_end = max(cover_end, A) + q / r
P(stock-out) = mean(stockout > 0)
```
Any number of lots, any arrival order. Stock affects consequence, ranking and alerts; never travel time.

## 5. Risk (`engine/risk.py`)

`index = round(100 (w_late P(late) + w_stock P(stockout)))` (no stock data → `100 P(late)`).
Bands LOW 0–29 / MEDIUM 30–59 / HIGH 60–100; floors MEDIUM if P(late) ≥ 25%, HIGH if P(late) ≥ 50% or
P(stock-out) ≥ 30%. Displayed = max(band, floor). A heuristic index, not a probability.

## 6. War Room (`engine/warroom.py`)

Per option (all on the same seed):
```
Freight_k  = incremental freight (Continue = 0) × freight_scale
SLA_k      = p × Σ_lots (q_lot/Q) × mean(max(0, T_lot − D))     (single lot: p × E[late h])
Stockout_k = s × mean(stockout_hours)                           (never fixed × P(stock-out))
Total_k    = Freight_k + SLA_k + Stockout_k
```
Hard constraints: P(stock-out) ≤ α; for Split P(A_urgent ≤ S) ≥ 1 − α; freight ≤ cap; urgent qty ≥ min;
optional P(late) ≤ β. Infeasible options are never recommended.
Recommendation: cheapest feasible; if Continue is feasible and nothing beats it by
`max(tie_pct × Total_Continue, tie_min_abs)` → NO JUSTIFIED INTERVENTION. Nothing feasible →
NO FEASIBLE OPTION – ESCALATE, least-violating shown for information only.
Stability: 2⁴ = 16 cases of freight, p, s, disruption duration at 0.75/1.25. Cost changes reuse samples;
duration changes rerun the engine with the same variates. STABLE 16/16, SENSITIVE 8–15, otherwise
NO ROBUST RECOMMENDATION. Break-even multipliers are computed from the linear cost terms.

## 7. Eligibility (`services/warroom.py`)

- Reroute: an alternative route must name its primary, entry decision node and rejoin waypoint
  (`routes.alternative_*`); the vehicle's last reported position must be before the entry node.
  Path = primary to entry + alternative + primary from rejoin. Freight = extra km × Rs/km + fixed.
- Split: only PLANNED / LOADING / AT_PLANT_GATE and a SINGLE lot. Urgent lot = max(min priority qty,
  consumption × 4 h) capped at Q; it takes the alternative if a closure is on the current path; both lots
  start after the second-vehicle lead time. Freight = fixed + Rs/km × urgent route km.

## 8. Simulator truth (`backend/app/simulator/`)

Hidden realisations come from `seed_truth` and are re-derived on demand, never stored: loading and gate
durations, per-route travel factors (primary and alternative, per lot), disruption true durations. The clock
advances in ≤ 5-minute ticks, ends disruptions at their true end, posts simulated milestones, and writes an
observed position each tick unless a `TELEMETRY_OUTAGE` is active. The engine and mapping layer never
import the simulator (tested).
