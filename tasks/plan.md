# Implementation Plan: FinPilot v3 — everything inside the Chrome extension

Source spec: `docs/spec.md` (section "v3: всё в расширении")
Deadline: Sun Nov 15, 23:59 ET. Plan written 05:57 ET.

## Overview
Move the whole product into a Chrome extension with no server. The extension holds the family's data
(profiles with PIN on one computer), runs our trained ML models in JavaScript, and uses Gemini only to
explain, chat and read files. Gemini is "taught" through context (family rules, examples from our datasets)
and gets our models as tools (function calling).

## Architecture Decisions
- **Engine = ES modules in `extension/lib/`** shared by the side panel and the background worker
  (`ml.js` models, `features.js` live features, `finance.js` money math, `verdict.js`, `store.js`, `gemini.js`).
  Rationale: one implementation, two UIs (panel + on-page card).
- **Models exported from Python to JSON** (`ml/export_extension.py`) and checked against Python test vectors.
  Compact text models re-evaluated: categorizer macro-F1 0.696 (big 0.692), price median error 38% (big 37%).
- **UI = Chrome Side Panel** (`panel.html`), replaces website + popup. Content script keeps the on-page card.
- **Storage = `chrome.storage.local`** (unlimitedStorage). Data never leaves the computer except to Gemini/PayPal when the user uses them.
- **Keys** (Gemini, PayPal Sandbox) entered in Settings, stored locally, never committed.
- **Testing:** a test page runs the same modules against Python test vectors; UI checked in the browser.

## Task List
Tracked in `tasks/todo.md`.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| JS port differs from Python (features, trees) | High — wrong verdicts | Test vectors from Python for every model and for live features on the demo family |
| Not enough time for all screens | High | Vertical slices in priority order; Phase 3 (PayPal) is cut first |
| Gemini free-tier rate limits / outages | Med | ML works without Gemini; chat falls back to the intent model; cache price opinions |
| Service-worker module limits in MV3 | Med | Background as `"type": "module"`; heavy work in the panel when open |
| Extension size (models ~7 MB) | Low | Fine for an unpacked extension |

## Open Questions
- None blocking. Room sync across computers is in "What's next".
