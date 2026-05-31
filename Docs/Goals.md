# Goals

## Active Goal
SoundScrapper를 텍스트 검색 도구에서 사용자 취향을 학습하는 사운드 탐색 도구로 확장한다.

## Current State
- FastAPI + HTML/CSS/Vanilla JS MVP is implemented.
- Freesound search, preview playback, saved candidates, and SQLite persistence are implemented.
- Korean work-tool style UI is implemented.
- Waveform view, preview audio cache/proxy, browser-side waveform analysis, analysis persistence, feedback buttons, and feedback-based score adjustment are implemented.

## Near-Term Goals
- Verify waveform rendering with real Freesound preview audio in the user's local browser.
- Tune analysis labels and thresholds for leading silence, heaviness, sharpness, and empty/weak sounds.
- Show analysis-aware explanations on result cards so the score is easier to trust.
- Improve search ranking with title/description/tag weighting and negative keyword filtering.

## Later Goals
- Use Freesound analysis descriptors where they add useful signal.
- Add search history and prompt/result comparison.
- Add Unity export after local sound discovery workflow is stable.
- Add embedding or AI reranking only after enough feedback data exists.

## Explicit Non-Goals For Now
- YouTube download or automatic analysis.
- Heavy local AI model installation.
- Unity Editor integration.
- Automatic silence skipping during playback.

