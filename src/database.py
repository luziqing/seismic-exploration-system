"""
SQLite database module: stores pick points and SAM segmentation results

Tables:
  - sgy_files    : uploaded SGY file records
  - slices       : generated slice image records
  - pick_sessions: pick sessions (linked to a slice)
  - points       : picked points (include/exclude)
  - sam_results  : SAM inference results (mask path, score)
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "db" / "seismic.db"


def get_conn() -> sqlite3.Connection:
    """Get a database connection (WAL mode + foreign keys enabled)"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sgy_files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT    NOT NULL,
            path        TEXT    NOT NULL,
            il_min      INTEGER DEFAULT 0,
            il_max      INTEGER DEFAULT 0,
            xl_min      INTEGER DEFAULT 0,
            xl_max      INTEGER DEFAULT 0,
            n_inlines   INTEGER DEFAULT 0,
            n_crosslines INTEGER DEFAULT 0,
            n_samples   INTEGER DEFAULT 0,
            dt_us       INTEGER DEFAULT 0,
            created_at  REAL    DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS slices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sgy_id      INTEGER REFERENCES sgy_files(id),
            category    TEXT    NOT NULL,   -- 'inline' / 'crossline' / 'timeslice'
            index_value INTEGER NOT NULL,   -- IL/XL number or time value
            path        TEXT    NOT NULL,   -- image file path
            created_at  REAL    DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS pick_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slice_id    INTEGER,  -- nullable: direct Zarr rendering needs no slices row
            name        TEXT    DEFAULT '',
            created_at  REAL    DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS points (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER REFERENCES pick_sessions(id),
            il          REAL    NOT NULL,
            xl          REAL    NOT NULL,
            depth       REAL    NOT NULL,
            px_x        REAL    DEFAULT 0,
            px_y        REAL    DEFAULT 0,
            label       INTEGER NOT NULL DEFAULT 0,  -- 1=include, 0=exclude
            created_at  REAL    DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS sam_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER REFERENCES pick_sessions(id),
            mask_path   TEXT    DEFAULT '',
            score       REAL    DEFAULT 0,
            mask_shape  TEXT    DEFAULT '',  -- JSON [h, w]
            created_at  REAL    DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS sam_validation_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER REFERENCES pick_sessions(id),
            sam_result_id INTEGER REFERENCES sam_results(id),
            prediction_threshold   REAL DEFAULT 0.5,
            ground_truth_threshold REAL DEFAULT 0.5,
            prediction_shape TEXT DEFAULT '',  -- JSON [h, w]
            ground_truth_shape TEXT DEFAULT '',  -- JSON [h, w]
            tp          INTEGER DEFAULT 0,
            fp          INTEGER DEFAULT 0,
            tn          INTEGER DEFAULT 0,
            fn          INTEGER DEFAULT 0,
            iou         REAL DEFAULT 0,
            dice        REAL DEFAULT 0,
            precision   REAL DEFAULT 0,
            recall      REAL DEFAULT 0,
            specificity REAL DEFAULT 0,
            accuracy    REAL DEFAULT 0,
            passed      INTEGER DEFAULT 0,
            acceptance_json TEXT DEFAULT '',
            checks_json TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '',
            created_at  REAL    DEFAULT (strftime('%s','now'))
        );

        -- QC-driven refine loop (spec qc-refine-loop, Requirement 4)
        CREATE TABLE IF NOT EXISTS refine_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            volume       TEXT, direction TEXT, slice_index INTEGER, mode TEXT, target_type TEXT,
            grid_shape   TEXT,             -- JSON [rows, cols]
            best_round   INTEGER, stop_reason TEXT, stop_message TEXT,
            constants    TEXT,             -- JSON
            created_at   REAL DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS refine_rounds (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id       INTEGER REFERENCES refine_runs(id),
            round        INTEGER,
            prompts      TEXT,             -- JSON
            metrics      TEXT,             -- JSON
            score        REAL, delta REAL,
            correction   TEXT,             -- JSON or NULL
            truth_reference TEXT,          -- JSON or NULL (reporting only)
            mask_rle     TEXT              -- JSON run-length encoding of the native-grid mask
        );
    """)
    # ── Migration: drop the FK constraint on pick_sessions.slice_id (old tables have REFERENCES slices(id))
    try:
        cols = conn.execute("PRAGMA table_info(pick_sessions)").fetchall()
        if cols:
            # check whether the sql still contains the old FK constraint
            tbl = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='pick_sessions'"
            ).fetchone()
            if tbl and "REFERENCES slices(id)" in (tbl["sql"] or ""):
                conn.executescript("""
                    CREATE TABLE pick_sessions_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        slice_id INTEGER,
                        name TEXT DEFAULT '',
                        created_at REAL DEFAULT (strftime('%s','now'))
                    );
                    INSERT INTO pick_sessions_new SELECT * FROM pick_sessions;
                    DROP TABLE pick_sessions;
                    ALTER TABLE pick_sessions_new RENAME TO pick_sessions;
                """)
    except Exception:
        pass
    conn.commit()
    conn.close()


# ── SGY files ─────────────────────────────────────────────────

def insert_sgy(filename: str, path: str, info: dict) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO sgy_files (filename, path, il_min, il_max, xl_min, xl_max,
           n_inlines, n_crosslines, n_samples, dt_us)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (filename, path, info.get("il_min", 0), info.get("il_max", 0),
         info.get("xl_min", 0), info.get("xl_max", 0),
         info.get("n_inlines", 0), info.get("n_crosslines", 0),
         info.get("n_samples", 0), info.get("dt_us", 0))
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_latest_sgy() -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM sgy_files ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Slices ────────────────────────────────────────────────────

def insert_slice(sgy_id: int, category: str, index_value: int, path: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO slices (sgy_id, category, index_value, path) VALUES (?, ?, ?, ?)",
        (sgy_id, category, index_value, path)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_slices_by_category(category: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM slices WHERE category = ? ORDER BY index_value",
        (category,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Pick sessions ─────────────────────────────────────────────

def create_session(slice_id: int, name: str = "") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO pick_sessions (slice_id, name) VALUES (?, ?)",
        (slice_id, name)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_or_create_session(slice_id: int) -> int:
    """Get the latest session for a slice, creating one if none exists"""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM pick_sessions WHERE slice_id = ? ORDER BY created_at DESC LIMIT 1",
        (slice_id,)
    ).fetchone()
    if row:
        session_id = row["id"]
        conn.close()
        return session_id
    conn.close()
    return create_session(slice_id)


# ── Points ────────────────────────────────────────────────────

def insert_point(session_id: int, il: float, xl: float, depth: float,
                 px_x: float = 0, px_y: float = 0, label: int = 1) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO points (session_id, il, xl, depth, px_x, px_y, label)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, il, xl, depth, px_x, px_y, label)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def insert_points_batch(session_id: int, points: list[dict]) -> int:
    """Insert points in bulk; return the number inserted"""
    conn = get_conn()
    cur = conn.executemany(
        """INSERT INTO points (session_id, il, xl, depth, px_x, px_y, label)
           VALUES (:session_id, :il, :xl, :depth, :px_x, :px_y, :label)""",
        [{**p, "session_id": session_id} for p in points]
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def get_points_by_session(session_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM points WHERE session_id = ? ORDER BY id",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_last_point(session_id: int) -> bool:
    """Delete the last point in a session"""
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM points WHERE id = (SELECT MAX(id) FROM points WHERE session_id = ?)",
        (session_id,)
    )
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def clear_points(session_id: int):
    """Delete all points in a session"""
    conn = get_conn()
    conn.execute("DELETE FROM points WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


# ── SAM results ───────────────────────────────────────────────

def insert_sam_result(session_id: int, mask_path: str, score: float,
                      mask_shape: tuple) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO sam_results (session_id, mask_path, score, mask_shape)
           VALUES (?, ?, ?, ?)""",
        (session_id, mask_path, score, json.dumps(list(mask_shape)))
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_latest_sam_result(session_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM sam_results WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_validation_run(session_id: int, summary: dict,
                          sam_result_id: Optional[int] = None,
                          metadata: Optional[dict] = None) -> int:
    confusion = summary.get("confusion", {})
    metrics = summary.get("metrics", {})
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO sam_validation_runs (
           session_id, sam_result_id,
           prediction_threshold, ground_truth_threshold,
           prediction_shape, ground_truth_shape,
           tp, fp, tn, fn,
           iou, dice, precision, recall, specificity, accuracy,
           passed, acceptance_json, checks_json, metadata_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            sam_result_id,
            summary.get("prediction_threshold", 0.5),
            summary.get("ground_truth_threshold", 0.5),
            json.dumps(summary.get("prediction_shape", [])),
            json.dumps(summary.get("ground_truth_shape", [])),
            confusion.get("tp", 0),
            confusion.get("fp", 0),
            confusion.get("tn", 0),
            confusion.get("fn", 0),
            metrics.get("iou", 0.0),
            metrics.get("dice", 0.0),
            metrics.get("precision", 0.0),
            metrics.get("recall", 0.0),
            metrics.get("specificity", 0.0),
            metrics.get("accuracy", 0.0),
            1 if summary.get("passed", False) else 0,
            json.dumps(summary.get("acceptance", {})),
            json.dumps(summary.get("checks", {})),
            json.dumps(metadata or {}),
        )
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def _decode_validation_run(row: sqlite3.Row) -> dict:
    data = dict(row)
    tp = data["tp"]
    fp = data["fp"]
    tn = data["tn"]
    fn = data["fn"]
    return {
        "id": data["id"],
        "session_id": data["session_id"],
        "sam_result_id": data["sam_result_id"],
        "prediction_threshold": data["prediction_threshold"],
        "ground_truth_threshold": data["ground_truth_threshold"],
        "prediction_shape": json.loads(data["prediction_shape"] or "[]"),
        "ground_truth_shape": json.loads(data["ground_truth_shape"] or "[]"),
        "confusion": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "total": tp + fp + tn + fn,
            "predicted_positive": tp + fp,
            "ground_truth_positive": tp + fn,
        },
        "metrics": {
            "iou": data["iou"],
            "dice": data["dice"],
            "precision": data["precision"],
            "recall": data["recall"],
            "specificity": data["specificity"],
            "accuracy": data["accuracy"],
        },
        "passed": bool(data["passed"]),
        "acceptance": json.loads(data["acceptance_json"] or "{}"),
        "checks": json.loads(data["checks_json"] or "{}"),
        "metadata": json.loads(data["metadata_json"] or "{}"),
        "created_at": data["created_at"],
    }


def get_latest_validation_run(session_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM sam_validation_runs WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,)
    ).fetchone()
    conn.close()
    return _decode_validation_run(row) if row else None


def list_validation_runs(session_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM sam_validation_runs WHERE session_id = ? ORDER BY id DESC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [_decode_validation_run(row) for row in rows]


# ── Refine loop runs (spec qc-refine-loop, Requirement 4) ─────────────────────

def mask_to_rle(mask) -> list[int]:
    """Row-major run lengths, starting with a run of zeros (possibly empty)."""
    import numpy as np
    flat = np.asarray(mask, dtype=bool).ravel()
    if flat.size == 0:
        return []
    change = np.flatnonzero(np.diff(flat.astype(np.int8))) + 1
    bounds = np.concatenate([[0], change, [flat.size]])
    runs = np.diff(bounds).tolist()
    return ([0] + runs) if flat[0] else runs


def rle_to_mask(runs: list[int], shape):
    import numpy as np
    flat = np.zeros(int(np.prod(shape)), dtype=bool)
    pos, val = 0, False
    for n in runs:
        if val:
            flat[pos:pos + n] = True
        pos += n
        val = not val
    if pos != flat.size:
        raise ValueError(f"RLE covers {pos} pixels, expected {flat.size}")
    return flat.reshape(shape)


def insert_refine_run(volume: str, direction: str, slice_index: int, mode: str, target_type: str,
                      grid_shape, result: dict) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO refine_runs (volume, direction, slice_index, mode, target_type, grid_shape,
                                    best_round, stop_reason, stop_message, constants)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (volume, direction, slice_index, mode, target_type, json.dumps(list(grid_shape)),
         result["best_round"], result["stop_reason"], result["stop_message"], json.dumps(result["constants"])))
    run_id = cur.lastrowid
    for r in result["rounds"]:
        conn.execute(
            """INSERT INTO refine_rounds (run_id, round, prompts, metrics, score, delta, correction,
                                          truth_reference, mask_rle) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, r["round"], json.dumps(r["prompts"]), json.dumps(r["metrics"]), r["score"], r["delta"],
             json.dumps(r["correction"]) if r["correction"] is not None else None,
             json.dumps(r.get("truth_reference")) if r.get("truth_reference") is not None else None,
             json.dumps(mask_to_rle(r["mask"]))))
    conn.commit()
    conn.close()
    return run_id


def get_refine_run(run_id: int) -> Optional[dict]:
    """The stored run with its rounds; masks decoded back to bool arrays."""
    conn = get_conn()
    run = conn.execute("SELECT * FROM refine_runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        conn.close()
        return None
    rows = conn.execute("SELECT * FROM refine_rounds WHERE run_id = ? ORDER BY round", (run_id,)).fetchall()
    conn.close()
    shape = tuple(json.loads(run["grid_shape"]))
    rounds = [{
        "round": r["round"], "prompts": json.loads(r["prompts"]), "metrics": json.loads(r["metrics"]),
        "score": r["score"], "delta": r["delta"],
        "correction": json.loads(r["correction"]) if r["correction"] else None,
        "truth_reference": json.loads(r["truth_reference"]) if r["truth_reference"] else None,
        "mask": rle_to_mask(json.loads(r["mask_rle"]), shape),
    } for r in rows]
    return {"run_id": run["id"], "volume": run["volume"], "direction": run["direction"],
            "index": run["slice_index"], "mode": run["mode"], "target_type": run["target_type"],
            "grid_shape": list(shape), "best_round": run["best_round"], "stop_reason": run["stop_reason"],
            "stop_message": run["stop_message"], "constants": json.loads(run["constants"]), "rounds": rounds}