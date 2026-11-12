# Defence brief — Dev2 (frontend, UX, slides, diagram)

## Your modules
`frontend/src/` (pages, components, api client), `frontend/e2e/`, `docs/architecture.mmd/.svg`, slides.

## Key ideas in words
- **One honest view per user**: the coordinator sees probabilities, costs and options; the customer sees the
  original promise, an updated expected delivery with a likely range, a Low/Medium/High label and a plain
  reason; the driver sees one big "confirm next step" button.
- **Explain, don't just display**: reason chips show hours per cause; the War Room lists why, ETA difference,
  main risk, trade-off and assumptions; the stability card says "holds in 16 of 16".
- **Honest labels**: "MODELLED" on every money figure that comes from assumptions; "an estimate, not a
  guarantee" for customers; "Illustrative routes. Positions are simulated." on every map.
- **Accessibility**: icon + text for every status, visible focus ring, labelled inputs, alert/status roles,
  loading/empty/error states with retry.
- **Offline**: no CDN, system fonts, Unicode icons, vector map on a grid; tiles optional with auto-fallback.

## Numbers to know
7 views; 1 end-to-end test with 3 browser sessions; 0 external requests during the demo (asserted).

## Three hard questions
1. **"Why not show the customer the probability?"** A percentage invites false precision and disputes. They
   get a Low/Medium/High label, a time range and the reason; coordinators get the numbers.
2. **"Why a grid instead of a real map?"** The demo must work with Wi-Fi off and must not imply real roads.
   Real tiles can be switched on, and the app falls back automatically if they fail.
3. **"How would a colour-blind user read status?"** Every badge has an icon and a word (✓ Low, ▲ Medium,
   ● High, ⚠ Stale); colour is only a second cue.
