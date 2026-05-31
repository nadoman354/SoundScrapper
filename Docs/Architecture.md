# Architecture

## Overview

SoundScrapper starts as a local web app with a Python backend and static frontend.

```text
Browser UI
  -> FastAPI backend
  -> Freesound API
  -> Preview audio cache
  -> SQLite saved candidates, analyses, feedback
```

## Backend

The backend owns external API access, token handling, prompt parsing, ranking, and persistence.

- `backend.app.main`: FastAPI app and routes.
- `backend.app.config`: environment and path settings.
- `backend.app.freesound_client`: Freesound API calls and result normalization.
- `backend.app.prompt_parser`: prompt cleanup and keyword expansion.
- `backend.app.ranker`: deterministic MVP ranking rules.
- `backend.app.preview_cache`: Freesound preview audio validation and local cache.
- `backend.app.db`: SQLite schema for saved sounds, analyses, and feedback.
- `backend.app.schemas`: request and response models.

## Frontend

The frontend is static and served by FastAPI.

- `frontend/index.html`: app shell.
- `frontend/app.js`: API calls, UI rendering, Web Audio waveform analysis, and feedback actions.
- `frontend/style.css`: layout and visual styling.

## Data

- Saved sounds are stored in `saved_sounds` with the Freesound ID as a unique key.
- Waveform/audio metrics are stored in `sound_analyses`.
- User feedback is stored in `sound_feedback`.
- Tags and waveform buckets are stored as JSON text.

## Future Phases

- Search history.
- Freesound analysis descriptors.
- Analysis-aware ranking explanations.
- Search history and prompt comparison.
- Unity export into an `Assets/Audio` target folder.
- AI/embedding reranking after enough feedback data exists.
