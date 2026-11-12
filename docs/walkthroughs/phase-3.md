# Phase 3 walkthrough — frontend, end-to-end test, docs

## Dev2 area (frontend and UX)

- **Seven views** in `frontend/src/pages/`: Login, Control Tower, Shipment Detail, War Room, Customer Portal,
  Transporter Portal, Analytics. Alerts are a drawer.
- **Types come from the backend**: `npm run types` reads `contracts/openapi.json` and writes
  `src/api/schema.d.ts`. If the backend changes a field, the frontend build fails until fixed.
- **Shared components** (`components/ui.tsx`): every status has an icon **and** words (never colour alone);
  every data view has loading, empty and error states with a retry button.
- **Map** (`components/MapView.tsx`): drawn with vector shapes on a labelled grid, so it works offline.
  Optional OpenStreetMap background; if three tiles fail it switches back automatically. Stale vehicles are
  drawn faded and dashed, labelled "last REPORTED position".
- **Customer wording**: "Original promise" next to "Updated expected delivery"; "evaluating an alternate
  route" before approval; "Rerouting has been initiated" only after.
- **Production**: `npm run build` creates `frontend/dist`; FastAPI serves it, so one server and one address.

## Dev3 area (QA and demo)

- **End-to-end test** (`frontend/e2e/vertical-slice.spec.ts`): opens three separate browser sessions, runs the
  whole demo, takes the screenshots in `docs/screenshots/`, and **fails if any request leaves the computer**
  (offline proof).
- **Performance**: Control Tower with 80 live shipments ≈ 150–210 ms (target 300 ms), after batching the
  "latest prediction" lookups into one query.
- **Generated docs**: `scripts/gen_reference_docs.py` writes the access matrix, DB reference, fixtures and
  measured golden numbers from the code.

## Check yourself

1. How does the frontend stay in step with the backend's data shapes?
2. What happens to the map with no internet?
3. How does the E2E test prove the demo is offline-capable?
