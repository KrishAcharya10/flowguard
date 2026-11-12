# Golden baseline (frozen)

Frozen after tuning on 2026-11-12. Environment: Windows 11, Python 3.11, NumPy 2.4.6
(`backend/requirements.lock.txt`). Deterministic comparisons use rounded values on this lockfile.

## Change log

| # | Parameter | From | To | Reason |
| --- | --- | --- | --- | --- |
| 1 | North Bypass (R1A) segment speed | 44 km/h | 42 km/h | At 44 km/h Reroute P(stock-out) measured 1.8%, below the G1 target range 2–8%. Speeds 43/42/41 all met every target; 42 sits mid-range (3.8%). No target range was edited. |

No other parameter was tuned.

## Frozen measurements (real API, seeded database)

### G1
| Measure | Target | Measured |
| --- | --- | --- |
| Before injection P(late) / P(stock-out) / category | ≤ 15% / ≤ 5% / LOW | 0.6% / 0.0% / LOW |
| Continue P(late) | ≥ 70% | 100.0% |
| Continue P(stock-out) | ≥ 30% | 95.4% |
| Continue category | HIGH | HIGH (index 98) |
| Continue P50 − D | 2–4 h | 2.9 h |
| Reroute P(late) | ≤ 30% | 20.4% |
| Reroute P(stock-out) | 2–8% | 3.8% |
| Reroute freight | > 0 | Rs 8,131 |
| Total Reroute vs 0.6 × Continue | ≤ | Rs 12,095 ≤ Rs 105,996 |
| Split eligible, freight > Reroute | yes | yes, Rs 40,626 |
| Recommendation | REROUTE | REROUTE |
| Stability | STABLE 16/16 | STABLE 16/16 |

### G2
| Measure | Target | Measured |
| --- | --- | --- |
| Continue P(late) | ≥ 50% | 100.0% |
| Continue P(stock-out) | ≤ 5% | 0.0% |
| Best other total − Continue | Continue not beaten by > threshold | Continue Rs 7,175; Reroute Rs 8,564; threshold Rs 2,000 |
| Recommendation | No justified intervention | NO JUSTIFIED INTERVENTION |
| Stability (recorded) | — | SENSITIVE 10/16 |

### G3
| Measure | Target | Measured |
| --- | --- | --- |
| Continue violates α | yes | P(stock-out) 95% > 1% |
| Reroute violates α | yes | P(stock-out) 4% > 1% |
| Split violates freight cap | yes | Rs 40,626 > Rs 20,000 (also α and priority arrival) |
| Result | NO FEASIBLE OPTION – ESCALATE | NO FEASIBLE OPTION – ESCALATE; least-violating: REROUTE (info only) |
| CRITICAL alert to all coordinators | yes | yes (both coordinator accounts) |

Regenerate the measured table any time with `scripts/gen_reference_docs.py` → `GOLDEN_MEASURED.md`.
If those numbers move outside the targets, `pytest tests/test_golden.py` fails.
