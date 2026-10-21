"""Dashboard numbers and chart data (plain DataFrames - charts are drawn in the views)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def subject_progress_df(conn) -> pd.DataFrame:
    """Per subject: topic counts and completion % (by topic count and by estimated hours)."""
    df = pd.read_sql_query("""
        SELECT s.subject_id, s.subject_name, s.exam_date,
               COUNT(t.topic_id) AS total_topics,
               COALESCE(SUM(t.status = 'completed'), 0) AS completed_topics,
               COALESCE(SUM(t.status = 'in_progress'), 0) AS in_progress_topics,
               COALESCE(SUM(t.status = 'pending'), 0) AS pending_topics,
               COALESCE(SUM(t.estimated_hours), 0) AS total_hours,
               COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.estimated_hours ELSE 0 END), 0) AS completed_hours
        FROM subjects s LEFT JOIN topics t ON t.subject_id = s.subject_id
        GROUP BY s.subject_id ORDER BY s.subject_name""", conn)
    df["completion_pct"] = (100 * df["completed_topics"] / df["total_topics"].where(df["total_topics"] > 0)).fillna(0).round(1)
    return df


def study_minutes_by_day(conn, days: int = 14, today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    first = today - timedelta(days=days - 1)
    df = pd.read_sql_query("""SELECT study_date, SUM(duration_minutes) AS minutes,
                                     SUM(COALESCE(planned_minutes, 0)) AS planned_minutes
                              FROM study_sessions WHERE study_date >= ? AND study_date <= ?
                              GROUP BY study_date""", conn, params=(first.isoformat(), today.isoformat()))
    full = pd.DataFrame({"study_date": [(first + timedelta(days=i)).isoformat() for i in range(days)]})
    out = full.merge(df, on="study_date", how="left").fillna(0)
    out["minutes"] = out["minutes"].astype(int)
    out["planned_minutes"] = out["planned_minutes"].astype(int)
    return out


def total_study_hours(conn) -> float:
    m = conn.execute("SELECT COALESCE(SUM(duration_minutes), 0) FROM study_sessions").fetchone()[0]
    return round(m / 60.0, 1)


def average_quiz_pct(conn) -> float | None:
    r = conn.execute("SELECT AVG(100.0 * score / total_questions) FROM quiz_results").fetchone()[0]
    return None if r is None else round(r, 1)


def upcoming_exams_df(conn, today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    df = pd.read_sql_query("""SELECT subject_name, exam_date, priority FROM subjects
                              WHERE exam_date IS NOT NULL AND exam_date >= ? ORDER BY exam_date""",
                           conn, params=(today.isoformat(),))
    if not df.empty:
        df["days_left"] = [(date.fromisoformat(d) - today).days for d in df["exam_date"]]
    else:
        df["days_left"] = pd.Series(dtype=int)
    return df


def topic_status_counts(conn) -> dict:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM topics GROUP BY status").fetchall()
    c = {"completed": 0, "in_progress": 0, "pending": 0}
    c.update({r["status"]: r["n"] for r in rows})
    c["total"] = sum(c.values())
    return c
