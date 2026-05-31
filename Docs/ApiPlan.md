# API Plan

## `GET /health`

Response:

```json
{ "status": "ok" }
```

## `POST /api/search`

Request:

```json
{
  "prompt": "short heavy dark magic explosion",
  "license": "commercial",
  "min_duration": 0.1,
  "max_duration": 3.0,
  "page_size": 20
}
```

Response:

```json
{
  "query": "explosion boom impact magic spell fantasy dark deep short heavy low bass",
  "results": [
    {
      "id": 123,
      "name": "Dark Impact Boom",
      "username": "creator",
      "license": "Creative Commons 0",
      "duration": 0.8,
      "tags": ["dark", "impact", "magic"],
      "preview_url": "https://...",
      "url": "https://freesound.org/...",
      "description": "A dark impact sound.",
      "score": 87,
      "personal_score_adjustment": 4
    }
  ]
}
```

## `POST /api/saved-sounds`

Request body matches a sound result item. The Freesound ID is upserted.

## `GET /api/saved-sounds`

Returns saved sounds ordered by newest first.

## `GET /api/preview-audio/{sound_id}`

Query:

```text
preview_url=https://cdn.freesound.org/...
```

Returns cached Freesound preview audio. Only HTTPS Freesound preview hosts are accepted.

## `POST /api/preview-cache/{sound_id}`

Caches a Freesound preview URL and returns an app-local audio URL.

## `POST /api/sound-analyses`

Stores browser-computed waveform/audio metrics:

```json
{
  "id": 123,
  "preview_url": "https://...",
  "waveform": [0.1, 0.7, 1.0],
  "rms": 0.2,
  "peak": 0.9,
  "leading_silence_seconds": 0.15,
  "low_ratio": 0.5,
  "mid_ratio": 0.3,
  "high_ratio": 0.2,
  "spectral_centroid_hz": 1200,
  "heaviness_score": 70,
  "sharpness_score": 25,
  "emptiness_score": 10
}
```

## `GET /api/sound-analyses/{sound_id}`

Returns stored analysis data when available.

## `POST /api/feedback`

Stores user feedback for personalization.

```json
{
  "id": 123,
  "prompt": "short heavy dark magic explosion",
  "feedback_type": "heavy_good",
  "name": "Dark Impact Boom",
  "tags": ["dark", "impact", "magic"]
}
```
