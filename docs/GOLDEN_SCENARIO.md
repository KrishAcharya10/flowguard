# Golden scenarios: inputs and target ranges

Committed before tuning. **Only distribution parameters may be tuned. Target ranges may not be edited.**
Targets are tuning aims for a fictional scenario, not empirical performance.
Measured values: `GOLDEN_MEASURED.md` (generated) and `GOLDEN_BASELINE.md` (frozen).

## Shared inputs

| Input | Value |
| --- | --- |
| Clock start (t₀) | 2026-11-16 00:30 UTC (06:00 IST) |
| Route | R1 Waluj to Pithampur, Plant X → Pithampur, 5 segments, 354 km, base travel 7.9 h |
| Alternative | R1A Dhule Bypass: entry decision node R1-W1 (Chalisgaon Junction), rejoin R1-W4 (Sendhwa Toll Plaza); reroute path 411 km |
| Disruption | FLOOD_R1: closure of segment R1-W2 → R1-W3 (river crossing), duration Triangular(7, 9, 12) h, starts at injection |
| Quantity Q | 24 t |
| Promise D | t₀ + 11 h (17:00 IST) |
| Seed | `seed_pred = crc32("20261116|pred|SHP-PTH-1116-01")` (G2 uses SHP-PTH-1116-02) |

## G1 — flooding + low stock (main demo; expected REROUTE, STABLE)

Inputs: SHP-PTH-1116-01 seeded LOADING (0.8 h in); the driver advances it to AT_PLANT_GATE; flooding is injected
while AT_PLANT_GATE. α = 10%. SLA p = Rs 20,000 per late hour, s = Rs 60,000 per stock-out hour.
Stock: 25 t at 2 t/h → S = t₀ + 12.5 h; u = 0.5 h.

| Target | Range |
| --- | --- |
| Stock relation | S about 1–2 h after D; u ≤ 1 h; S − u ≥ D |
| Before injection | P(late) ≤ 15%, P(stock-out) ≤ 5%, category LOW |
| Continue after injection | P(late) ≥ 70%, P(stock-out) ≥ 30%, HIGH, P50 2–4 h after D |
| Reroute | P(late) ≤ 30%; 2% ≤ P(stock-out) ≤ 8%; freight > 0; Total_Reroute ≤ 0.6 × Total_Continue |
| Split | eligible; freight > Reroute freight |
| Recommendation | REROUTE |
| Stability | STABLE (16/16) |

## G2 — same disruption, high stock cover (expected CONTINUE)

Inputs: SHP-PTH-1116-02 (HDPE-B52), AT_PLANT_GATE, same flood. Stock 120 t at 1.5 t/h (80 h cover). SLA p = Rs 2,500.

| Target | Range |
| --- | --- |
| Continue | P(late) ≥ 50%, P(stock-out) ≤ 5%, feasible |
| Totals | No option beats Continue by more than the tie-break threshold max(2% × Total_Continue, Rs 2,000) |
| Message | "NO JUSTIFIED INTERVENTION – CONTINUE CURRENT PLAN"; "Late is not the same as costly." |
| Stability | Recorded, not asserted |

## G3 — no feasible option

Inputs: G1 inputs, then α = 1% and max incremental freight = Rs 20,000 (below Split's freight).

| Target | Range |
| --- | --- |
| Violations | Continue and Reroute violate α; Split violates the freight cap |
| Result | "NO FEASIBLE OPTION – ESCALATE"; violated constraints listed per option; least-violating option shown as information only (never "Recommended") |
| Alert | CRITICAL alert visible to every coordinator |
| Override | Approving any option requires a reason and writes a `CONSTRAINT OVERRIDE` audit entry |

## Where these are proven

- Phase 0 hand-check (no database): `scripts/phase0_handcheck.py` → "ALL TARGETS COMPATIBLE – GO".
- Real stack: `backend/tests/test_golden.py` (4 tests).
