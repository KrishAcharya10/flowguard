# Generative AI disclosure

Hackathon rule 5 (PDF p.9): *"Generative AI is allowed. Declare it. State where and how you used it.
Undeclared use costs 10 points. You must be able to explain every part of your code, data and design."*

## Summary

| Question | Answer |
| --- | --- |
| Runtime generative AI in FlowGuard? | **None.** No language model is called by the running application |
| What computes ETA and delay risk? | A transparent Monte Carlo simulation with declared distributions (`backend/app/engine/`). Not a trained ML model |
| What decides costs, constraints, recommendations, access? | Deterministic rules written in code and covered by tests |
| Was generative AI used to build it? | **Yes**, as a development assistant (below) |

## Tools used during development

| Tool (as shown in the product) | Where | What it produced | How humans verified it |
| --- | --- | --- | --- |
| Claude Code (VS Code extension), models **Claude Fable 5.2**, **Claude Opus 5.5** and **Claude Sonnet 5.5** (switched within the same project session) | Whole repository | Backend (engine, services, API, seed, tests), frontend (all views), scripts, and the docs in `docs/` and `README.md`. It also tuned one parameter (North Bypass speed, see `GOLDEN_BASELINE.md`) | 212 automated backend tests, 12 Playwright browser tests (3 role windows), 3 live-site checks, the Phase 0 hand-check script; **team review of each walkthrough in `docs/walkthroughs/` (to be signed off below)** |
| Claude Code plugins installed for the project (`code-review`, `feature-dev`, `pr-review-toolkit`, `skill-creator`, `hookify`, `claude-code-setup`, `ralph-loop`) | `.claude/settings.json` | Installed; **not used** to produce the current code. If the team uses them later, add a row here | — |

## To complete before presenting (team)

The AI assistant can only declare what happened in its own session. The team must add every other use:

- [ ] Tool(s) used to draft the master prompt / specification (`FLOWGUARD_FINAL_MASTER_PROMPT_V3_2.md`) and any
      earlier prompt versions, with the model name exactly as shown in that product.
- [ ] Any AI used for slides, images, the demo video or speaker notes.
- [ ] Any later AI review (e.g. an Opus read-only audit) or fixes.
- [ ] Sign-off: each developer has read the walkthroughs and their defence brief and can explain their module.

| Developer | Module reviewed | Signed (name, date) |
| --- | --- | --- |
| Dev1 | Backend, data, security | |
| Dev2 | Frontend, UX | |
| Dev3 | Engine, QA, demo | |

## What to say to judges ("where is the AI?")

"AI helped us write the code, and we declare it. The product itself deliberately uses no generative AI and no
trained model. The ETA engine is a transparent simulation: we have no real telemetry history to train on, and
training on our own synthetic data would be circular. Every number traces to a stated assumption, and a human
approves every intervention."
