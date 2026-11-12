# Final audit

Run on 2026-11-12 against the built repository. Evidence = commands that were actually run.

| Command | Result |
| --- | --- |
| `cd backend && .venv\Scripts\python -m pytest -q` | **126 passed** |
| `backend\.venv\Scripts\python scripts\phase0_handcheck.py` | **ALL TARGETS COMPATIBLE – GO** (29/29) |
| `cd frontend && npm run build` | TypeScript + Vite build succeeds |
| `cd frontend && npx playwright test` | **3 passed** (3 browser sessions, production build, zero external requests) |

## Five most likely ways this project fails on the day

| # | Failure | Mitigation in place | Remaining action |
| --- | --- | --- | --- |
| 1 | A team member cannot explain a part of the code (rule 5) | Walkthroughs, three defence briefs, Q&A drill | **Each developer reads their brief and signs `AI_DISCLOSURE.md`** |
| 2 | Undeclared AI use (−10 points) | `AI_DISCLOSURE.md` lists this session | **Team adds the tools used to write the master prompt and slides** |
| 3 | Clock advanced during the War Room → approval refused live | 409 with a clear message; runbook says keep the clock paused | Rehearse five times |
| 4 | Laptop/server problem during the live demo | One command start, Reset demo button, offline-capable | **Record the backup video** |
| 5 | Judges read modelled figures as achieved savings | Every figure labelled MODELLED; "not verified Plant X or LYB performance" banner | Say "modelled" out loud |

## Requirement audit

| Requirement | Status | Test evidence | Demo evidence | Remaining limitation |
| --- | --- | --- | --- | --- |
| O1 Separate logins (customer, coordinator, transporter) | **PASS** | `test_role_endpoint_matrix` (43 endpoints × anon + 3 roles), 404 ownership tests, throttle/inactive test | Three tabs, manual login | Token in sessionStorage (documented) |
| O2 Map + status milestones | **PASS** | Milestone rules tests, stale-position test, clock test | Driver confirms gate; map + table update | Illustrative grid routes, not real roads |
| O3 ETA + delay risk + reason | **PASS** | 14 engine tests, golden G1, chips-sum test, P50-change attribution | ETA +5.4 h, Low→High, "road closure wait" | Assumed distributions, no accuracy claim |
| O4 Alert customer + coordinator with suggested action (reroute/split) | **PASS** | Vertical-slice test, customer key-absence test, dedupe test, G3 CRITICAL alert | Alert drawer → War Room → approve → customer "Rerouting has been initiated" | Single-shipment, not fleet |
| O5 Dashboard: on-time + delay causes by route and transporter | **PASS** | Bucket, per-order on-time, delay-sum, company-level tests | Analytics → Performance | Fictional history |
| D1 Single probabilistic engine | **PASS** | `test_only_one_eta_engine_function`; stored prediction == Continue | — | — |
| D2 War Room (3 options, constraints, approval) | **PASS** | G1–G3, lifecycle tests | Comparison table, approve | — |
| D3 Stock cover | **PASS** | 4 hand-calculated stock tests | P(stock-out) in detail and War Room | Fictional stock data; consent needed |
| D4 Editable assumptions + stability | **PASS** | Assumptions supersede test; 16-case test | Stability card; Assumptions tab | — |
| Bonus: POD | **PARTIAL** | POD test | Driver portal | Status + recipient only; no file upload |
| Bonus: gate booking, chatbot | **NOT BUILT** | — | — | Out of scope by design |
| Impact indicator with calculation | **PASS** | Panel B formula test | Business impact tab | Illustrative inputs |
| Architecture diagram matching demo | **PASS** | Rendered from `architecture.mmd` | Slide 5 | — |
| Generative AI declared | **PARTIAL** | — | `AI_DISCLOSURE.md` | Team must add non-session tools and sign off |

## Audit areas

| Area | Verdict | Evidence |
| --- | --- | --- |
| ETA maths | OK | Monotonicity, ordering, determinism (two processes), residual ≈ 0 in deterministic case, active-closure residual test |
| Stock maths | OK | 4 hand examples incl. remainder-before-urgent |
| Cost maths | OK | Doubling p changes only SLA; split SLA quantity-weighted (hand-checked) |
| Infeasibility | OK | Never recommended; least-violating info only; override reason + audit |
| Stability | OK | 16 cases, label consistent with count; G1 STABLE 16/16 |
| DB consistency | OK | FKs on, CHECK constraints, split quantities sum exactly, append-only audit |
| RBAC | OK | Matrix test covers every route in the OpenAPI schema |
| Customer privacy | OK | Key-absence on 4 customer endpoints after a full intervention; no "Rs" in customer text |
| Dashboard correctness | OK | KPIs recomputed independently in tests |
| Offline operation | OK | E2E asserts zero non-local requests |
| Demo repeatability | OK | Deterministic seed + reset endpoint; reset test |
| Team explainability | **Pending humans** | Briefs and walkthroughs written; sign-off not yet done |

## Strict self-score against the rubric (honest estimate, not a promise)

| Criterion | Max | Estimate | Why not full marks |
| --- | --- | --- | --- |
| Problem understanding & user fit | 10 | 8–9 | Three distinct user views; stock-cover framing is strong |
| Innovation & original thinking | 10 | 7–9 | War Room + stability + "late is not costly" are distinctive |
| Working prototype | 20 | 16–19 | Full slice works offline; bonus items mostly skipped |
| Technical design & architecture | 10 | 8–9 | Clean layering, contracts, tests; SQLite single worker |
| Feasibility & scalability | 10 | 6–8 | Pilot path is credible but untested on real data |
| Business value & impact | 15 | 10–13 | Impact is modelled only (correctly labelled) |
| Responsible AI, security & data | 10 | 8–9 | Strong controls; sessionStorage token |
| UX & accessibility | 5 | 4 | Not audited with a screen reader |
| Presentation & demo | 5 | depends on rehearsal | |
| Q&A & team understanding | 5 | depends on the team | |

## Acceptance gates (spec §9)

| # | Gate | Status | Evidence |
| --- | --- | --- | --- |
| 1 | O1–O5 functional | PASS | Table above |
| 2 | Three roles connected | PASS | E2E: driver action → coordinator → customer |
| 3 | Predictions from the real engine | PASS | Stored prediction equals War Room Continue (G1 test) |
| 4 | Scenarios internally consistent | PASS | Common random numbers; correlation test |
| 5 | Infeasible never recommended | PASS | Engine + G3 tests |
| 6 | Approval protected by versions | PASS | Three 409 tests (shipment, clock, assumptions) |
| 7 | Customer data separated | PASS | Key-absence + 404 tests |
| 8 | Dashboard from real records | PASS | Analytics tests; no hard-coded figures in UI |
| 9 | Reproducible, offline-capable demo | PASS | Reset test; E2E offline assertion |
| 10 | Docs, disclosure, diagram, defence briefs | PARTIAL | All written; **human sign-off, slides and backup video remain** |
