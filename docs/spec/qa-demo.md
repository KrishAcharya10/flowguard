# QA and demo specification (as built)

## Test suites

| Suite | Command | Count | Covers |
| --- | --- | --- | --- |
| Backend unit, metamorphic, golden, access, workflow | `cd backend && .venv\Scripts\python -m pytest -q` | 126 | Engine maths, stock, risk, War Room, G1–G3, RBAC matrix, privacy, lifecycle, simulator, analytics, contract, performance, reset |
| Phase 0 hand-check (no DB) | `backend\.venv\Scripts\python scripts\phase0_handcheck.py` | 29 checks | G1–G3 targets compatible with concrete parameters |
| End-to-end (Playwright, production build, 3 browser contexts) | `cd frontend && npx playwright test` | 1 | The whole vertical slice; writes screenshots to `docs/screenshots/` |
| Type-check + production build | `cd frontend && npm run build` | — | TypeScript against generated API types |

## Spec §7 checklist → test

| Spec item | Test |
| --- | --- |
| Golden G1–G3 within ranges | `test_golden.py` |
| Longer disruption never lowers P(late) | `test_longer_disruption_never_lowers_p_late` |
| Earlier deadline never lowers P(late) | `test_earlier_deadline_never_lowers_p_late` |
| P10 ≤ P50 ≤ P90 | `test_percentiles_are_ordered` |
| Chips sum to mean(T) − baseline | `test_reason_chips_sum_to_mean_minus_baseline` |
| Same inputs + seed → same rounded results, two runs and two processes | `test_identical_inputs_and_seed_give_identical_results_twice`, `test_identical_results_across_two_processes` |
| Doubling p changes Total only via SLA | `test_doubling_p_changes_total_only_through_the_sla_term` |
| Infeasible never recommended | `test_infeasible_option_is_never_recommended` |
| Material change after scenarios → 409 | `test_material_change_after_scenarios_makes_approve_409`, `test_clock_advance_after_scenarios_makes_approve_409`, `test_assumptions_change_supersedes_open_cases_and_recalculates` |
| Stale telemetry widens uncertainty, no fabricated position | `test_stale_scale_widens_uncertainty_without_moving_the_baseline`, `test_stale_telemetry_widens_range_and_never_fabricates_a_position` |
| seed_pred ≠ seed_truth | `test_prediction_and_truth_seeds_differ_for_every_seeded_shipment` |
| engine imports no fastapi/sqlalchemy/simulator | `test_engine_imports_no_framework_and_no_simulator`, `test_mapping_layer_never_imports_the_simulator` |
| Stock: 3 hand examples + remainder before urgent | `test_stock_*` (4 tests) |
| Access matrix; cross-customer/transporter 404; key absence | `test_role_endpoint_matrix` (43 cases), `test_other_*_404*`, `test_customer_responses_contain_no_internal_keys` |
| Approve/reject idempotent; override reason; audit; customer notification; assumptions supersede | `test_approve_is_idempotent_and_applies_once`, `test_reject_is_idempotent`, `test_non_recommended_option_requires_override_reason`, `test_vertical_slice_end_to_end` |
| KPI buckets sum; on-time per order; delay events sum; transporter by company | `test_buckets_sum_to_active_total`, `test_on_time_is_per_order_at_gate_arrival`, `test_delay_events_sum_to_realised_delay_and_do_not_overlap`, `test_transporter_metrics_are_by_company_and_patterns_are_visible` |
| Performance: overview < 300 ms (80 shipments), scenarios < 2 s | `test_overview_with_80_live_shipments_is_under_300_ms` (≈ 150–210 ms measured), `test_performance_targets` (scenario creation ≈ 50 ms) |
| No wall clock / Python hash in business logic | `test_no_wall_clock_or_python_hash_in_business_logic` |
| OpenAPI export matches the app | `test_exported_openapi_matches_the_running_app` |

## Demo

See `docs/DEMO_RUNBOOK.md` for the timed script, reset-and-verify checklist, slide outline and Q&A drill.
