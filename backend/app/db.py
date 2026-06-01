from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from backend.app.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    SavedFolder,
    SavedSound,
    SavedSoundUpdate,
    SoundAnalysis,
    SoundSearchResult,
)

DEFAULT_WORKSPACE_ID = "local"


@dataclass(frozen=True)
class FreesoundOAuthToken:
    workspace_id: str
    access_token: str
    refresh_token: str
    expires_at: int
    username: str = ""

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_sounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'local',
    freesound_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    duration REAL NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    preview_url TEXT,
    url TEXT,
    description TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    source_provider TEXT NOT NULL DEFAULT 'freesound',
    source_id TEXT NOT NULL DEFAULT '',
    source_url TEXT,
    license_url TEXT,
    creator_url TEXT,
    attribution_text TEXT,
    download_url TEXT,
    download_allowed INTEGER NOT NULL DEFAULT 1,
    download_count INTEGER,
    note TEXT NOT NULL DEFAULT '',
    fit_rating INTEGER,
    folder TEXT NOT NULL DEFAULT '',
    labels TEXT NOT NULL DEFAULT '[]',
    download_filename TEXT NOT NULL DEFAULT '',
    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS saved_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL DEFAULT 'local',
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    workspace_id TEXT NOT NULL DEFAULT 'local',
    freesound_id INTEGER NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    feedback_type TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    source_provider TEXT NOT NULL DEFAULT 'freesound',
    source_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS freesound_oauth_tokens (
    workspace_id TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL DEFAULT 0,
    username TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def initialize_db(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA)
        _ensure_analysis_duration_column(connection)
        _ensure_saved_source_columns(connection)
        _ensure_saved_metadata_columns(connection)
        _ensure_workspace_columns(connection)
        _ensure_freesound_oauth_table(connection)
        _rebuild_saved_sounds_if_needed(connection)
        _rebuild_saved_folders_if_needed(connection)
        _ensure_workspace_indexes(connection)
        _ensure_saved_folder_table(connection)
        _sync_existing_saved_folders(connection)
        _ensure_feedback_source_columns(connection)
        connection.commit()


def save_sound(
    database_path: Path,
    sound: SoundSearchResult,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> SavedSound:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    tags = json.dumps(sound.tags, ensure_ascii=False)
    source_provider = sound.source_provider or "freesound"
    source_id = sound.source_id or str(sound.id)

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            INSERT INTO saved_sounds (
                workspace_id, freesound_id, name, username, license, duration, tags,
                preview_url, url, description, score, source_provider, source_id,
                source_url, license_url, creator_url, attribution_text, download_url,
                download_allowed, download_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, source_provider, source_id) DO UPDATE SET
                freesound_id = excluded.freesound_id,
                name = excluded.name,
                username = excluded.username,
                license = excluded.license,
                duration = excluded.duration,
                tags = excluded.tags,
                preview_url = excluded.preview_url,
                url = excluded.url,
                description = excluded.description,
                score = excluded.score,
                source_url = excluded.source_url,
                license_url = excluded.license_url,
                creator_url = excluded.creator_url,
                attribution_text = excluded.attribution_text,
                download_url = excluded.download_url,
                download_allowed = excluded.download_allowed,
                download_count = excluded.download_count,
                saved_at = CURRENT_TIMESTAMP
            """,
            (
                workspace_id,
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
                source_provider,
                source_id,
                sound.source_url,
                sound.license_url,
                sound.creator_url,
                sound.attribution_text,
                sound.download_url,
                int(sound.download_allowed),
                sound.download_count,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT
                saved_sounds.*,
                (
                    SELECT GROUP_CONCAT(DISTINCT feedback_type)
                    FROM sound_feedback
                    WHERE sound_feedback.workspace_id = saved_sounds.workspace_id
                        AND sound_feedback.source_provider = saved_sounds.source_provider
                        AND sound_feedback.source_id = saved_sounds.source_id
                ) AS feedback_types
            FROM saved_sounds
            WHERE workspace_id = ? AND source_provider = ? AND source_id = ?
            """,
            (workspace_id, source_provider, source_id),
        ).fetchone()

    return _row_to_saved_sound(row)


def list_saved_sounds(
    database_path: Path,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> list[SavedSound]:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                saved_sounds.*,
                (
                    SELECT GROUP_CONCAT(DISTINCT feedback_type)
                    FROM sound_feedback
                    WHERE sound_feedback.workspace_id = saved_sounds.workspace_id
                        AND sound_feedback.source_provider = saved_sounds.source_provider
                        AND sound_feedback.source_id = saved_sounds.source_id
                ) AS feedback_types
            FROM saved_sounds
            WHERE saved_sounds.workspace_id = ?
            ORDER BY saved_at DESC, id DESC
            """,
            (workspace_id,),
        ).fetchall()

    return [_row_to_saved_sound(row) for row in rows]


def update_saved_sound(
    database_path: Path,
    saved_id: int,
    update: SavedSoundUpdate,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> SavedSound | None:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    fields_set = _model_fields_set(update)
    assignments: list[str] = []
    values: list[object] = []
    folder_name: str | None = None

    if "note" in fields_set:
        assignments.append("note = ?")
        values.append(update.note or "")
    if "fit_rating" in fields_set:
        assignments.append("fit_rating = ?")
        values.append(update.fit_rating)
    if "folder" in fields_set:
        folder_name = _normalize_folder_name(update.folder or "")
        assignments.append("folder = ?")
        values.append(folder_name)
    if "labels" in fields_set:
        assignments.append("labels = ?")
        values.append(json.dumps(_clean_labels(update.labels or []), ensure_ascii=False))
    if "download_filename" in fields_set:
        assignments.append("download_filename = ?")
        values.append((update.download_filename or "").strip())

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        if assignments:
            if "folder" in fields_set and folder_name:
                _ensure_folder_named(connection, folder_name, workspace_id)
            values.extend([saved_id, workspace_id])
            connection.execute(
                f"""
                UPDATE saved_sounds
                SET {', '.join(assignments)}
                WHERE id = ? AND workspace_id = ?
                """,
                values,
            )
            connection.commit()

        row = connection.execute(
            """
            SELECT
                saved_sounds.*,
                (
                    SELECT GROUP_CONCAT(DISTINCT feedback_type)
                    FROM sound_feedback
                    WHERE sound_feedback.workspace_id = saved_sounds.workspace_id
                        AND sound_feedback.source_provider = saved_sounds.source_provider
                        AND sound_feedback.source_id = saved_sounds.source_id
                ) AS feedback_types
            FROM saved_sounds
            WHERE id = ? AND workspace_id = ?
            """,
            (saved_id, workspace_id),
        ).fetchone()

    return _row_to_saved_sound(row) if row else None


def delete_saved_sound(
    database_path: Path,
    saved_id: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> bool:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM saved_sounds WHERE id = ? AND workspace_id = ?",
            (saved_id, workspace_id),
        )
        connection.commit()
        return cursor.rowcount > 0


def list_saved_folders(
    database_path: Path,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> list[SavedFolder]:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                saved_folders.*,
                COALESCE(folder_counts.sound_count, 0) AS sound_count
            FROM saved_folders
            LEFT JOIN (
                SELECT folder, COUNT(*) AS sound_count
                FROM saved_sounds
                WHERE workspace_id = ? AND folder <> ''
                GROUP BY folder
            ) AS folder_counts
                ON folder_counts.folder = saved_folders.name
            WHERE saved_folders.workspace_id = ?
            ORDER BY saved_folders.sort_order ASC, LOWER(saved_folders.name) ASC
            """,
            (workspace_id, workspace_id),
        ).fetchall()

    return [_row_to_saved_folder(row) for row in rows]


def create_saved_folder(
    database_path: Path,
    name: str,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> SavedFolder:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    folder_name = _normalize_folder_name(name)
    if not folder_name:
        raise ValueError("Folder name is required.")

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        existing = _folder_row_by_name(connection, folder_name, workspace_id)
        if existing:
            return _row_to_saved_folder(existing)

        sort_order = connection.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM saved_folders WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()[0]
        cursor = connection.execute(
            "INSERT INTO saved_folders (workspace_id, name, sort_order) VALUES (?, ?, ?)",
            (workspace_id, folder_name, sort_order),
        )
        connection.commit()
        row = _folder_row_by_id(connection, cursor.lastrowid, workspace_id)

    return _row_to_saved_folder(row)


def rename_saved_folder(
    database_path: Path,
    folder_id: int,
    name: str,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> SavedFolder | None:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    folder_name = _normalize_folder_name(name)
    if not folder_name:
        raise ValueError("Folder name is required.")

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        current = _folder_row_by_id(connection, folder_id, workspace_id)
        if not current:
            return None

        old_name = current["name"]
        existing = _folder_row_by_name(connection, folder_name, workspace_id)
        if existing and existing["id"] != folder_id:
            connection.execute(
                "UPDATE saved_sounds SET folder = ? WHERE workspace_id = ? AND folder = ?",
                (folder_name, workspace_id, old_name),
            )
            connection.execute(
                "DELETE FROM saved_folders WHERE id = ? AND workspace_id = ?",
                (folder_id, workspace_id),
            )
            connection.commit()
            row = _folder_row_by_id(connection, existing["id"], workspace_id)
            return _row_to_saved_folder(row)

        connection.execute(
            "UPDATE saved_folders SET name = ? WHERE id = ? AND workspace_id = ?",
            (folder_name, folder_id, workspace_id),
        )
        connection.execute(
            "UPDATE saved_sounds SET folder = ? WHERE workspace_id = ? AND folder = ?",
            (folder_name, workspace_id, old_name),
        )
        connection.commit()
        row = _folder_row_by_id(connection, folder_id, workspace_id)

    return _row_to_saved_folder(row)


def delete_saved_folder(
    database_path: Path,
    folder_id: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> bool:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        current = _folder_row_by_id(connection, folder_id, workspace_id)
        if not current:
            return False
        connection.execute(
            "UPDATE saved_sounds SET folder = '' WHERE workspace_id = ? AND folder = ?",
            (workspace_id, current["name"]),
        )
        cursor = connection.execute(
            "DELETE FROM saved_folders WHERE id = ? AND workspace_id = ?",
            (folder_id, workspace_id),
        )
        connection.commit()
        return cursor.rowcount > 0


def save_freesound_oauth_token(
    database_path: Path,
    token: FreesoundOAuthToken,
) -> FreesoundOAuthToken:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(token.workspace_id)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            INSERT INTO freesound_oauth_tokens (
                workspace_id, access_token, refresh_token, expires_at, username
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at,
                username = excluded.username,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                workspace_id,
                token.access_token,
                token.refresh_token,
                int(token.expires_at),
                token.username or "",
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM freesound_oauth_tokens WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
    return _row_to_freesound_token(row)


def get_freesound_oauth_token(
    database_path: Path,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> FreesoundOAuthToken | None:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM freesound_oauth_tokens WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
    return _row_to_freesound_token(row) if row else None


def delete_freesound_oauth_token(
    database_path: Path,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> bool:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM freesound_oauth_tokens WHERE workspace_id = ?",
            (workspace_id,),
        )
        connection.commit()
        return cursor.rowcount > 0


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


def save_feedback(
    database_path: Path,
    feedback: FeedbackRequest,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> FeedbackResponse:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    tags = json.dumps(feedback.tags, ensure_ascii=False)
    source_provider = feedback.source_provider or "freesound"
    source_id = feedback.source_id or str(feedback.id)

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        exclusive_types = _exclusive_feedback_types(feedback.feedback_type)
        if exclusive_types:
            connection.execute(
                _delete_feedback_sql(len(exclusive_types)),
                (workspace_id, source_provider, source_id, *exclusive_types),
            )

        connection.execute(
            """
            DELETE FROM sound_feedback
            WHERE workspace_id = ? AND source_provider = ? AND source_id = ? AND feedback_type = ?
            """,
            (workspace_id, source_provider, source_id, feedback.feedback_type),
        )

        if not feedback.active:
            connection.commit()
            return FeedbackResponse(
                id=0,
                freesound_id=feedback.id,
                feedback_type=feedback.feedback_type,
                active=False,
                created_at="",
            )

        cursor = connection.execute(
            """
            INSERT INTO sound_feedback (
                workspace_id, freesound_id, prompt, feedback_type, name, tags,
                source_provider, source_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                feedback.id,
                feedback.prompt,
                feedback.feedback_type,
                feedback.name,
                tags,
                source_provider,
                source_id,
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
        active=True,
        created_at=row["created_at"],
    )


def feedback_adjustment(
    database_path: Path,
    result: SoundSearchResult,
    analysis: SoundAnalysis | None = None,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> int:
    initialize_db(database_path)
    workspace_id = _normalize_workspace_id(workspace_id)
    tags = {tag.lower() for tag in result.tags}
    name_terms = {term for term in result.name.lower().replace("_", " ").split() if len(term) > 2}
    source_provider = result.source_provider or "freesound"
    source_id = result.source_id or str(result.id)
    adjustment = 0

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        exact_rows = connection.execute(
            """
            SELECT feedback_type
            FROM sound_feedback
            WHERE workspace_id = ? AND source_provider = ? AND source_id = ?
            """,
            (workspace_id, source_provider, source_id),
        ).fetchall()
        related_rows = connection.execute(
            """
            SELECT
                sound_feedback.feedback_type,
                sound_feedback.name,
                sound_feedback.tags,
                sound_analyses.duration,
                sound_analyses.waveform,
                sound_analyses.leading_silence_seconds,
                sound_analyses.low_ratio,
                sound_analyses.high_ratio,
                sound_analyses.heaviness_score,
                sound_analyses.sharpness_score,
                sound_analyses.emptiness_score
            FROM sound_feedback
            LEFT JOIN sound_analyses
                ON sound_feedback.freesound_id = sound_analyses.freesound_id
            WHERE sound_feedback.workspace_id = ?
            ORDER BY sound_feedback.created_at DESC
            LIMIT 120
            """,
            (workspace_id,),
        ).fetchall()

    for row in exact_rows:
        adjustment += _feedback_weight(row["feedback_type"]) * 3

    related_positive = 0
    related_negative = 0
    for row in related_rows:
        related_adjustment = _related_feedback_adjustment(row, tags, name_terms, analysis)
        if related_adjustment > 0:
            related_positive += related_adjustment
        elif related_adjustment < 0:
            related_negative += related_adjustment

    adjustment += min(18, related_positive)
    adjustment += max(-10, related_negative)

    return max(-25, min(25, adjustment))


def _row_to_saved_sound(row: sqlite3.Row) -> SavedSound:
    tags = json.loads(row["tags"]) if row["tags"] else []
    labels = json.loads(row["labels"]) if "labels" in row.keys() and row["labels"] else []
    feedback_types = []
    if "feedback_types" in row.keys() and row["feedback_types"]:
        feedback_types = [item for item in row["feedback_types"].split(",") if item]
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
        feedback_types=feedback_types,
        source_provider=row["source_provider"],
        source_id=row["source_id"],
        source_url=row["source_url"],
        license_url=row["license_url"],
        creator_url=row["creator_url"],
        attribution_text=row["attribution_text"],
        download_url=row["download_url"],
        download_allowed=bool(row["download_allowed"]),
        download_count=row["download_count"] if "download_count" in row.keys() else None,
        note=row["note"] if "note" in row.keys() else "",
        fit_rating=row["fit_rating"] if "fit_rating" in row.keys() else None,
        folder=row["folder"] if "folder" in row.keys() else "",
        labels=labels,
        download_filename=row["download_filename"] if "download_filename" in row.keys() else "",
    )


def _row_to_saved_folder(row: sqlite3.Row) -> SavedFolder:
    return SavedFolder(
        folder_id=row["id"],
        name=row["name"],
        sort_order=row["sort_order"],
        sound_count=row["sound_count"] if "sound_count" in row.keys() else 0,
        created_at=row["created_at"],
    )


def _row_to_freesound_token(row: sqlite3.Row) -> FreesoundOAuthToken:
    return FreesoundOAuthToken(
        workspace_id=row["workspace_id"],
        access_token=row["access_token"],
        refresh_token=row["refresh_token"],
        expires_at=int(row["expires_at"]),
        username=row["username"] if "username" in row.keys() else "",
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
        "game_like": 5,
        "asset_ready": 5,
        "heavy_good": 5,
        "sharp_good": 4,
        "clean_good": 4,
        "easy_cut": 4,
        "loop_good": 3,
        "magic_feel": 4,
        "bad": -5,
        "noise_bad": -5,
        "leading_silence_bad": -4,
        "too_sharp": -4,
        "too_loud": -4,
        "too_long": -3,
        "low_quality": -4,
        "wrong_mood": -3,
        "license_risky": -4,
    }
    return weights.get(feedback_type, 0)


def _related_feedback_adjustment(
    row: sqlite3.Row,
    tags: set[str],
    name_terms: set[str],
    analysis: SoundAnalysis | None,
) -> int:
    feedback_tags = {tag.lower() for tag in json.loads(row["tags"] or "[]")}
    feedback_name_terms = {
        term for term in row["name"].lower().replace("_", " ").split() if len(term) > 2
    }
    overlap = len(tags & feedback_tags) + len(name_terms & feedback_name_terms)
    adjustment = 0

    if overlap:
        adjustment += min(2, overlap) * _related_feedback_weight(row["feedback_type"])

    analysis_adjustment = 0
    if analysis:
        analysis_adjustment = _analysis_feedback_adjustment(row, analysis)
        adjustment += analysis_adjustment

    stored_waveform = json.loads(row["waveform"] or "[]") if row["waveform"] else []
    has_second_signal = overlap > 0 or analysis_adjustment != 0
    if (
        analysis
        and stored_waveform
        and has_second_signal
        and _waveform_profile_similarity(stored_waveform, analysis.waveform) >= 0.88
    ):
        adjustment += 2 if _feedback_weight(row["feedback_type"]) > 0 else -1

    return adjustment


def _related_feedback_weight(feedback_type: str) -> int:
    if feedback_type == "bad":
        return -2
    return _feedback_weight(feedback_type)


def _analysis_feedback_adjustment(row: sqlite3.Row, analysis: SoundAnalysis) -> int:
    feedback_type = row["feedback_type"]
    adjustment = 0

    if feedback_type == "heavy_good" and analysis.heaviness_score >= 60:
        adjustment += 3
    elif feedback_type == "sharp_good" and 45 <= analysis.sharpness_score <= 82:
        adjustment += 3
    elif feedback_type == "too_sharp" and analysis.sharpness_score >= 75:
        adjustment -= 4
    elif feedback_type == "too_loud" and (analysis.peak >= 0.98 or analysis.rms >= 0.32):
        adjustment -= 4
    elif feedback_type == "too_long" and analysis.duration >= 8:
        adjustment -= 3
    elif feedback_type == "low_quality" and (
        analysis.emptiness_score >= 55 or analysis.peak < 0.12
    ):
        adjustment -= 3
    elif feedback_type == "clean_good" and analysis.emptiness_score <= 18:
        adjustment += 2
    elif feedback_type == "noise_bad" and analysis.emptiness_score >= 35:
        adjustment -= 3
    elif feedback_type == "leading_silence_bad" and analysis.leading_silence_seconds >= 0.45:
        adjustment -= 3
    elif feedback_type == "easy_cut" and _estimate_waveform_events(analysis.waveform) >= 1:
        adjustment += 3
    elif feedback_type == "loop_good" and analysis.duration >= 4:
        adjustment += 2
    elif feedback_type in {"asset_ready", "game_like"} and _is_asset_ready_analysis(analysis):
        adjustment += 2

    return adjustment


def _exclusive_feedback_types(feedback_type: str) -> tuple[str, ...]:
    if feedback_type in {"good", "bad"}:
        return ("good", "bad")
    return ()


def _delete_feedback_sql(type_count: int) -> str:
    placeholders = ", ".join("?" for _ in range(type_count))
    return f"""
        DELETE FROM sound_feedback
        WHERE workspace_id = ?
            AND source_provider = ?
            AND source_id = ?
            AND feedback_type IN ({placeholders})
    """


def _is_asset_ready_analysis(analysis: SoundAnalysis) -> bool:
    return (
        analysis.leading_silence_seconds <= 0.25
        and analysis.emptiness_score <= 25
        and analysis.duration <= 8
    )


def _estimate_waveform_events(waveform: list[float]) -> int:
    if not waveform:
        return 0

    peak = max(waveform)
    if peak < 0.12:
        return 0

    threshold = max(0.18, peak * 0.45)
    quiet_threshold = max(0.08, threshold * 0.4)
    events = 0
    in_event = False
    quiet_run = 0

    for value in waveform:
        if value >= threshold:
            if not in_event:
                events += 1
                in_event = True
            quiet_run = 0
        elif in_event and value <= quiet_threshold:
            quiet_run += 1
            if quiet_run >= 2:
                in_event = False
                quiet_run = 0
        elif in_event:
            quiet_run = 0

    return events


def _waveform_profile_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0

    buckets = 12
    left_profile = _waveform_profile(left, buckets)
    right_profile = _waveform_profile(right, buckets)
    distance = sum(abs(a - b) for a, b in zip(left_profile, right_profile)) / buckets
    return max(0, 1 - distance)


def _waveform_profile(waveform: list[float], buckets: int) -> list[float]:
    bucket_size = max(1, len(waveform) // buckets)
    profile: list[float] = []
    for offset in range(0, len(waveform), bucket_size):
        chunk = waveform[offset : offset + bucket_size]
        profile.append(sum(chunk) / max(1, len(chunk)))
        if len(profile) == buckets:
            break

    while len(profile) < buckets:
        profile.append(0)

    return profile


def _ensure_analysis_duration_column(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(sound_analyses)").fetchall()
    }
    if "duration" not in columns:
        connection.execute(
            "ALTER TABLE sound_analyses ADD COLUMN duration REAL NOT NULL DEFAULT 0"
        )


def _ensure_saved_source_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(saved_sounds)").fetchall()
    }
    column_defaults = {
        "source_provider": "TEXT NOT NULL DEFAULT 'freesound'",
        "source_id": "TEXT NOT NULL DEFAULT ''",
        "source_url": "TEXT",
        "license_url": "TEXT",
        "creator_url": "TEXT",
        "attribution_text": "TEXT",
        "download_url": "TEXT",
        "download_allowed": "INTEGER NOT NULL DEFAULT 1",
        "download_count": "INTEGER",
    }
    for name, definition in column_defaults.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE saved_sounds ADD COLUMN {name} {definition}")

    connection.execute(
        """
        UPDATE saved_sounds
        SET
            source_provider = COALESCE(NULLIF(source_provider, ''), 'freesound'),
            source_id = COALESCE(NULLIF(source_id, ''), CAST(freesound_id AS TEXT)),
            source_url = COALESCE(source_url, url),
            download_url = COALESCE(download_url, preview_url)
        """
    )


def _ensure_saved_metadata_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(saved_sounds)").fetchall()
    }
    column_defaults = {
        "note": "TEXT NOT NULL DEFAULT ''",
        "fit_rating": "INTEGER",
        "folder": "TEXT NOT NULL DEFAULT ''",
        "labels": "TEXT NOT NULL DEFAULT '[]'",
        "download_filename": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in column_defaults.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE saved_sounds ADD COLUMN {name} {definition}")


def _ensure_saved_folder_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL DEFAULT 'local',
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _ensure_freesound_oauth_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS freesound_oauth_tokens (
            workspace_id TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at INTEGER NOT NULL DEFAULT 0,
            username TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _sync_existing_saved_folders(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT DISTINCT workspace_id, folder
        FROM saved_sounds
        WHERE folder IS NOT NULL AND TRIM(folder) <> ''
            AND workspace_id IS NOT NULL
        ORDER BY LOWER(folder)
        """
    ).fetchall()
    for row in rows:
        _ensure_folder_named(connection, row[1], row[0])


def _ensure_folder_named(
    connection: sqlite3.Connection,
    name: str,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> None:
    workspace_id = _normalize_workspace_id(workspace_id)
    folder_name = _normalize_folder_name(name)
    if not folder_name:
        return
    existing = connection.execute(
        "SELECT id FROM saved_folders WHERE workspace_id = ? AND name = ?",
        (workspace_id, folder_name),
    ).fetchone()
    if existing:
        return
    sort_order = connection.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM saved_folders WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO saved_folders (workspace_id, name, sort_order) VALUES (?, ?, ?)",
        (workspace_id, folder_name, sort_order),
    )


def _folder_row_by_id(
    connection: sqlite3.Connection,
    folder_id: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> sqlite3.Row | None:
    workspace_id = _normalize_workspace_id(workspace_id)
    return connection.execute(
        """
        SELECT
            saved_folders.*,
            (
                SELECT COUNT(*)
                FROM saved_sounds
                WHERE saved_sounds.workspace_id = saved_folders.workspace_id
                    AND saved_sounds.folder = saved_folders.name
            ) AS sound_count
        FROM saved_folders
        WHERE id = ? AND workspace_id = ?
        """,
        (folder_id, workspace_id),
    ).fetchone()


def _folder_row_by_name(
    connection: sqlite3.Connection,
    name: str,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> sqlite3.Row | None:
    workspace_id = _normalize_workspace_id(workspace_id)
    return connection.execute(
        """
        SELECT
            saved_folders.*,
            (
                SELECT COUNT(*)
                FROM saved_sounds
                WHERE saved_sounds.workspace_id = saved_folders.workspace_id
                    AND saved_sounds.folder = saved_folders.name
            ) AS sound_count
        FROM saved_folders
        WHERE workspace_id = ? AND name = ?
        """,
        (workspace_id, name),
    ).fetchone()


def _normalize_folder_name(name: str) -> str:
    normalized = " ".join(str(name or "").split()).strip()
    if normalized == "미분류":
        return ""
    return normalized[:80]


def _ensure_workspace_columns(connection: sqlite3.Connection) -> None:
    table_defaults = {
        "saved_sounds": "TEXT NOT NULL DEFAULT 'local'",
        "saved_folders": "TEXT NOT NULL DEFAULT 'local'",
        "sound_feedback": "TEXT NOT NULL DEFAULT 'local'",
    }
    for table, definition in table_defaults.items():
        columns = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if "workspace_id" not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN workspace_id {definition}")
        connection.execute(
            f"""
            UPDATE {table}
            SET workspace_id = ?
            WHERE workspace_id IS NULL OR TRIM(workspace_id) = ''
            """,
            (DEFAULT_WORKSPACE_ID,),
        )


def _rebuild_saved_sounds_if_needed(connection: sqlite3.Connection) -> None:
    create_sql = _table_create_sql(connection, "saved_sounds")
    if "freesound_id INTEGER NOT NULL UNIQUE" not in create_sql:
        return

    connection.execute("DROP INDEX IF EXISTS saved_sounds_source_identity")
    connection.execute("ALTER TABLE saved_sounds RENAME TO saved_sounds_legacy")
    connection.execute(
        """
        CREATE TABLE saved_sounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL DEFAULT 'local',
            freesound_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            license TEXT NOT NULL DEFAULT '',
            duration REAL NOT NULL DEFAULT 0,
            tags TEXT NOT NULL DEFAULT '[]',
            preview_url TEXT,
            url TEXT,
            description TEXT,
            score INTEGER NOT NULL DEFAULT 0,
            source_provider TEXT NOT NULL DEFAULT 'freesound',
            source_id TEXT NOT NULL DEFAULT '',
            source_url TEXT,
            license_url TEXT,
            creator_url TEXT,
            attribution_text TEXT,
            download_url TEXT,
            download_allowed INTEGER NOT NULL DEFAULT 1,
            download_count INTEGER,
            note TEXT NOT NULL DEFAULT '',
            fit_rating INTEGER,
            folder TEXT NOT NULL DEFAULT '',
            labels TEXT NOT NULL DEFAULT '[]',
            download_filename TEXT NOT NULL DEFAULT '',
            saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO saved_sounds (
            id, workspace_id, freesound_id, name, username, license, duration, tags,
            preview_url, url, description, score, source_provider, source_id,
            source_url, license_url, creator_url, attribution_text, download_url,
            download_allowed, download_count, note, fit_rating, folder, labels,
            download_filename, saved_at
        )
        SELECT
            id, COALESCE(NULLIF(workspace_id, ''), 'local'), freesound_id, name, username,
            license, duration, tags, preview_url, url, description, score,
            source_provider, source_id, source_url, license_url, creator_url,
            attribution_text, download_url, download_allowed, download_count, note, fit_rating,
            folder, labels, download_filename, saved_at
        FROM saved_sounds_legacy
        """
    )
    connection.execute("DROP TABLE saved_sounds_legacy")


def _rebuild_saved_folders_if_needed(connection: sqlite3.Connection) -> None:
    create_sql = _table_create_sql(connection, "saved_folders")
    if "name TEXT NOT NULL UNIQUE" not in create_sql:
        return

    connection.execute("ALTER TABLE saved_folders RENAME TO saved_folders_legacy")
    connection.execute(
        """
        CREATE TABLE saved_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL DEFAULT 'local',
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO saved_folders (id, workspace_id, name, sort_order, created_at)
        SELECT id, COALESCE(NULLIF(workspace_id, ''), 'local'), name, sort_order, created_at
        FROM saved_folders_legacy
        """
    )
    connection.execute("DROP TABLE saved_folders_legacy")


def _ensure_workspace_indexes(connection: sqlite3.Connection) -> None:
    connection.execute("DROP INDEX IF EXISTS saved_sounds_source_identity")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS saved_sounds_workspace_source_identity
        ON saved_sounds(workspace_id, source_provider, source_id)
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS saved_folders_workspace_name
        ON saved_folders(workspace_id, name)
        """
    )


def _table_create_sql(connection: sqlite3.Connection, table_name: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row[0] if row and row[0] else ""


def _normalize_workspace_id(workspace_id: str) -> str:
    normalized = str(workspace_id or "").strip()
    if not normalized:
        return DEFAULT_WORKSPACE_ID
    normalized = "".join(
        character for character in normalized if character.isalnum() or character in "._-"
    )
    return normalized[:80] or DEFAULT_WORKSPACE_ID


def _ensure_feedback_source_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(sound_feedback)").fetchall()
    }
    if "source_provider" not in columns:
        connection.execute(
            "ALTER TABLE sound_feedback ADD COLUMN source_provider TEXT NOT NULL DEFAULT 'freesound'"
        )
    if "source_id" not in columns:
        connection.execute(
            "ALTER TABLE sound_feedback ADD COLUMN source_id TEXT NOT NULL DEFAULT ''"
        )
    connection.execute(
        """
        UPDATE sound_feedback
        SET
            source_provider = COALESCE(NULLIF(source_provider, ''), 'freesound'),
            source_id = COALESCE(NULLIF(source_id, ''), CAST(freesound_id AS TEXT))
        """
    )


def _clean_labels(labels: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for label in labels:
        normalized = label.strip()
        if not normalized or normalized.lower() in seen:
            continue
        cleaned.append(normalized[:40])
        seen.add(normalized.lower())
        if len(cleaned) == 20:
            break
    return cleaned


def _model_fields_set(model: SavedSoundUpdate) -> set[str]:
    fields = getattr(model, "model_fields_set", None)
    if fields is not None:
        return set(fields)
    return set(getattr(model, "__fields_set__", set()))
