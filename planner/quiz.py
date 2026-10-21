"""Quiz selection, scoring, saving and weak-topic detection (all explainable rules)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .validators import ValidationError, check_int

LETTERS = ("A", "B", "C", "D")


@dataclass
class ScoredQuestion:
    question_id: int
    question_text: str
    chosen: str | None
    correct: str
    is_correct: bool
    explanation: str
    options: dict = field(default_factory=dict)


@dataclass
class QuizScore:
    score: int
    total: int
    details: list

    @property
    def percent(self) -> float:
        return round(100.0 * self.score / self.total, 1) if self.total else 0.0


def fetch_questions(conn, topic_id: int, limit: int | None = None, seed: int | None = None) -> list[dict]:
    rows = conn.execute("SELECT * FROM quiz_questions WHERE topic_id = ? ORDER BY question_id", (topic_id,)).fetchall()
    questions = [dict(r) for r in rows]
    rng = random.Random(seed)
    rng.shuffle(questions)
    if limit is not None:
        questions = questions[:max(0, int(limit))]
    return questions


def option_order(question: dict, shuffle: bool = True, rng: random.Random | None = None) -> list[str]:
    """Return the letters in the order they should be shown. Scoring always uses the original letter."""
    letters = list(LETTERS)
    if shuffle:
        (rng or random).shuffle(letters)
    return letters


def option_text(question: dict, letter: str) -> str:
    return str(question["option_" + letter.lower()])


def score_answers(questions: list[dict], answers: dict) -> QuizScore:
    """Score a quiz. `answers` maps question_id -> chosen letter ('A'-'D') or None/missing (counts as wrong)."""
    if not questions:
        raise ValidationError("There are no questions to score.")
    details = []
    score = 0
    for q in questions:
        chosen = answers.get(q["question_id"])
        if chosen is not None and chosen not in LETTERS:
            raise ValidationError(f"Invalid answer '{chosen}' for question {q['question_id']}.")
        ok = chosen == q["correct_option"]
        score += int(ok)
        details.append(ScoredQuestion(q["question_id"], q["question_text"], chosen, q["correct_option"], ok,
                                      q["explanation"], {l: option_text(q, l) for l in LETTERS}))
    return QuizScore(score, len(questions), details)


def save_result(conn, topic_id: int, result: QuizScore, quiz_date: date | None = None) -> int:
    """Save the score into quiz_results (existing table) and the per-question answers into quiz_answers."""
    when = (quiz_date or date.today()).isoformat()
    try:
        cur = conn.execute("INSERT INTO quiz_results(topic_id, quiz_date, score, total_questions) VALUES (?,?,?,?)",
                           (topic_id, when, result.score, result.total))
        quiz_id = cur.lastrowid
        conn.executemany("INSERT INTO quiz_answers(quiz_id, question_id, chosen_option, is_correct) VALUES (?,?,?,?)",
                         [(quiz_id, d.question_id, d.chosen, int(d.is_correct)) for d in result.details])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return quiz_id


# --------------------------------------------------------------------------- weak topics
def recent_average_pct(conn, topic_id: int, n_recent: int) -> float | None:
    """Average percentage of the topic's n most recent quizzes (None if never quizzed)."""
    rows = conn.execute("""SELECT 100.0 * score / total_questions AS pct FROM quiz_results
                           WHERE topic_id = ? ORDER BY quiz_date DESC, quiz_id DESC LIMIT ?""",
                        (topic_id, int(n_recent))).fetchall()
    return round(sum(r["pct"] for r in rows) / len(rows), 1) if rows else None


def weak_topics(conn, threshold_pct: float = 50, n_recent: int = 3) -> pd.DataFrame:
    """Topics whose average over their last `n_recent` quizzes is strictly below `threshold_pct`.

    Rule shown to the user: average(last N quiz %) < threshold  ->  weak.
    """
    threshold_pct = check_int(threshold_pct, "Threshold", 1, 99)
    n_recent = check_int(n_recent, "Recent quizzes", 1, 10)
    rows = conn.execute("""SELECT t.topic_id, s.subject_name, t.topic_name FROM topics t
                           JOIN subjects s ON s.subject_id = t.subject_id
                           WHERE EXISTS (SELECT 1 FROM quiz_results q WHERE q.topic_id = t.topic_id)
                           ORDER BY s.subject_name, t.topic_id""").fetchall()
    out = []
    for r in rows:
        avg = recent_average_pct(conn, r["topic_id"], n_recent)
        if avg is not None and avg < threshold_pct:
            out.append({"topic_id": r["topic_id"], "subject_name": r["subject_name"], "topic_name": r["topic_name"],
                        "recent_avg_pct": avg, "threshold_pct": threshold_pct, "quizzes_averaged": n_recent})
    df = pd.DataFrame(out, columns=["topic_id", "subject_name", "topic_name", "recent_avg_pct",
                                    "threshold_pct", "quizzes_averaged"])
    return df.sort_values("recent_avg_pct").reset_index(drop=True)


def quiz_results_df(conn) -> pd.DataFrame:
    return pd.read_sql_query("""SELECT q.quiz_id, q.quiz_date, s.subject_name, t.topic_name, q.score,
                                       q.total_questions, ROUND(100.0 * q.score / q.total_questions, 1) AS percent
                                FROM quiz_results q JOIN topics t ON t.topic_id = q.topic_id
                                JOIN subjects s ON s.subject_id = t.subject_id
                                ORDER BY q.quiz_date DESC, q.quiz_id DESC""", conn)
