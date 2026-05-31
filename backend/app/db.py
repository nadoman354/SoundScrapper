from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.app.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    SoundAnalysis,
    SavedSound,
    SoundSearchResult,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_sounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    freesound_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    duration REAL NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    preview_url TEXT,
    url TEXT,
    description TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sound_analyses (
    freesound_id INTEGER PRIMARY KEY,
    preview_url TEXT NOT NULL,
    waveform TEXT NOT NULL DEFAULT '[]',
    duration REAL NOT NULL DEFAULT 0,
    rms REAL NOT NULL DEFAULT 0,
    peak REAL NOT NULL DEFAULT 0,
    leading_silence_seconds REAL NOT NULL DEFAULT 0,
    low_ratio REAL NOT NULL DEFAULT 0,
    mid_ratio REAL NOT NULL DEFAULT 0,
    high_ratio REAL NOT NULL DEFAULT 0,
    spectral_centroid_hz REAL NOT NULL DEFAULT 0,
    heaviness_score INTEGER NOT NULL DEFAULT 0,
    sharpness_score INTEGER NOT NULL DEFAULT 0,
    emptiness_score INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sound_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    freesound_id INTEGER NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    feedback_type TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def initialize_db(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA)
        connection.commit()


def save_sound(database_path: Path, sound: SoundSearchResult) -> SavedSound:
    initialize_db(database_path)
    tags = json.dumps(sound.tags, ensure_ascii=False)

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            INSERT INTO saved_sounds (
                freesound_id, name, username, license, duration, tags,
                preview_url, url, description, score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(freesound_id) DO UPDATE SET
                name = excluded.name,
                username = excluded.username,
                license = excluded.license,
                duration = excluded.duration,
                tags = excluded.tags,
                preview_url = excluded.preview_url,
                url = excluded.url,
                description = excluded.description,
                score = excluded.score,
                saved_at = CURRENT_TIMESTAMP
            """,
            (
                sound.id,
                sound.name,
                sound.username,
                sound.license,
                sound.duration,
                tags,
                sound.preview_url,
                sound.url,
                sound.description,
                sound.score,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM saved_sounds WHERE freesound_id = ?",
            (sound.id,),
        ).fetchone()

    return _row_to_saved_sound(row)


def list_saved_sounds(database_path: Path) -> list[SavedSound]:
    initialize_db(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM saved_sounds ORDER BY saved_at DESC, id DESC"
        ).fetchall()

    return [_row_to_saved_sound(row) for row in rows]


def save_analysis(database_path: Path, analysis: SoundAnalysis) -> SoundAnalysis:
    initialize_db(database_path)
    waveform = json.dumps(analysis.waveform)

    with sqlite3.connect(database_path) as connection:
        _ensure_analysis_duration_column(connection)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            INSERT INTO sound_analyses (
                freesound_id, preview_url, waveform, duration, rms, peak, leading_silence_seconds,
                low_ratio, mid_ratio, high_ratio, spectral_centroid_hz,
                heaviness_score, sharpness_score, emptiness_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(freesound_id) DO UPDATE SET
                preview_url = excluded.preview_url,
                waveform = excluded.waveform,
                duration = excluded.duration,
                rms = excluded.rms,
                peak = excluded.peak,
                leading_silence_seconds = excluded.leading_silence_seconds,
                low_ratio = excluded.low_ratio,
                mid_ratio = excluded.mid_ratio,
                high_ratio = excluded.high_ratio,
                spectral_centroid_hz = excluded.spectral_centroid_hz,
                heaviness_score = excluded.heaviness_score,
                sharpness_score = excluded.sharpness_score,
                emptiness_score = excluded.emptiness_score,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                analysis.id,
                analysis.preview_url,
                waveform,
                analysis.duration,
                analysis.rms,
                analysis.peak,
                analysis.leading_silence_seconds,
                analysis.low_ratio,
                analysis.mid_ratio,
                analysis.high_ratio,
                analysis.spectral_centroid_hz,
                analysis.heaviness_score,
                analysis.sharpness_score,
                analysis.emptiness_score,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM sound_analyses WHERE freesound_id = ?",
            (analysis.id,),
        ).fetchone()

    return _row_to_analysis(row)


def get_analysis(database_path: Path, freesound_id: int) -> SoundAnalysis | None:
    initialize_db(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM sound_analyses WHERE freesound_id = ?",
            (freesound_id,),
        ).fetchone()
    return _row_to_analysis(row) if row else None


def save_feedback(database_path: Path, feedback: FeedbackRequest) -> FeedbackResponse:
    initialize_db(database_path)
    tags = json.dumps(feedback.tags, ensure_ascii=False)

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            """
            INSERT INTO sound_feedback (freesound_id, prompt, feedback_type, name, tags)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                feedback.id,
                feedback.prompt,
                feedback.feedback_type,
                feedback.name,
                tags,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM sound_feedback WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return FeedbackResponse(
        id=row["id"],
        freesound_id=row["freesound_id"],
        feedback_type=row["feedback_type"],
        created_at=row["created_at"],
    )


def feedback_adjustment(database_path: Path, result: SoundSearchResult) -> int:
    initialize_db(database_path)
    tags = {tag.lower() for tag in result.tags}
    name_terms = {term for term in result.name.lower().replace("_", " ").split() if len(term) > 2}
    adjustment = 0

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        exact_rows = connection.execute(
            "SELECT feedback_type FROM sound_feedback WHERE freesound_id = ?",
            (result.id,),
        ).fetchall()
        related_rows = connection.execute(
            """
            SELECT feedback_type, name, tags
            FROM sound_feedback
            ORDER BY created_at DESC
            LIMIT 120
            """
        ).fetchall()

    for row in exact_rows:
        adjustment += _feedback_weight(row["feedback_type"]) * 3

    for row in related_rows:
        feedback_tags = {tag.lower() for tag in json.loads(row["tags"] or "[]")}
        feedback_name_terms = {
            term for term in row["name"].lower().replace("_", " ").split() if len(term) > 2
        }
        overlap = len(tags & feedback_tags) + len(name_terms & feedback_name_terms)
        if overlap:
            adjustment += min(2, overlap) * _feedback_weight(row["feedback_type"])

    return max(-25, min(25, adjustment))


def _row_to_saved_sound(row: sqlite3.Row) -> SavedSound:
    tags = json.loads(row["tags"]) if row["tags"] else []
    return SavedSound(
        saved_id=row["id"],
        saved_at=row["saved_at"],
        id=row["freesound_id"],
        name=row["name"],
        username=row["username"],
        license=row["license"],
        duration=row["duration"],
        tags=tags,
        preview_url=row["preview_url"],
        url=row["url"],
        description=row["description"],
        score=row["score"],
    )


def _row_to_analysis(row: sqlite3.Row) -> SoundAnalysis:
    return SoundAnalysis(
        id=row["freesound_id"],
        preview_url=row["preview_url"],
        waveform=json.loads(row["waveform"]) if row["waveform"] else [],
        duration=row["duration"],
        rms=row["rms"],
        peak=row["peak"],
        leading_silence_seconds=row["leading_silence_seconds"],
        low_ratio=row["low_ratio"],
        mid_ratio=row["mid_ratio"],
        high_ratio=row["high_ratio"],
        spectral_centroid_hz=row["spectral_centroid_hz"],
        heaviness_score=row["heaviness_score"],
        sharpness_score=row["sharpness_score"],
        emptiness_score=row["emptiness_score"],
        updated_at=row["updated_at"],
    )


def _feedback_weight(feedback_type: str) -> int:
    weights = {
        "good": 4,
        "heavy_good": 5,
        "magic_feel": 5,
        "bad": -5,
        "too_sharp": -4,
    }
    return weights.get(feedback_type, 0)


def _ensure_analysis_duration_column(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(sound_analyses)").fetchall()
    }
    if "duration" not in columns:
        connection.execute(
            "ALTER TABLE sound_analyses ADD COLUMN duration REAL NOT NULL DEFAULT 0"
        )
