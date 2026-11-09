"""
SQLite 数据库模块 — 存储拾取点和 SAM 分割结果

表结构:
  - sgy_files    : 上传的 SGY 文件记录
  - slices       : 生成的切片图片记录
  - pick_sessions: 拾取会话 (关联到某张切片)
  - points       : 拾取的点位 (include/exclude)
  - sam_results  : SAM 推理结果 (mask 路径, score)
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "db" / "seismic.db"


def get_conn() -> sqlite3.Connection:
    """获取数据库连接 (启用 WAL 模式 + 外键)"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化所有表"""
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
            index_value INTEGER NOT NULL,   -- IL/XL 号或时间值
            path        TEXT    NOT NULL,   -- 图片文件路径
            created_at  REAL    DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS pick_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            slice_id    INTEGER,  -- nullable: Zarr直接渲染模式下无需关联slices表
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
    """)
    # ── 迁移: 移除 pick_sessions.slice_id 的 FK 约束 (旧表有 REFERENCES slices(id))
    try:
        cols = conn.execute("PRAGMA table_info(pick_sessions)").fetchall()
        if cols:
            # 检查 sql 是否包含旧的 FK 约束
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


# ── SGY 文件操作 ──────────────────────────────────────────────

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


# ── 切片操作 ──────────────────────────────────────────────────

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


# ── 拾取会话 ──────────────────────────────────────────────────

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
    """获取某切片的最新会话, 没有则创建"""
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


# ── 点位操作 ──────────────────────────────────────────────────

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
    """批量插入点位, 返回插入数量"""
    conn = get_conn()
    conn.executemany(
        """INSERT INTO points (session_id, il, xl, depth, px_x, px_y, label)
           VALUES (:session_id, :il, :xl, :depth, :px_x, :px_y, :label)""",
        [{**p, "session_id": session_id} for p in points]
    )
    count = conn.execute(
        "SELECT changes()").fetchone()[0]
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
    """删除会话中最后一个点"""
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
    """清空会话中的所有点"""
    conn = get_conn()
    conn.execute("DELETE FROM points WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


# ── SAM 结果 ──────────────────────────────────────────────────

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
