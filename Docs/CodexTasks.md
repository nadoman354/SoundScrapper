# Codex Tasks

## Task 001 - Project Skeleton
Create the initial FastAPI plus static frontend project structure.

## Task 002 - Freesound Client
Implement a Freesound API client using `FREESOUND_API_KEY`.

## Task 003 - Search Endpoint
Add `POST /api/search` that accepts a prompt and returns normalized sound candidates.

## Task 004 - Result Cards
Render sound result cards with title, duration, license, tags, and audio preview.

## Task 005 - Save Candidates
Add SQLite storage for saved sound candidates.

## Task 006 - Ranking Rules
Add ranking based on tags, duration, license, and prompt keywords.

## Task 007 - Korean Workbench UI
Localize the app UI into Korean and improve the layout for result comparison.

## Task 008 - Waveform Inspection
Add per-card waveform generation, preview cache/proxy, and click-to-seek playback.

## Task 009 - Audio Analysis Persistence
Store waveform and analysis metrics such as RMS, peak, leading silence, low/mid/high ratios, heaviness, sharpness, and emptiness.

## Task 010 - User Feedback Learning
Add feedback buttons and use stored feedback as a lightweight score adjustment signal.

## Task 011 - Ranking Quality Tuning
Improve title/description/tag weighting, negative keywords, and analysis-aware score explanations.

## Task 012 - Future AI Reranker
Experiment with embedding or AI reranking only after enough feedback data exists.
