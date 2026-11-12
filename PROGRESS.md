# PROGRESS

Last updated: 2026-11-12.

## Done
- [x] Phase 0: requirements extract, traceability, assumptions, golden scenarios, engine contracts, hand-check (29/29 GO).
- [x] Backend: models, deterministic seed (14 live + 160 historical), auth + RBAC, milestones, engine, stock, risk,
      War Room (3 options, constraints, recommendation, 16-case stability), lifecycle with version checks, alerts,
      simulator + clock, analytics, business impact, assumptions, audit, reset.
- [x] Frontend: 7 views, alerts drawer, offline map, generated API types, production build served by FastAPI.
- [x] Tests: 126 backend (incl. golden G1–G3, RBAC matrix, privacy, performance with 80 shipments);
      3 Playwright E2E tests (vertical slice with an offline assertion; demo guide jump + start).
- [x] Docs: specs, architecture (Mermaid + SVG), API access matrix and DB reference (generated), fixtures,
      golden baseline, known limitations, AI disclosure, demo runbook, walkthroughs, defence briefs, final audit.

- [x] Demo guide: 8 use cases with one-click setup (start / jump), presenter panel, custom disruption durations;
      split remainder keeps the original truck's delay; FLOW.md (recorded run of use cases 1 and 4).

- [x] Live operations: live sync (all roles), simulation control (start/pause/speed/auto-pause), new orders, driver
      breakdown/hazard reports, activity feed, redesigned coordinator / driver / customer portals.
- [x] Bonus features: gate slot booking (+ driver check-in), "Where is my order?" chatbot, invoice and proof-of-delivery
      upload / download with private storage, versions, verification and audit.
- [x] Delivery completion fix: the driver's arrived card opens with the hand-over form (receiver name + photo, or "Complete
      delivery without a document"); the coordinator can complete a delivery for the driver (Documents, Control Tower row).
- [x] Realistic names: Maharashtra places (Waluj to Pithampur / Amravati / Satara / Bhiwandi), invented companies and people,
      meaningful ids (`ORD-PTH-1116-01`), clearer demo guide (question, minutes, quick-start).
- [x] Visual redesign: design tokens, map-first Control Tower, new map (OpenStreetMap tiles by default, automatic offline
      "Illustrative logistics network", custom truck markers, clustering, active-reroute and disruption overlays, legend,
      full screen, filters, vehicle panel), War Room scenario cards, shipment-detail map, login, driver next-step-first.
- [x] Tests: 217 backend, 20 browser (incl. map online/offline, reroute, layouts, POD completion), 3 live-site checks.

## Next (humans)
1. Each developer reads `docs/walkthroughs/` and their `docs/DEFENCE_BRIEF_DEVn.md`, then signs `docs/AI_DISCLOSURE.md`.
2. Add any other AI tools the team used (master prompt drafting, slides) to `docs/AI_DISCLOSURE.md`.
3. Build slides from the outline in `docs/DEMO_RUNBOOK.md` §3.
4. Five timed rehearsals; record the backup video.
5. Optional: Opus read-only audit, then targeted fixes.

## Blockers
None.

## Test status
Backend 217 passed · hand-check GO · frontend build OK · lint 0 errors · browser tests 20 passed · live-site check 3 passed.

## Open decisions / notes
- The only external call is the optional OpenStreetMap tile request (user decision, replaces the old "no external service"
  rule; see `CLAUDE.md`, `docs/KNOWN_LIMITATIONS.md`). Offline, the map falls back to a local drawing automatically.
- The master prompt asked to stop after Phase 0 for approval. The user instructed "start now and complete", so the
  build continued; Phase 0 outputs remain for review.
- One parameter tuned (Dhule Bypass speed 44 → 42 km/h), logged in `docs/GOLDEN_BASELINE.md`.
- Not built: gate slot booking, chatbot, POD file upload, scope class E features.
