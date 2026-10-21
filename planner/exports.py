"""CSV export helpers."""
from __future__ import annotations

import pandas as pd

from . import analytics, db, quiz


def _safe_cell(v):
    """Neutralise spreadsheet formula injection (cells starting with = + - @)."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    safe = df.copy()
    for col in safe.columns:
        if safe[col].dtype == object or str(safe[col].dtype).startswith("str"):
            safe[col] = safe[col].map(_safe_cell)
    return safe.to_csv(index=False).encode("utf-8-sig")   # BOM so Excel shows UTF-8 correctly


def progress_export(conn) -> pd.DataFrame:
    return db.topics_df(conn).rename(columns={"estimated_hours": "estimated_hours"})


def exports(conn) -> dict[str, pd.DataFrame]:
    return {"progress": progress_export(conn), "subject_summary": analytics.subject_progress_df(conn),
            "quiz_results": quiz.quiz_results_df(conn), "study_plan": db.plan_df(conn),
            "study_sessions": db.sessions_df(conn)}
