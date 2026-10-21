"""SQLite access: connection, safe migrations, settings and CRUD helpers.

All SQL uses parameter placeholders (?) - user input is never formatted into SQL.
"""
from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import config
from .validators import (ValidationError, check_exam_date, check_float, check_int,
                         check_not_future, check_status, clean_name)

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- connection
def get_connection(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the database (default: data/study_planner.db) and make sure it is migrated."""
    path = Path(path) if path else config.DB_PATH
    if not path.exists():
        if path == config.DB_PATH and config.ORIGINAL_DB_PATH.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(config.ORIGINAL_DB_PATH, path)   # first run: restore from supplied copy
        else:
            raise FileNotFoundError(f"Database not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn, path)
    return conn


@contextmanager
def connect(path: Path | str | None = None):
    conn = get_connection(path)
    try:
        yield conn
    finally:
        conn.close()


# --------------------------------------------------------------------------- migrations
def _columns(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}  # table is a fixed literal


def migrate(conn: sqlite3.Connection, path: Path | None = None) -> None:
    """Upgrade an older database in place. Existing rows are never deleted or rewritten.

    v0 -> v1 adds: subjects.daily_minutes, study_sessions.planned_minutes,
    study_plan.rescheduled, quiz_questions.needs_review, tables `settings` and
    `quiz_answers`, and a unique index on study_plan(plan_date, topic_id).
    A timestamped backup copy is made first (file databases only).
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        _ensure_default_settings(conn)
        return
    if path is not None and Path(path).exists():
        config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copyfile(path, config.BACKUP_DIR / f"study_planner_pre_v{SCHEMA_VERSION}_{stamp}.db")
    conn.commit()
    conn.execute("BEGIN")
    try:
        if "daily_minutes" not in _columns(conn, "subjects"):
            conn.execute("ALTER TABLE subjects ADD COLUMN daily_minutes INTEGER NOT NULL DEFAULT 120")
        if "planned_minutes" not in _columns(conn, "study_sessions"):
            conn.execute("ALTER TABLE study_sessions ADD COLUMN planned_minutes INTEGER")
        if "rescheduled" not in _columns(conn, "study_plan"):
            conn.execute("ALTER TABLE study_plan ADD COLUMN rescheduled INTEGER NOT NULL DEFAULT 0")
        if "needs_review" not in _columns(conn, "quiz_questions"):
            conn.execute("ALTER TABLE quiz_questions ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0")
        conn.execute("""CREATE TABLE IF NOT EXISTS settings (
                            key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS quiz_answers (
                            answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            quiz_id INTEGER NOT NULL REFERENCES quiz_results(quiz_id) ON DELETE CASCADE,
                            question_id INTEGER NOT NULL REFERENCES quiz_questions(question_id) ON DELETE CASCADE,
                            chosen_option TEXT CHECK(chosen_option IN ('A','B','C','D')),
                            is_correct INTEGER NOT NULL CHECK(is_correct IN (0,1)))""")
        # Only create the unique index when the existing data allows it (it does for the supplied DB).
        dupes = conn.execute("""SELECT COUNT(*) FROM (SELECT 1 FROM study_plan
                                GROUP BY plan_date, topic_id HAVING COUNT(*) > 1)""").fetchone()[0]
        if dupes == 0:
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_plan_date_topic
                            ON study_plan(plan_date, topic_id)""")
        # Flag (never delete) questions whose exact text is reused under several topics.
        conn.execute("""UPDATE quiz_questions SET needs_review = 1 WHERE question_text IN
                        (SELECT question_text FROM quiz_questions
                         GROUP BY question_text HAVING COUNT(DISTINCT topic_id) > 1)""")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_quiz_results_topic ON quiz_results(topic_id, quiz_date)")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        _ensure_default_settings(conn, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _ensure_default_settings(conn, commit: bool = True) -> None:
    for k, v in config.DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    if commit:
        conn.commit()


# --------------------------------------------------------------------------- settings
def get_setting(conn, key: str, cast=int):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    raw = row[0] if row else config.DEFAULT_SETTINGS[key]
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return cast(config.DEFAULT_SETTINGS[key])


def set_setting(conn, key: str, value) -> None:
    if key not in config.DEFAULT_SETTINGS:
        raise ValidationError(f"Unknown setting: {key}")
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
    conn.commit()


def save_settings(conn, daily_limit: int, weak_threshold: int, recent_quizzes: int, break_minutes: int) -> None:
    daily_limit = check_int(daily_limit, "Daily study limit (minutes)", 15, 960)
    weak_threshold = check_int(weak_threshold, "Weak-topic threshold (%)", 1, 99)
    recent_quizzes = check_int(recent_quizzes, "Recent quizzes to average", 1, 10)
    break_minutes = check_int(break_minutes, "Break length (minutes)", 0, 30)
    set_setting(conn, "daily_limit_minutes", daily_limit)
    set_setting(conn, "weak_threshold_pct", weak_threshold)
    set_setting(conn, "weak_recent_quizzes", recent_quizzes)
    set_setting(conn, "break_minutes", break_minutes)


# --------------------------------------------------------------------------- subjects
def subjects_df(conn) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM subjects ORDER BY exam_date IS NULL, exam_date, subject_name", conn)


def add_subject(conn, name, exam_date, priority, daily_minutes, today: date | None = None) -> int:
    name = clean_name(name, "Subject name")
    exam = check_exam_date(exam_date, today) if exam_date else None
    priority = check_int(priority, "Priority", 1, 5)
    daily_minutes = check_int(daily_minutes, "Daily study time (minutes)", 15, 720)
    try:
        cur = conn.execute("INSERT INTO subjects(subject_name, exam_date, priority, daily_minutes) VALUES (?,?,?,?)",
                           (name, exam, priority, daily_minutes))
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValidationError(f"A subject named '{name}' already exists.")
    return cur.lastrowid


def update_subject(conn, subject_id, name, exam_date, priority, daily_minutes, today: date | None = None) -> None:
    name = clean_name(name, "Subject name")
    old = conn.execute("SELECT exam_date FROM subjects WHERE subject_id = ?", (subject_id,)).fetchone()
    if old is None:
        raise ValidationError("That subject no longer exists.")
    exam = check_exam_date(exam_date, today, allow_unchanged=old["exam_date"]) if exam_date else None
    priority = check_int(priority, "Priority", 1, 5)
    daily_minutes = check_int(daily_minutes, "Daily study time (minutes)", 15, 720)
    try:
        conn.execute("UPDATE subjects SET subject_name=?, exam_date=?, priority=?, daily_minutes=? WHERE subject_id=?",
                     (name, exam, priority, daily_minutes, subject_id))
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValidationError(f"A subject named '{name}' already exists.")


# --------------------------------------------------------------------------- topics
def topics_df(conn, subject_id: int | None = None) -> pd.DataFrame:
    sql = """SELECT t.topic_id, t.subject_id, s.subject_name, t.topic_name, t.difficulty,
                    t.estimated_hours, t.status, t.last_studied_date
             FROM topics t JOIN subjects s ON s.subject_id = t.subject_id"""
    params: tuple = ()
    if subject_id is not None:
        sql += " WHERE t.subject_id = ?"
        params = (subject_id,)
    return pd.read_sql_query(sql + " ORDER BY s.subject_name, t.topic_id", conn, params=params)


def add_topic(conn, subject_id, name, difficulty, estimated_hours, status="pending", last_studied=None,
              today: date | None = None) -> int:
    name = clean_name(name, "Topic name")
    difficulty = check_int(difficulty, "Difficulty", 1, 5)
    hours = check_float(estimated_hours, "Estimated hours", 0.25, 40)
    status = check_status(status)
    last = check_not_future(last_studied, "Last studied date", today) if last_studied else None
    try:
        cur = conn.execute("""INSERT INTO topics(subject_id, topic_name, difficulty, estimated_hours, status, last_studied_date)
                              VALUES (?,?,?,?,?,?)""", (subject_id, name, difficulty, hours, status, last))
        conn.commit()
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            raise ValidationError(f"This subject already has a topic named '{name}'.")
        raise ValidationError("Could not save the topic - check the selected subject.")
    return cur.lastrowid


def update_topic(conn, topic_id, name, difficulty, estimated_hours, status, last_studied=None,
                 today: date | None = None) -> None:
    name = clean_name(name, "Topic name")
    difficulty = check_int(difficulty, "Difficulty", 1, 5)
    hours = check_float(estimated_hours, "Estimated hours", 0.25, 40)
    status = check_status(status)
    last = check_not_future(last_studied, "Last studied date", today) if last_studied else None
    try:
        conn.execute("""UPDATE topics SET topic_name=?, difficulty=?, estimated_hours=?, status=?, last_studied_date=?
                        WHERE topic_id=?""", (name, difficulty, hours, status, last, topic_id))
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValidationError(f"This subject already has a topic named '{name}'.")


# --------------------------------------------------------------------------- revisions & sessions
def add_revision(conn, topic_id, revised_date, confidence, notes="") -> int:
    when = check_not_future(revised_date, "Revision date")
    confidence = check_int(confidence, "Confidence", 1, 5)
    cur = conn.execute("INSERT INTO revision_history(topic_id, revised_date, confidence, notes) VALUES (?,?,?,?)",
                       (topic_id, when, confidence, (notes or "").strip()[:500]))
    conn.commit()
    return cur.lastrowid


def add_session(conn, topic_id, study_date, planned_minutes, actual_minutes, completed, notes="",
                plan_id: int | None = None, mark_studied: bool = True) -> int:
    when = check_not_future(study_date, "Study date")
    planned = check_int(planned_minutes, "Planned minutes", 1, 720)
    actual = check_int(actual_minutes, "Actual minutes", 1, 720)
    cur = conn.execute("""INSERT INTO study_sessions(topic_id, study_date, duration_minutes, completed, notes, planned_minutes)
                          VALUES (?,?,?,?,?,?)""",
                       (topic_id, when, actual, 1 if completed else 0, (notes or "").strip()[:500], planned))
    if mark_studied:
        conn.execute("""UPDATE topics SET last_studied_date = ?,
                        status = CASE WHEN status = 'pending' THEN 'in_progress' ELSE status END
                        WHERE topic_id = ? AND (last_studied_date IS NULL OR last_studied_date < ?)""",
                     (when, topic_id, when))
        conn.execute("""UPDATE topics SET status = CASE WHEN status = 'pending' THEN 'in_progress' ELSE status END
                        WHERE topic_id = ?""", (topic_id,))
    if plan_id is not None and completed:
        conn.execute("UPDATE study_plan SET status = 'completed' WHERE plan_id = ?", (plan_id,))
    conn.commit()
    return cur.lastrowid


def sessions_df(conn) -> pd.DataFrame:
    return pd.read_sql_query("""SELECT ss.session_id, ss.study_date, s.subject_name, t.topic_name,
                                       ss.planned_minutes, ss.duration_minutes AS actual_minutes,
                                       ss.completed, ss.notes
                                FROM study_sessions ss JOIN topics t ON t.topic_id = ss.topic_id
                                JOIN subjects s ON s.subject_id = t.subject_id
                                ORDER BY ss.study_date DESC, ss.session_id DESC""", conn)


def plan_df(conn, only_status: str | None = None) -> pd.DataFrame:
    sql = """SELECT p.plan_id, p.plan_date, s.subject_name, t.topic_name, p.topic_id, p.planned_minutes,
                    p.reason, p.status, p.rescheduled
             FROM study_plan p JOIN topics t ON t.topic_id = p.topic_id
             JOIN subjects s ON s.subject_id = t.subject_id"""
    params: tuple = ()
    if only_status:
        sql += " WHERE p.status = ?"
        params = (only_status,)
    return pd.read_sql_query(sql + " ORDER BY p.plan_date, p.plan_id", conn, params=params)


def set_plan_status(conn, plan_id: int, status: str) -> None:
    if status not in ("planned", "completed", "missed"):
        raise ValidationError("Invalid plan status.")
    conn.execute("UPDATE study_plan SET status = ? WHERE plan_id = ?", (status, plan_id))
    conn.commit()
