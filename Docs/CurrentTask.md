# Current Task

## Goal
Stabilize the first enhanced Sound Scout workflow: Freesound search, Korean UI, waveform inspection, preview cache, and user feedback learning.

## Scope
- Keep the FastAPI + static frontend MVP working.
- Let users inspect preview waveforms from result cards.
- Cache Freesound preview audio through the backend.
- Store waveform/audio analysis metrics in SQLite.
- Store user feedback and use it as a lightweight personalization signal.
- Keep the app usable without introducing heavy AI or embedding dependencies.

## Out of Scope
- YouTube search or download.
- Unity integration.
- React migration.
- Electron packaging.
- Heavy AI model or embedding search.
- Automatic silence skipping.

## Acceptance Criteria
- `uvicorn backend.app.main:app --reload` starts the app.
- `/health` returns `{ "status": "ok" }`.
- The frontend can submit a search request.
- Search uses Freesound API token authentication.
- Saved sounds persist in SQLite.
- Result cards expose waveform and feedback controls.
- Preview audio can be cached/proxied safely from Freesound URLs.
- Analysis and feedback data persist in SQLite.
- Feedback can influence future result scores.
- Static analysis and tests are reported after implementation.
