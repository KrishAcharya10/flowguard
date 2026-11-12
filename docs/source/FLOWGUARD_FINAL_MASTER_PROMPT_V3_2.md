# FLOWGUARD — FINAL CLAUDE CODE MASTER BUILD PROMPT V3.2 (AUTHORITATIVE)

**Use this entire document as the single master instruction for Claude Code Fable 5.2.**
This V3.2 document consolidates the implementation kickoff and the authoritative technical
specification. Do not combine it with older OG, V3, V3.1, or separate full-build prompts.
If any sentence later in this document conflicts with the clarifications in this header,
this header takes precedence. The official LYB hackathon PDF remains the authority for
official problem-statement requirements and rules; this prompt defines the implementation
architecture, modelling assumptions, contracts, and acceptance criteria.

## Authority, conflict resolution, and execution roles

- **Official requirement authority:** the supplied LYB problem-statement PDF controls the official
  problem statement, mandatory requirements, restrictions, judging rubric, and presentation rules.
- **Engineering authority:** this V3.2 prompt controls implementation details, data contracts,
  algorithms, lifecycle semantics, security, testing, and acceptance gates. Do not silently
  substitute a different design from an older prompt, repository note, or generated plan.
- **Conflict handling:** if an engineering instruction appears to violate the official PDF, stop
  and report the exact conflict. For contradictions inside this prompt, use the numbered
  clarifications immediately below as authoritative. Do not invent an interpretation.
- **Primary agent:** Claude Fable 5.2 owns integrated implementation. The three human developers
  own review and sign-off for their modules. Opus is read-only reviewer; Sonnet may apply only
  explicitly approved fixes.
- **Approval gate:** Phase 0 is a design-and-contract phase only. Do not create application
  features, seed the live demo database, or begin feature implementation until a human explicitly
  approves the Phase 0 report. A GO recommendation from Claude is not human approval.
- **Truthful product positioning:** FLOWGUARD is a predictive logistics decision-support
  prototype. Its runtime ETA/risk calculations are the specified stochastic simulation and
  deterministic business rules, not a trained ML model or runtime generative-AI system.
  Generative AI used during development must be disclosed accurately in `docs/AI_DISCLOSURE.md`.

## Before launch — fill these two fields

- `H = 24` as the initial planning baseline; replace it with the actual remaining build hours if different. The official PDF does not promise a 24-hour build window.
- `Integration owner = Developer 1` by default; change if the team chooses another owner.

## Final authoritative clarifications

1. **Shipment-state names:** use `PLANNED > LOADING > AT_PLANT_GATE > IN_TRANSIT > ARRIVED_AT_CUSTOMER_GATE > DELIVERED`. `AT_PLANT_GATE` means loaded and waiting to leave Plant X. `ARRIVED_AT_CUSTOMER_GATE` means arrived at the customer's receiving gate. Never use the legacy aliases `AT_GATE` or `ARRIVED` for these states. Use the exact
   canonical enum values above in the database, API, tests, fixtures, and UI state mapping. A split parent has a separate terminal disposition `SPLIT_PARENT`, is not DELIVERED, and is excluded from delivery KPIs.
2. **Breakdown semantics:** a vehicle breakdown is a `VEHICLE_STOPPAGE` at the current position with a sampled repair duration. It is not a route closure. Flooding/blocked-road events remain route closures. This avoids the contradiction where a closure blocks entry but the vehicle is already on the affected segment.
3. **Reason-chip math:** define a deterministic baseline from remaining reference handling plus base route travel. Show the mean contribution of handling deviation, gate queue, slowdown, closure wait and repair wait. Define a residual that makes the contributions sum to `mean(T) - baseline` within floating-point tolerance. The residual may contain multiplicative interactions; do not require it to be zero in every scenario. Label chips as mean contributions and show P50/P90 separately.
4. **Route alternative topology:** every alternative route must explicitly identify its primary route, entry decision node and destination/rejoin point. If no valid connection exists, reroute is ineligible. Do not infer route connectivity from names.
5. **Split-shipment representation:** the parent becomes `SPLIT_PARENT`; two child lots share the original order and have quantities summing exactly to the parent quantity. Model the second vehicle/driver as a separate fictional resource even if it belongs to the same transporter company. Do not imply one driver operates two vehicles.
6. **Approval freshness:** every intervention snapshots `shipment.state_version`, `assumptions_version` and the simulation clock version or `sim_now`. Approval must reject with HTTP 409 and require re-simulation if any snapshot is stale. This is necessary because clock advancement changes the vehicle position and can invalidate a decision node. Keep the demo clock paused while the coordinator reviews and approves a scenario.
7. **Customer-safe O4 alert:** the coordinator receives the specific suggested action (reroute or split) and its operational reason. The customer receives a safe plain-language action message, e.g. “Your delivery may be delayed. Our logistics team is evaluating an alternate route; no action is required from you.” After approval, show the action taken and updated expected delivery. Never expose internal cost assumptions.
8. **On-time KPI:** use customer-gate arrival, not later proof-of-delivery completion. An order is eligible for the denominator once all non-parent leaf lots have reached the customer gate. It is on time only if every leaf lot arrived by the original immutable `promised_at` plus grace. `SPLIT_PARENT` rows are excluded; child lots are attributed to the original order.
9. **Delay attribution:** realised delay is `max(0, arrived_at - planned_arrival_at)`. Seeded, non-overlapping delay-event hours must sum to this quantity within a documented rounding tolerance. Do not create negative delay causes for early shipments.
10. **Monte Carlo pairing:** use common random numbers across Continue/Reroute/Split. For split lots, use a scenario-case variate matrix with shared shipment-level factors and stable route-segment/lot-specific columns. Do not accidentally reuse one lot's complete random stream for both child lots or use independent unrelated streams that make option comparisons noisy. Keep prediction seeds separate from hidden simulator-truth seeds.
11. **Numerical units:** use hours internally for duration, kilometres for distance, tonnes for quantity, tonnes/hour for consumption, and ₹ for currency. Store timestamps in UTC and display Asia/Kolkata. Validate all conversions at API boundaries.
12. **SQLite:** use one Uvicorn worker, WAL mode, foreign keys on every connection, a documented busy timeout and short write transactions. Do not run parallel background writers. Pin NumPy and all other dependencies in the lockfile; deterministic test comparisons should use documented rounded numerical tolerances on the same locked environment, not raw floating-point byte identity.
13. **Alerts and no-feasible-option:** create an alert when the displayed risk category moves upward to MEDIUM or HIGH, subject to deduplication. For no-feasible-option, alert all logistics coordinators (there is no fourth supervisor role). Keep the least-violating option informational only. Never label it recommended. Any override requires a reason and an explicit `CONSTRAINT OVERRIDE` audit entry.
14. **Single-session development:** Fable is the integrated primary coding agent. Human developers own/review modules. Opus performs read-only audits. Sonnet implements specifically approved fixes. Do not create parallel Claude coding sessions unless separate Git worktrees and branches are explicitly set up.
15. **Human understanding:** after each implementation phase, produce the plain-language walkthrough and developer defence notes. The team must read them and be able to explain the code and business logic, not merely present generated output.
16. **No feature creep:** build O1–O5 first, then D1–D4. The War Room's basic actionable O4 recommendation must exist in the hour-8 vertical slice; full three-option comparison and approval follows immediately. Do not start optional X features until official requirements and core differentiators are tested.
17. **Legacy prompt reconciliation:** where an older kickoff says `AT_GATE` or `ARRIVED`, map
    those labels to `AT_PLANT_GATE` or `ARRIVED_AT_CUSTOMER_GATE` only when the underlying event
    meaning is unambiguous. Otherwise stop and flag the data/contract migration; never silently
    coerce ambiguous historical values. The canonical enum in item 1 is mandatory.
18. **Prediction versus simulator truth:** do not pass simulator-truth samples, hidden positions,
    or future event outcomes into the prediction engine, API responses, customer views, or visible
    map. Prediction and truth remain isolated even when both are deterministically seeded.
19. **O4 messaging and approval:** an alert is not an executed intervention. Before approval,
    customer messaging must say the team is evaluating an option. Only after a successful
    transactional apply may it say rerouting/splitting has been initiated. Keep customer-safe
    messages free of internal cost, penalty, inventory-rate, and competing-transporter details.

## Final launch sequence

1. Put the official PDF at `docs/source/LYB_Mumbai_Hackathon_2026_Round2_Problem_Statements.pdf`.
2. Open Claude Code in the FlowGuard repository and select Fable 5.2.
3. Paste this entire document.
4. Fable performs Phase 0 only and stops for human approval.
5. Review the traceability matrix, engine contracts and G1–G3 hand-checks before authorising coding.
6. After approval, Fable proceeds through implementation and testing phases.
7. Opus independently audits the repository read-only; Sonnet applies approved targeted fixes.

---

FLOWGUARD — IMPLEMENTATION SPECIFICATION — LYB MUMBAI HACKATHON 2026, PROBLEM STATEMENT 3

You are Claude Fable 5.2, the integrated primary build agent for FLOWGUARD
("Predict. Simulate. Deliver."), a decision-support control tower for a fictional
polymer producer, Plant X. Three human developers own modules and review your work.
Opus later audits read-only. Sonnet later applies approved targeted fixes.

BUILD WINDOW H = 24 hours as the initial planning baseline (NOT stated in the PDF; replace if the actual remaining window differs).
Integration owner (merges, approves): Developer 1, unless the team explicitly assigns another owner.
Dev1 = backend/data reviewer. Dev2 = frontend/UX reviewer. Dev3 = engine/QA/demo owner.

================================================================
1. SOURCE OF TRUTH
================================================================
Read docs/source/LYB_Mumbai_Hackathon_2026_Round2_Problem_Statements.pdf fully.
If it cannot be read, STOP and report. Do not invent its contents.
Extract Problem Statement 3, the ground rules, the 10-minute format, the judging rubric
and the final checklist VERBATIM into docs/source/requirements.md with page numbers.

Official requirements (all mandatory, nothing may displace them):
 O1 Separate logins: customer, logistics coordinator, transporter/driver.
 O2 Track orders and shipments on a map with status milestones.
 O3 Predict ETA and delay risk per shipment and show the reason.
 O4 Alert customer and coordinator on delay risk with a suggested action (reroute or split).
 O5 Dashboard: on-time performance and delay causes by route and transporter.
Bonus ideas (optional): gate slot booking, "Where is my order?" chatbot, invoice/POD files.
Rubric: working prototype 20; business impact 15; problem fit, innovation, technical design,
feasibility, responsible AI/security/data 10 each; UX, presentation/demo, Q&A 5 each.
Rule 5: generative AI is allowed but MUST be declared; undeclared use costs 10 points; every
member must be able to explain all code, data and design. No data is supplied; use only
fictional data. Never imply a real LYB site, system, route or transporter.

Scope classes:
 O = O1-O5. D1 single probabilistic ETA/risk engine. D2 three-scenario War Room.
 D3 customer stock cover. D4 editable assumptions + recommendation stability.
 E = alert escalation, speed control, custom disruption parameters, driver-reported hazards.
 X = carbon, QR/OTP POD, gate booking, offline driver queue, chatbot extras.
Build E only after O and D are tested. Start X only before nothing else is pending.
O4 is NOT optional: even the hour-8 slice must show an actionable Continue-vs-Reroute
suggestion with a reason. The full War Room follows immediately after.
Cut order if time shrinks: X, then speed control, custom disruption parameters, alert
escalation, stability analysis, Panel A. Never cut O1-O5, D1, D2. If H < 16, drop all E and X.

================================================================
2. EXECUTION MODE
================================================================
PHASE 0 (no application features). Produce, then STOP for human approval:
 - docs/source/requirements.md, docs/TRACEABILITY.md (O1-O5 -> screen, endpoint, tables,
   test, demo step), docs/ASSUMPTIONS.md (every invented number and why)
 - docs/GOLDEN_SCENARIO.md (inputs + target ranges; Section 6), docs/GOLDEN_BASELINE.md
   (placeholder, filled after tuning)
 - SQLAlchemy models, Pydantic schemas, exported contracts/openapi.json, contracts/fixtures/,
   backend/app/engine/contracts.py (typed engine inputs/outputs), docs/API_ACCESS_MATRIX.md
 - docs/spec/engine.md, api.md, ui.md, qa-demo.md: derived faithfully from this prompt, no
   contradictions with it, no silent additions
 - CLAUDE.md (max 200 lines): identity, O1-O5, execution mode, scope classes, ownership, hard
   rules (Section 3), phase list, stop conditions
 - Hand-checks (script or arithmetic) proving G1, G2, G3 targets are mutually compatible with
   concrete parameters, the sequential stock model, reroute/split eligibility, cost formulas,
   and no-feasible-option behaviour. If any target is infeasible, report the exact inputs and a
   proposed correction. Do NOT edit target ranges to make things pass.
 - Final Phase 0 report: verified items, unresolved decisions, risks, GO/NO-GO.
After explicit human approval, work autonomously through the phases without further plans.

STOP AND ASK ONLY IF: a paid service/secret is needed; a destructive operation on existing
files is needed; a frozen contract must change; an official requirement is at risk; a major
approved architecture decision must change.

SESSION HYGIENE: keep PROGRESS.md (done / next / blockers / test status / open decisions).
Commit at the end of every phase. If context grows large, update PROGRESS.md and tell the
human to start a fresh session that re-reads CLAUDE.md and PROGRESS.md.
If humans later run parallel Claude sessions, use separate git worktrees and branches; shared
files (contracts/, docs/, lockfiles, router registry) change only via integration-owner merge.

After each phase write a plain-language walkthrough of what you changed in each human
owner's area (docs/walkthroughs/phase-N.md). Build docs/DEFENCE_BRIEF_DEV1/2/3.md
incrementally from these (module summary, key formulas in words, three hard Q&As each).

================================================================
3. HARD RULES
================================================================
 - No datetime.now()/time.time() in business logic. Time is injected from simulation_state.
 - Never use Python hash(). Seeds use zlib.crc32. No seed depends on the wall clock.
 - Seed namespaces (Section 4.2). Engine and ORM-to-engine mapping must never import simulator.
 - Exactly one ETA engine function: simulate_arrival(inputs, n_samples, seed).
 - Pydantic schemas are the single source of API truth; export openapi.json programmatically;
   a test fails if it differs from the running app; generate TypeScript types from it.
 - Customer responses use separate allow-list schemas.
 - Every synthetic business figure is labelled MODELLED or SIMULATED. Never "saved/ROI/achieved"
   without "modelled". Currency: Rs (fictional).
 - promised_at is immutable. Customer wording: "Updated expected delivery", never "new commitment".
 - Never report a test as passed without running it. Never claim a feature complete without
   evidence. Never claim an external service works unless you executed it.
 - No paid API, secret, CDN or live routing/traffic/weather service is needed to run the demo.
 - No feature work after feature freeze (H-5). After code freeze (H-3): P0 bug fixes only.

================================================================
4. CANONICAL SPECIFICATION
================================================================
4.1 DEFINITIONS (declared modelling assumptions, not LYB policy)
 promised_at       promised arrival deadline at the customer's receiving gate (immutable)
 planned_arrival_at the original operational plan (promised_at minus a buffer)
 arrived_at        gate-arrival event; ON-TIME = arrived_at <= promised_at + grace (default 0)
 delivered_at      later proof-of-delivery completion (status + recipient name in v1)
 Order on-time requires ALL lots arrived by promised_at. Lot-level data feeds delay analytics.
 Realised delay = max(0, arrived_at - planned_arrival_at); lateness = max(0, arrived_at - promised_at). Delay-event attributed hours must sum to realised delay exactly (within a documented rounding tolerance).
 revised_eta_communicated (+ _at) is a communication record only; never used in KPIs.
 Milestones forward-only: PLANNED > LOADING > AT_PLANT_GATE > IN_TRANSIT > ARRIVED_AT_CUSTOMER_GATE > DELIVERED. A split parent has separate terminal disposition SPLIT_PARENT and is not a delivery milestone. AT_PLANT_GATE means the vehicle is loaded and waiting to depart Plant X; ARRIVED_AT_CUSTOMER_GATE means it has reached the customer's receiving gate.
 Driver updates: assigned shipment only, next state only, not later than sim_now, idempotent,
 creates an event, bumps state_version.

4.2 TRUTH VERSUS BELIEF
 seed_pred  = zlib.crc32(f"{GLOBAL_SEED}|pred|{shipment_id}")
 seed_truth = zlib.crc32(f"{GLOBAL_SEED}|truth|{shipment_id}|{route_id}|{lot_type}")
 The simulator holds hidden realisations derived from seed_truth, re-derived on demand, NEVER
 stored. They cover the primary route, alternative route and split lots, so the outcome of any
 approved option is already determined. The predictor sees only observed events, telemetry and
 declared distributions. Tests: seed_pred != seed_truth for every seeded shipment;
 engine/ and the mapping layer do not import simulator/.
 Telemetry: simulator emits an observed position per clock step unless a TELEMETRY_OUTAGE is
 active; the map shows the last REPORTED position and its age; hidden position is never shown
 as observed.

4.3 ETA ENGINE (single path; same function for current ETA, risk and every War Room scenario)
 For sample i of N = 500:
   T_i = t_now + handling_i + travel_i + gate_queue_i + closure_wait_i + repair_wait_i
   travel_i = sum over remaining segments j of (d_j / v_j) * R_i * S_ij * m_ij
   Factors: Z ~ N(0,1); factor = exp(sigma * Z - sigma^2 / 2)  (sigma is a STANDARD DEVIATION)
   R_i  one route-level factor shared by all segments (sigma_route)
   S_ij per-segment factor (sigma_segment < sigma_route by default)
   m_ij >= 1 slowdown multiplier, applied to segment j if the vehicle ENTERS j inside the
        slowdown window (entry-time rule; no piecewise integration)
   d_j = haversine(consecutive waypoints) * circuity (default 1.2); never hand-entered
   handling_i: only stages NOT yet completed (no double counting of past delays)
   gate_queue_i ~ Triangular(min, mode, max) only while the vehicle is still queued, else 0
   Transporter factor scales sigma only (default 1.0); it does not move the mean.
 Closure: wait = max(0, end - t_reach) if t_reach >= start else 0. Simplification, stated in
   the UI/docs: a closure blocks ENTRY to the segment; a vehicle already inside it is unaffected.
 Residual closure duration (ACTIVE closure with elapsed e = t_now - t_start, duration CDF F
   from Triangular(min, mode, max)):
     u' = F(e) + u * (1 - F(e));  duration = F^-1(u');  end = t_start + duration
   If F(e) >= 0.999: residual = u * residual_floor (default 0.5 h) and end = t_now + residual.
   For a closure not yet started use the unconditional u. Never resample a total duration that
   implies an active closure already ended.
 Sampling: pre-draw ONE matrix of standard variates per shipment (named columns: route factor,
   segment factors, gate queue u, closure-duration u, handling u). All options (Continue,
   Reroute, Split) reuse it (common random numbers). Pin numpy in the lockfile.
 Outputs: nearest-rank P10, P50, P90; P(late) = mean(T_i > promised_at). Display ETA rounded to
   5 min and probabilities as whole percent (MC standard error up to ~2.2 pp at N=500; say so).
   Sanity: promised_at >= P90 implies P(late) <= ~10%; P50 > promised_at implies P(late) > 50%.
 Stale data: age = sim_now - last_telemetry_at. Fresh/Aging/Stale thresholds are assumptions.
   If Stale, multiply both sigmas by (1 + min(age/stale_threshold, 2)). Show "Data Confidence";
   staleness is NOT a separate risk-index term.
 Predictions are stored immutably (seed, n, p10/p50/p90, p_late, p_stockout, risk_index,
   previous_p50, trigger_event_id, reasons_json, state_version, assumptions_version).
   Recompute on: material milestone, disruption start/end, telemetry outage start/end,
   intervention applied, assumptions change, clock advance. GET endpoints NEVER run Monte Carlo.
   Predictions exist for all active shipments including PLANNED; delivered shows actuals.
 The Monte Carlo measures uncertainty under assumed distributions. It is NOT an empirical
   accuracy claim and NOT a trained ML model. State this in UI and docs.

4.4 REASON DECOMPOSITION (explains the MEAN, not P50)
 Define base_handling as the documented deterministic reference duration for only the
 remaining handling stages. Define base_travel = sum_j(d_j/v_j). Define baseline ETA as
 t_now + base_handling + base_travel, with no queue, disruption or stochastic factors.
 Components, computed as sample means:
 - handling deviation = mean(handling_i) - base_handling;
 - gate queue = mean(gate_queue_i);
 - slowdown increment = mean(sum_j(base_j * (m_ij - 1)));
 - closure wait = mean(closure_wait_i);
 - vehicle repair wait = mean(repair_wait_i), when applicable;
 - travel variability / interactions = mean(T) - baseline - sum(all preceding components).
 The residual closes the decomposition exactly within floating-point tolerance. It may be
 non-zero when multiplicative route/segment factors interact with slowdowns or closures; do not
 claim it must always be near zero. In a no-disruption deterministic baseline test it should
 be approximately zero. Label all chips "mean contribution". Display P50/P90 separately.
 Stale/transporter uncertainty appears as separate non-hour chips.
 "Why did P50 change": rerun previous inputs and current inputs with the SAME variate matrix,
 report the P50 difference and attribute it to trigger_event_id.
 Example: "P50 moved +2.6 h since 14:10: flooding event 7."

4.5 DISRUPTION TAXONOMY
 delay_events.cause enum: FLOODING, BREAKDOWN, GATE_CONGESTION, SLOW_LOADING, LATE_DISPATCH,
 ROUTE_CONGESTION. TELEMETRY_OUTAGE is a data-quality event, not a delay cause.
 FLOODING -> CLOSURE on a chosen segment. BREAKDOWN -> VEHICLE_STOPPAGE at the vehicle's
 current position with a sampled repair duration; it is not a route closure. GATE_CONGESTION ->
 shifts gate_queue triangular params. SLOW_LOADING -> shifts handling distribution.
 LATE_DISPATCH -> fixed departure offset only while departure is still pending; once departed,
 the elapsed delay is already represented by the current simulation state and must not be added
 again. ROUTE_CONGESTION -> SLOWDOWN.
 Presets are parameterised events (route/segment, start, duration range), validated bounds.
 Overlapping disruptions must not double-count.
 Endpoints: POST /api/simulations/disruptions, GET same, POST .../{id}/end.

4.6 STOCK MODEL (affects consequence, priority and ranking; NEVER travel time)
 Per customer: inventory I0 (tonnes) at t0, consumption r (t/h), unloading u (h), priority qty.
 Depletion S = t0 + I0/r. Usable arrival of a lot: A = T + u.
 Sequential lot model (any number of lots, any arrival order):
   cover_end = S; stockout_hours = 0
   for each lot sorted by A ascending:
       stockout_hours += max(0, A - cover_end)
       cover_end = max(cover_end, A) + q_lot / r
 P(stockout) = mean(stockout_hours_i > 0). One lot reduces to max(0, A - S).
 If a customer has no stock data: omit the stock terms, set w_late = 1, show
 "Stock data unavailable". Label: "Customer stock data is fictional; a real deployment needs
 customer consent to share coarse stock-cover data."
 Hard constraints on stock are stated on probabilities, never on P50.

4.7 RISK INDEX
 Index = round(100 * (w_late * P(late) + w_stock * P(stockout))), defaults 0.6/0.4, sum to 1,
 editable with validation. A heuristic index, not a probability. Bands: LOW 0-29, MEDIUM 30-59,
 HIGH 60-100 (assumptions). Category floors: MEDIUM if P(late) >= 25%; HIGH if P(late) >= 50%
 or P(stockout) >= 30%. Displayed category = max(band, floor). Priority affects alert routing
 and list ordering only.
 Alert triggers (independent of the index): displayed risk category transitions upward to MEDIUM
 or HIGH; P(late) crosses 50%; P(stockout) crosses 20%; an active disruption on the remaining
 path has expected wait >= configured hours; or a high-priority shipment becomes Stale. Fire only on category change or index change >= 10;
 dedupe with a dedupe_key. Customer alerts: plain-language reason, Low/Medium/High, ETA range, original promise, updated
 expected delivery and customer-safe suggested action (for example, "Our logistics team is
 evaluating an alternate route; no action is required from you"). After approval, show the action
 taken. Never expose internal costs.

4.8 WAR ROOM (single-shipment optimisation; NOT fleet optimisation; say so in the UI)
 Options: CONTINUE (always eligible), REROUTE, SPLIT.
 REROUTE: eligible only if the vehicle has not passed a decision node ahead of the affected
   segment. Each alternative route must explicitly identify its primary route, entry decision
   node and destination/rejoin point; do not infer the connection from route names. Remaining =
   current position-to-entry-node + alternative route from entry to destination/rejoin point.
   Cost = extra_km * cost_per_km + fixed handling. If no valid connection exists, mark it
   ineligible with the reason.
 SPLIT: eligible only for PLANNED, LOADING or AT_PLANT_GATE. Second vehicle available after a
   configurable fictional lead time (assumption). q_u = max(min priority qty, qty covering a
   configured number of consumption hours), capped at Q. Urgent lot takes the alternative route
   when a closure affects the primary; the remainder follows the original plan. Cost = second
   vehicle fixed cost + cost_per_km * distance. On application: parent receives a separate terminal disposition SPLIT_PARENT (not DELIVERED
   and excluded from delivery KPIs); two child shipments (URGENT, REMAINDER, parent_shipment_id)
   are created under the same order. Their quantities must sum exactly to the parent quantity.
   Children start in LOADING after the second-vehicle lead time. If they inherit the same
   transporter company, they still represent a separate fictional vehicle/driver resource; state
   this assumption and do not imply one driver operates two vehicles simultaneously.
 Ineligible options stay visible, greyed, with the reason.
 Per option show: P50, P90, P(late), P(stockout), expected late hours, expected stock-out
 hours, extra freight, SLA cost, stock-out cost, expected total, optional CO2.
 COST (incremental vs the current plan; D = original promised_at):
   Freight_k   incremental freight (Continue = 0)
   SLA_k       p * mean(max(0, T_i - D)); p = contractual penalty per late hour for the order
   Stockout_k  s * mean(stockout_hours_i); s = INCREMENTAL stock-out cost per hour beyond p
   Total_k     Freight_k + SLA_k + Stockout_k  (three components displayed separately)
   Split SLA   p * [ (q_u/Q) * mean(max(0, T_u - D)) + (1 - q_u/Q) * mean(max(0, T_r - D)) ]
 Never model stock-out cost as fixed amount * P(stockout). Rates are fictional assumptions.
 HARD CONSTRAINTS (configurable, validated): alpha = max P(stockout) (default 10%); max
 incremental freight cost; min urgent quantity; required priority arrival P(A_urgent <= S)
 >= 1 - alpha; optional beta = max P(late) (default off). Infeasible options are never
 recommended.
 RECOMMENDATION: lowest Total among feasible options. If the best beats Continue by less than
 max(2% of Total_Continue, a configured minimum absolute saving) -> "NO JUSTIFIED INTERVENTION -
 CONTINUE CURRENT PLAN" (handle zero-baseline explicitly). Always show why, cost advantage, ETA
 difference, main risk, trade-offs, assumptions.
 NO FEASIBLE OPTION: banner "NO FEASIBLE OPTION - ESCALATE", violated constraints per option,
 least-violating option as information only (never "Recommended"), CRITICAL alert to all
 coordinators (no fourth role).
 STABILITY: stress freight scale, p, s, mean disruption duration at -25% and +25%: 16 full-
 factorial cases. Cost-only changes reuse stored samples; duration changes rerun the engine with
 the same variate matrix. An option becoming infeasible counts as a change. Labels: STABLE = same
 recommendation in 16/16; SENSITIVE = 8-15; NO ROBUST RECOMMENDATION = under 8 or none feasible.
 Show "holds in x of 16 stress cases" (a count, not a probability) and the nearest break-even
 (costs are linear in freight, p, s) when calculable.

4.9 INTERVENTION LIFECYCLE
 One decision case per shipment containing its scenarios, recommendation, stability result,
 constraint snapshot, shipment.state_version, assumptions_version and simulation_state.clock_version.
 States: AWAITING_APPROVAL > APPROVED | REJECTED | SUPERSEDED; APPROVED > APPLIED > COMPLETED.
 At most one AWAITING_APPROVAL per shipment; a new case supersedes the old.
 state_version bumps on material events (milestone, disruption start/end, telemetry outage
 start/end, applied intervention), not on clock ticks. assumptions_version bumps on every
 PUT /api/assumptions, which also recalculates active predictions, supersedes open cases and
 writes an audit event.
 Approve takes selected_scenario_id and optional override_reason. Returns 409 if shipment.state_version, assumptions_version or simulation clock version differs
 (case marked SUPERSEDED, recalculation required). Approve/reject idempotent.
 Approving a non-recommended or infeasible option requires an override_reason, shown as
 "CONSTRAINT OVERRIDE" in the audit log.
 Application is ONE database transaction: shipment/route change or split, event, new
 prediction, customer and coordinator alerts, audit event.

4.10 KPIs
 Active transit buckets (mutually exclusive, sum to shipments not yet at the customer gate):
 LATE (promised_at passed), AT_RISK (not late, category Medium/High), ON_TRACK (not late, Low).
 Shipments that reached ARRIVED_AT_CUSTOMER_GATE but await POD are displayed separately as
 ARRIVED_PENDING_POD. Delivered/POD-complete shipments are separate. SPLIT_PARENT is excluded.
 On-time % = orders whose every non-parent leaf shipment lot has reached
 ARRIVED_AT_CUSTOMER_GATE by promised_at + grace, divided by orders whose every leaf lot reached
 the customer gate in the selected window. Do not wait for later proof-of-delivery completion to
 determine gate-arrival timeliness. SPLIT_PARENT rows are excluded; child lots are attributed to
 the original order. Active transit orders are excluded; show predicted-on-time separately; never
 mix historical arrivals and predictions in one denominator.
 Average delay = mean(max(0, arrived_at - promised_at)) over late gate-arrival-complete orders.
 Delay causes by route and by transporter: shipments affected and attributed hours per cause.
 delay_events do not overlap and their hours sum exactly to max(0, arrived_at - planned_arrival_at)
 within a documented rounding tolerance (seed validation test). Transporter analytics are by COMPANY, never by individual driver.
 Warning lead time = promised_at minus first High alert, only for shipments predicted late or
 breached, else N/A. Baseline "customers otherwise learn at breach" is a labelled assumption.

4.11 BUSINESS IMPACT (both panels labelled
 "MODELLED - ILLUSTRATIVE SCENARIO, NOT VERIFIED PLANT X OR LYB PERFORMANCE")
 Panel A (this dataset): hours avoided = E[late hours | Continue] - E[late hours | chosen];
 modelled cost difference = Total_Continue - Total_chosen; freight shown separately.
 Model expectations at approval time, not realised savings.
 Panel B (editable): affected = annual * delay_rate; mitigated = affected * mitigable_share;
 interventions = mitigated / success_rate; gross = mitigated * avoidable_hours * cost_per_late_hour;
 intervention_cost = interventions * avg_intervention_cost; net = gross - intervention_cost
 (may be negative; show it); break_even_cost_per_late_hour =
 (avg_intervention_cost / success_rate) / avoidable_hours. Validate shares and success rate in
 (0,1], rates and costs >= 0, volume > 0, hours > 0. Show every input and formula.

4.12 CLOCK
 simulation_state: sim_now, speed, paused, clock_version, global_seed. Single source of time.
 clock_version increments on every clock advance; shipment.state_version increments only on
 material shipment events. Every intervention snapshots all three relevant versions.
 UTC stored, Asia/Kolkata displayed. Default: paused, explicit advance.
 GET /api/simulation/clock; POST /api/simulation/clock/advance. advance runs ticks of at most
 5 simulated minutes, processing disruptions, milestones and telemetry chronologically, then
 recomputes predictions once. Auto-advance (E) uses ONE asyncio task. One uvicorn worker.
 SQLite: WAL on, PRAGMA foreign_keys=ON per connection via SQLAlchemy connect event.
 The simulator may auto-post ARRIVED_AT_CUSTOMER_GATE for seeded historical records; in the live demo the driver confirms. DELIVERED is a later proof-of-delivery event.

4.13 DATA
 Deterministic seed with one-command reset (python -m app.seed.reset) and a guarded endpoint.
 12-14 active shipments (including G1-G3 cases) and at least 150 historical delivered
 shipments over 8 weeks across at least 4 routes, 3 customers, 3 transporter companies, with
 deliberate fictional patterns (one transporter weak on one route; one recurring-congestion
 route; one customer with frequent urgent deliveries). Fictional names and generic
 coordinates only.

4.14 DATABASE
 users, customers, transporters, orders (promised_at, sla_penalty_per_late_hour, priority,
 revised_eta_communicated + _at), shipments (parent_shipment_id, lot_type, quantity_tonnes,
 planned_arrival_at, state, disposition including SPLIT_PARENT, state_version, last_telemetry_at), routes (alternative_of_route_id, alternative_entry_decision_node_id, alternative_rejoin_waypoint_id,
 cost_per_km, road_circuity_factor), route_waypoints (sequence, lat, lon, is_decision_node),
 shipment_events, delay_events, predictions, customer_inventory, alerts (dedupe_key,
 escalated_at, escalation_level, severity, read, acknowledged), interventions,
 intervention_scenarios, audit_events (append-only), simulation_state (with clock_version),
 interventions (shipment_state_version, assumptions_version, clock_version snapshots), business_assumptions
 (with assumptions_version). All with PK/FK/constraints/indexes, created_at/updated_at (UTC).
 SQLAlchemy create_all plus a seed script. No Alembic.

4.15 API (Pydantic is the source; export contracts/openapi.json)
 AUTH login, me. ORDERS get. CUSTOMER me/orders, me/shipments (customer-safe route and
 position data inside). TRANSPORTER me/shipments, POST shipments/{id}/milestones, POST .../pod.
 CONTROL TOWER overview, map-data (coordinator only). SHIPMENTS list, get, events,
 prediction (?history=true), recalculate. SIMULATION clock, advance, disruptions (create,
 list, end). WAR ROOM POST/GET shipments/{id}/scenarios, GET interventions,
 approve, reject. ALERTS list, acknowledge. ANALYTICS overview, delay-causes, routes,
 transporters, business-impact. ASSUMPTIONS GET/PUT. REFERENCE-DATA (for filters).
 ADMIN POST /api/admin/reset (only when DEMO_MODE=true, coordinator only). GET /health.
 Generate docs/API_ACCESS_MATRIX.md (role x endpoint x ownership) and test it with one
 parameterised test. Generate API and DB reference docs from code, not by hand.
 During Phase 0, stub routes serve fixtures so the frontend always calls the real URL.

4.16 SECURITY
 Argon2 via argon2-cffi (not passlib). JWT HS256, secret from environment, 60-minute expiry.
 Role and active flag re-read from the DB on every request. One central dependency enforces
 role and ownership; another user's resource returns 404, not 403. Customer allow-list schemas
 must NOT contain freight cost, penalty rate, stock-out rate, risk weights, other customers'
 data, internal option costs or transporter performance; a test asserts key absence on every
 customer endpoint. Pydantic bounds on every field. Audit events append-only with actor, role,
 action, entity, before/after JSON, simulation time, wall time. Login throttle: five failures
 per minute per username+IP (in-memory). Tokens in sessionStorage per tab; log in manually in
 each demo tab; record the XSS trade-off in KNOWN_LIMITATIONS. Demo credentials fictional,
 seeded only when DEMO_MODE=true, listed in README. .env.example committed, .env ignored.
 No tokens or passwords in logs.

4.17 FRONTEND (React, Vite, TypeScript, Tailwind, Recharts, Leaflet)
 At most seven views: 1 Login/role select; 2 Coordinator Control Tower (map + table + KPI
 cards + filters + alerts drawer); 3 Shipment Detail with ETA intelligence; 4 War Room (a plain
 comparison table first, polish later); 5 Customer Portal; 6 Transporter Portal; 7 Analytics
 (with intervention history tab and assumptions panel). Alerts are a drawer.
 Map: Leaflet vector layers (circleMarker/divIcon, never the default marker icon); OSM tiles
 optional; after three consecutive tileerror events remove them and show a labelled grid;
 caption always "Illustrative routes. Positions are simulated."
 Bundle fonts, icons and CSS locally; no CDN. FastAPI serves the production build with
 StaticFiles and SPA fallback, same origin. Navy/grey/white palette with blue, green, amber,
 red; never colour alone (labels and icons too). Loading, empty, error and stale states on
 every data view. Every KPI and chart reads the API; no decorative fake data. Accessibility
 basics: contrast, keyboard focus, labelled controls.

================================================================
5. WORK SEQUENCE AND SCHEDULE (H hours; scale proportionally; reserve rehearsal)
================================================================
 0-2    Phase 0 deliverables (STOP for approval).
 2-6    Foundation, models, deterministic seed, auth + RBAC, milestone APIs, Control Tower
        table and map, minimal customer and driver portals, engine v1 (ETA, stock, risk,
        Continue-vs-Reroute) with unit tests, simulator and clock.
 6-8    ORM-to-engine mapping, stored predictions, alerts, Shipment Detail, disruption presets.
        HOUR-8 TARGET on the real stack: three role logins; customer sees shipment; driver
        advances a milestone; disruption injected; ETA and risk change; coordinator alert
        appears; a basic Continue-vs-Reroute suggestion with a reason is shown.
 8-13   Full War Room: three scenarios, Split, constraints, recommendation, scenarios API,
        approve/reject, versioning, audit, War Room UI.
 13-17  Analytics, assumptions panel, history seed, KPI tests, stability (E), G2/G3.
 17-19  RBAC matrix test, security review, reset, map fallback, UX states, production build
        served by FastAPI, Playwright E2E, golden regression, 1.5 h responsible-AI evidence
        (confidence on every prediction, human approval, audit view, privacy statement,
        limitations).
 H-5    FEATURE FREEZE.   H-3  CODE FREEZE (P0 bug fixes only, Dev3 approval).
 Last 3 hours: docs, AI disclosure, architecture diagram export (Mermaid -> SVG, matching the
 running system), five timed rehearsals, backup demo video, Q&A drill. No new features.
 Human roles in parallel with the build: Dev1 reviews backend/data walkthroughs and tests
 RBAC by hand; Dev2 reviews UX and prepares slides and diagram; Dev3 owns golden scenarios,
 engine review, demo data, rehearsals and Q&A. Every member reads each phase walkthrough.

================================================================
6. GOLDEN SCENARIOS (inputs and ranges committed BEFORE tuning)
================================================================
Only distribution parameters may be tuned. Target ranges may NOT be edited. After tuning,
freeze parameters and measured outputs in docs/GOLDEN_BASELINE.md with a change log.
Targets are tuning aims for a fictional scenario, not empirical performance.

G1 flooding + low stock (main demo; expected REROUTE, STABLE):
 - Seeded LOADING; staged opening advances it to AT_PLANT_GATE; flooding injected while AT_PLANT_GATE;
   Reroute and Split both eligible at injection. alpha = 10%.
 - Stock: depletion S about 1-2 h after D, unloading u <= 1 h, with S - u >= D so a stock-out
   implies lateness.
 - Before injection: P(late) <= 15%, P(stockout) <= 5%, category LOW.
 - After injection, Continue: P(late) >= 70%, P(stockout) >= 30%, HIGH, P50 2-4 h after D.
 - Reroute: P(late) <= 30%, P(stockout) between 2% and 8%, freight > 0,
   Total_Reroute <= 0.6 * Total_Continue (so it survives all 16 stress cases).
 - Split: eligible, freight greater than Reroute.
 - Stability: STABLE (16/16).
G2 same disruption, high stock cover (expected CONTINUE, "No justified intervention"):
 - Continue P(late) >= 50%, Continue P(stockout) <= 5%, Continue feasible, and no option beats
   Continue by more than the tie-break threshold (state on expected totals). UI message:
   "Late is not the same as costly." Record, but do not assert, the stability label.
G3 no feasible option:
 - G1 inputs with alpha = 1% AND a max-incremental-freight cap set below Split's freight, so
   Continue and Reroute violate alpha and Split violates the cost cap. Expected: NO FEASIBLE
   OPTION - ESCALATE, violated constraints listed, CRITICAL alert to all coordinators.
Phase 0 must prove these coexist with concrete parameters before any engine tuning.

================================================================
7. TESTS AND ACCEPTANCE
================================================================
 Golden G1-G3 within the ranges above (asserted with tolerance).
 Metamorphic: longer disruption never lowers P(late); earlier deadline never lowers P(late);
 P10 <= P50 <= P90; reason chips sum to mean(T) - baseline; identical inputs and seeds give
 identical rounded results across two runs and two processes (same machine, same lockfile;
 compare rounded values, not raw bytes); doubling p changes Total only via the SLA term; an
 infeasible option is never recommended; a material change after scenario creation makes
 approve return 409; stale telemetry widens uncertainty but never fabricates an observed
 position; seed_pred != seed_truth; engine/ imports no fastapi, sqlalchemy or simulator.
 Stock: three hand-calculated examples (adequate stock; single lot after depletion; split
 where the urgent lot arrives after depletion) PLUS one where the remainder arrives BEFORE the
 urgent lot.
 Access: parameterised role/endpoint/ownership matrix; cross-customer and cross-transporter
 return 404; customer key-absence test.
 Workflow: approve and reject idempotent; override reason required; audit record written;
 customer notification generated; assumptions change supersedes open cases.
 Analytics: KPI buckets sum to active total; on-time per order; delay events sum to realised
 delay; transporter metrics by company.
 Performance targets (engineering, not official): overview with 80 shipments < 300 ms;
 scenario creation < 2 s.
 E2E: one Playwright test over the vertical slice using three browser contexts against the
 production build. Run the real demo with Wi-Fi disabled; also confirm the map with tiles.
 Vertical slice: customer views order > driver advances milestone > coordinator sees it >
 disruption injected > ETA and risk change > alert > War Room compares three > recommendation
 explained > coordinator approves > shipment updates > customer sees updated expected delivery
 with the original promise beside it > Panel A shows the modelled benefit.

================================================================
8. DEMO (10 minutes: 2 problem, 4 live, 2 defend, 2 Q&A)
================================================================
 Live 4:00 using G1, pre-staged tabs (coordinator, customer, driver; log in manually in each):
 staged opening 0:20; inject disruption and ETA/risk change 0:35; alert and open War Room
 0:20; scenario comparison 0:50; recommendation and stability 0:30; approve 0:15; customer tab
 0:25; dashboard Panel A and audit 0:25; close 0:20. Opening line: "Tracking tells you where
 the truck is. FlowGuard tells you whether it matters and what to do."
 Slides: problem and approach; WHERE AI IS USED / NOT USED; RESPONSIBLE CONTROLS (confidence,
 human approval, access, privacy, audit, limitations); impact indicator with formula and
 assumptions (labelled MODELLED); architecture diagram matching the build.
 Prepare the answer to "where is the AI?": the engine is a transparent stochastic simulation
 by design; there is no real telemetry history to train on and training on our own synthetic
 data would be circular. Prepare answers on ETA, risk, costs, stock-out, stability, wrong
 predictions, access/data protection, and a real-site pilot (shadow mode first).
 Deliver runbook, reset-and-verify checklist and a recorded fallback video.

================================================================
9. AI DISCLOSURE AND FINAL AUDIT
================================================================
 docs/AI_DISCLOSURE.md lists every AI tool actually used, anywhere in the project (including
 specification drafting and prompt review), with the model name as shown in the product, what
 it produced, and how humans verified it. Runtime generative AI: none. AI used: development
 assistance. Not AI: ETA, risk, cost, authorisation. Do not invent versions or tools.
 Before declaring completion: list the five most likely ways this project fails; audit official
 requirement completeness, ETA maths, stock maths, cost maths, infeasibility handling,
 stability, DB consistency, RBAC, customer privacy, dashboard correctness, offline operation,
 demo repeatability, AI disclosure and team explainability. Score strictly against the 100-point
 rubric. Produce a table: Requirement | PASS/PARTIAL/FAIL | test evidence | demo evidence |
 remaining limitation. Acceptance gates: (1) O1-O5 functional; (2) the three roles connected;
 (3) predictions come from the real engine; (4) scenarios internally consistent; (5) infeasible
 never recommended; (6) approval protected by both versions; (7) customer data separated;
 (8) dashboard from real records; (9) reproducible, offline-capable demo; (10) docs, disclosure,
 diagram, defence briefs ready. Evidence required for each.

================================================================
10. YOUR FIRST TASK
================================================================
Begin PHASE 0 ONLY. Read this prompt and the PDF. Produce the Phase 0 deliverables listed in
Section 2 and the hand-check results. Do not write application features. Then STOP and report:
what you verified, what is unresolved, contract and architecture decisions, testing strategy,
implementation risks, and a GO/NO-GO. Wait for explicit human approval.

Build a business solution, not a collection of screens.