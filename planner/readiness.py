"""Revision reminders and the exam-readiness ESTIMATE.

The readiness number is a rough, rule-based estimate from your own data. It is NOT a
prediction of your exam marks and NOT a guarantee.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .quiz import recent_average_pct

# Confidence rating (1-5) -> days until the topic should be revised again.
REVISION_INTERVAL_DAYS = {1: 1, 2: 3, 3: 7, 4: 14, 5: 21}
DEFAULT_CONFIDENCE = 3
WEIGHTS = {"completion": 0.5, "revision": 0.2, "quiz": 0.3}
DISCLAIMER = ("This is an estimate based only on the data you entered (syllabus completion, revision and quiz "
              "results). It is not a prediction of your marks and not a guarantee of exam success.")


def revision_reminders(conn, today: date | None = None) -> pd.DataFrame:
    """One row per studied topic: when it is next due for revision, based on last revision date + confidence."""
    today = today or date.today()
    rows = conn.execute("""
        SELECT t.topic_id, s.subject_name, t.topic_name, t.status, t.last_studied_date,
               (SELECT revised_date FROM revision_history r WHERE r.topic_id = t.topic_id
                ORDER BY revised_date DESC, revision_id DESC LIMIT 1) AS last_revised,
               (SELECT confidence FROM revision_history r WHERE r.topic_id = t.topic_id
                ORDER BY revised_date DESC, revision_id DESC LIMIT 1) AS confidence
        FROM topics t JOIN subjects s ON s.subject_id = t.subject_id
        WHERE t.status <> 'pending' OR t.last_studied_date IS NOT NULL
              OR EXISTS (SELECT 1 FROM revision_history r WHERE r.topic_id = t.topic_id)
        ORDER BY s.subject_name, t.topic_id""").fetchall()
    out = []
    for r in rows:
        conf = r["confidence"] or DEFAULT_CONFIDENCE
        interval = REVISION_INTERVAL_DAYS[conf]
        basis = r["last_revised"] or r["last_studied_date"]
        if basis is None:
            continue
        due = date.fromisoformat(basis) + timedelta(days=interval)
        overdue = (today - due).days
        status = "Overdue" if overdue > 0 else ("Due today" if overdue == 0 else "Upcoming")
        out.append({"topic_id": r["topic_id"], "subject_name": r["subject_name"], "topic_name": r["topic_name"],
                    "last_revised": r["last_revised"] or "never", "confidence": r["confidence"] or None,
                    "interval_days": interval, "due_date": due.isoformat(), "days_overdue": max(0, overdue),
                    "reminder": status,
                    "why": (f"Last revised {r['last_revised']}" if r["last_revised"] else f"Never revised (last studied {basis})")
                           + f", confidence {conf}/5 -> revise every {interval} day(s)."})
    df = pd.DataFrame(out, columns=["topic_id", "subject_name", "topic_name", "last_revised", "confidence",
                                    "interval_days", "due_date", "days_overdue", "reminder", "why"])
    order = {"Overdue": 0, "Due today": 1, "Upcoming": 2}
    if not df.empty:
        df = df.sort_values(by=["reminder", "days_overdue"], key=lambda c: c.map(order) if c.name == "reminder" else -c)
    return df.reset_index(drop=True)


def exam_readiness(conn, subject_id: int, today: date | None = None) -> dict:
    """Estimate (0-100) = 50% syllabus completion + 20% revision + 30% quiz performance.

    If a component has no data (e.g. no quizzes yet) its weight is shared among the others
    and `notes` says so. `data_confidence` is low when few topics have been quizzed.
    """
    today = today or date.today()
    topics = conn.execute("SELECT topic_id, status, estimated_hours FROM topics WHERE subject_id = ?", (subject_id,)).fetchall()
    if not topics:
        return {"estimate": None, "notes": ["This subject has no topics yet."], "disclaimer": DISCLAIMER}
    total_h = sum(t["estimated_hours"] for t in topics)
    done_h = sum(t["estimated_hours"] for t in topics if t["status"] == "completed")
    half_h = sum(t["estimated_hours"] * 0.5 for t in topics if t["status"] == "in_progress")
    completion = 100 * (done_h + half_h) / total_h if total_h else 0.0

    rem = revision_reminders(conn, today)
    rem = rem[rem["topic_id"].isin([t["topic_id"] for t in topics if t["status"] == "completed"])]
    revision = None
    if not rem.empty:
        vals = []
        for r in rem.itertuples():
            if r.confidence is None or pd.isna(r.confidence):
                vals.append(0.0)                      # completed but never revised
            else:
                base = float(r.confidence) / 5
                vals.append(base * (0.5 if r.days_overdue > 0 else 1.0))
        revision = 100 * sum(vals) / len([t for t in topics if t["status"] == "completed"])
    elif any(t["status"] == "completed" for t in topics):
        revision = 0.0

    quiz_vals = [recent_average_pct(conn, t["topic_id"], 1) for t in topics]
    quiz_vals = [v for v in quiz_vals if v is not None]
    quiz = sum(quiz_vals) / len(quiz_vals) if quiz_vals else None
    coverage = len(quiz_vals) / len(topics)

    parts = {"completion": completion, "revision": revision, "quiz": quiz}
    present = {k: v for k, v in parts.items() if v is not None}
    wsum = sum(WEIGHTS[k] for k in present)
    estimate = sum(WEIGHTS[k] * v for k, v in present.items()) / wsum
    notes = []
    if revision is None:
        notes.append("No completed topics yet, so revision is not counted.")
    if quiz is None:
        notes.append("No quizzes taken yet, so quiz performance is not counted.")
    if coverage < 0.5:
        notes.append(f"Only {len(quiz_vals)} of {len(topics)} topics have a quiz result - treat this estimate as low-confidence.")
    band = "Needs a lot of work" if estimate < 40 else ("Getting there" if estimate < 70 else "Looking good so far")
    return {"estimate": round(estimate, 1), "band": band, "components": {k: (None if v is None else round(v, 1)) for k, v in parts.items()},
            "weights": WEIGHTS, "quiz_coverage_pct": round(100 * coverage), "data_confidence": "low" if coverage < 0.5 else "medium",
            "notes": notes, "disclaimer": DISCLAIMER}
