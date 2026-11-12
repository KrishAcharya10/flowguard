# Traceability: official requirements → build → tests → demo

Every official expectation (PDF page 7) maps to a screen, an endpoint, the tables behind it, at least one
automated test, and a step in the live demo (`docs/DEMO_RUNBOOK.md`).

## Official requirements O1–O5

| ID | Requirement (PDF p.7) | Screen | Endpoints | Tables | Tests | Demo step |
| --- | --- | --- | --- | --- | --- | --- |
| **O1** | Separate logins for customer, logistics coordinator, transporter/driver | Login (`/login`), role-guarded routes | `POST /api/auth/login`, `GET /api/auth/me` | `users` (role, customer_id, transporter_id, is_active) | `test_access.py::test_role_endpoint_matrix` (41 endpoints × 3 roles + anonymous), `test_other_customers_shipment_returns_404_not_403`, `test_other_drivers_shipment_returns_404_not_403`, `test_login_throttle_and_inactive_user`; E2E logs in 3 browser contexts | 0:00 three tabs, each logged in manually |
| **O2** | Track orders and shipments on a map, with status milestones | Control Tower map + table; Shipment Detail milestone bar; Customer Portal map + milestones; Driver portal | `GET /api/control-tower/map-data`, `GET /api/control-tower/overview`, `GET /api/customer/me/orders`, `POST /api/transporter/shipments/{id}/milestones` | `routes`, `route_waypoints`, `shipments` (state, last_lat/lon, last_telemetry_at), `shipment_events` | `test_driver_milestones_next_state_only_idempotent_and_not_in_future`, `test_stale_telemetry_widens_range_and_never_fabricates_a_position`, `test_clock_advance_moves_shipments...`; E2E steps 2–3 | 0:20 driver confirms "Loaded, waiting at plant gate"; coordinator sees it on map and table |
| **O3** | Predict an ETA and delay risk for each shipment, and show the reason | Shipment Detail "ETA intelligence" (P10/P50/P90, P(late), P(stock-out), risk, reason chips, "P50 moved +x h because …"), prediction history chart | `GET /api/shipments/{id}`, `GET /api/shipments/{id}/prediction?history=true`, `POST /api/shipments/{id}/recalculate` | `predictions` (immutable), `customer_inventory`, `disruptions` | `test_engine.py` (14 metamorphic/unit tests incl. chips sum, monotonicity, P10≤P50≤P90, determinism across processes), `test_golden.py::test_g1_*`, `test_get_endpoints_never_run_monte_carlo` | 0:40 inject flooding; ETA moves +5.4 h, risk LOW → HIGH, reason "Road closure wait" |
| **O4** | Alert the customer and coordinator on delay risk, with a suggested action (reroute / split) | Coordinator alerts drawer ("Suggested action: REROUTE via Dhule Bypass…", "Open War Room"); Customer "Delivery updates"; War Room | `GET /api/alerts`, `GET /api/customer/me/alerts`, `POST /api/shipments/{id}/scenarios`, `POST /api/interventions/{id}/approve` / `reject` | `alerts` (dedupe_key), `interventions`, `intervention_scenarios`, `audit_events` | `test_vertical_slice_end_to_end`, `test_customer_responses_contain_no_internal_keys`, `test_alerts_are_deduplicated`, `test_g3_no_feasible_option_escalates_to_all_coordinators`, approval lifecycle tests | 1:15 alert opens War Room; 1:35 comparison; 2:25 approve; 2:40 customer tab shows "Rerouting has been initiated" |
| **O5** | Dashboard of on-time performance and delay causes by route and transporter | Analytics → Performance (KPIs, on-time by route and by transporter company, stacked delay-cause charts, totals) | `GET /api/analytics/overview`, `/routes`, `/transporters`, `/delay-causes` | `shipments` (arrived_at), `orders` (promised_at), `delay_events` | `test_buckets_sum_to_active_total`, `test_on_time_is_per_order_at_gate_arrival`, `test_delay_events_sum_to_realised_delay_and_do_not_overlap`, `test_transporter_metrics_are_by_company...`, `test_delay_attribution_for_a_live_arrival` | 3:05 Analytics: Waluj to Amravati congestion pattern; Konkan Express weakest on Waluj to Satara |

## Differentiators D1–D4

| ID | Feature | Where | Tests |
| --- | --- | --- | --- |
| D1 | One probabilistic ETA/risk engine (`simulate_arrival`) used for current ETA, risk and every War Room option | `backend/app/engine/eta.py` | `test_only_one_eta_engine_function`, `test_g1_flooding...` asserts stored prediction == Continue scenario |
| D2 | War Room: Continue / Reroute / Split with costs, hard constraints, recommendation, approval | `engine/warroom.py`, `services/warroom.py`, War Room page | `test_golden.py` (G1–G3), workflow tests |
| D3 | Customer stock cover: sequential lot model, P(stock-out) | `engine/stock.py` | 4 hand-calculated stock tests incl. remainder-before-urgent |
| D4 | Editable assumptions + 16-case stability | Analytics → Assumptions; War Room stability card | `test_assumptions_change_supersedes_open_cases_and_recalculates`, `test_stability_has_16_cases...` |

## Bonus ideas (PDF p.7) — status

| Bonus | Status |
| --- | --- |
| Truck slot booking at the plant gate | **Built**: `/gate`, driver check-in, `backend/app/services/gate.py`; tests `test_bonus.py` (gate), `e2e/bonus-features.spec.ts` |
| "Where is my order?" chatbot | **Built** (rule-based, read-only): customer portal widget, `services/chat.py`; tests `test_bonus.py` (chat), e2e |
| Upload and download of invoice and proof of delivery | **Built**: `/documents`, driver POD upload, customer downloads, `services/documents.py`; tests `test_bonus.py` (documents), e2e |

## Presentation requirements (PDF p.10)

| Item | Where |
| --- | --- |
| Measurable impact with calculation and assumptions | Analytics → Business impact (Panel A from approved cases, Panel B editable formula); `docs/DEMO_RUNBOOK.md` slide 4 |
| Architecture diagram matching the demo | `docs/ARCHITECTURE.md` (+ `docs/architecture.svg`) |
| Controls (human review, confidence, privacy, access) | Analytics → Responsible AI tab; `docs/KNOWN_LIMITATIONS.md`; War Room override rules |
| Where AI is used and not used | `docs/AI_DISCLOSURE.md`; Responsible AI tab |
