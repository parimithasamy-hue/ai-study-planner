"""Rule-based timetable generator and missed-study recovery.

Everything here is deterministic and explainable. A topic's priority score is the sum of:
  exam proximity  0-40   (closer exam -> higher)
  subject priority 4 x (1-5)
  difficulty       3 x (1-5)
  weak quiz score  +20   (recent average below the user's threshold)
  in progress      +5    (finish what is started)
HARD RULE: for every day, study minutes + breaks never exceed the daily limit (and the
subject's own daily cap). Whatever does not fit is returned as `leftovers`, never dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import config, db
from .quiz import weak_topics


@dataclass
class Task:
    topic_id: int
    topic_name: str
    subject_id: int
    subject_name: str
    exam_date: date | None
    priority: int
    difficulty: int
    remaining_minutes: int
    status: str = "pending"
    weak: bool = False
    recent_avg_pct: float | None = None
    weak_threshold: float = 50
    origin_note: str = ""          # e.g. "Recovered from missed 2026-10-20"


@dataclass
class Block:
    plan_date: date
    task: Task
    minutes: int
    reason: str


@dataclass
class Leftover:
    task: Task
    minutes: int
    why: str


def block_cap(difficulty: int, max_block: int = 60) -> int:
    return config.HARD_TOPIC_BLOCK_MINUTES if difficulty >= 4 else max_block


def score_task(task: Task, on_day: date) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    days_left = (task.exam_date - on_day).days if task.exam_date else None
    if days_left is not None:
        prox = 40 * max(0.0, 1 - days_left / 30)
        score += prox
        reasons.append(f"exam in {days_left} day{'s' if days_left != 1 else ''}")
    else:
        reasons.append("no exam date set")
    score += 4 * task.priority
    reasons.append(f"subject priority {task.priority}/5")
    score += 3 * task.difficulty
    reasons.append(f"difficulty {task.difficulty}/5" + (" (longer block)" if task.difficulty >= 4 else ""))
    if task.weak and task.recent_avg_pct is not None:
        score += 20
        reasons.append(f"weak quiz score ({task.recent_avg_pct:.0f}% < {task.weak_threshold:.0f}% threshold)")
    if task.status == "in_progress":
        score += 5
        reasons.append("already in progress")
    elif task.status == "pending":
        reasons.append("not started yet")
    if task.origin_note:
        reasons.insert(0, task.origin_note)
    return score, reasons


def plan_days(tasks: list[Task], start: date, daily_limit: int, subject_caps: dict[int, int] | None = None,
              used_minutes: dict[date, int] | None = None, used_subject: dict[tuple, int] | None = None,
              taken_pairs: set | None = None, break_minutes: int = 5, max_block: int = 60,
              horizon_days: int | None = None) -> tuple[list[Block], list[Leftover]]:
    """Pure scheduling function (no database). Returns (blocks, leftovers).

    * one block per topic per day (no duplicates)
    * a topic is only scheduled on days strictly before its exam
    * minutes + breaks per day <= daily_limit; minutes per subject per day <= subject cap
    """
    subject_caps = subject_caps or {}
    used = dict(used_minutes or {})
    used_subj = dict(used_subject or {})
    taken = set(taken_pairs or set())
    remaining = {t.topic_id: t.remaining_minutes for t in tasks}
    blocks: list[Block] = []
    leftovers: list[Leftover] = []

    active = []
    for t in tasks:
        if t.remaining_minutes <= 0:
            continue
        if t.exam_date is not None and t.exam_date <= start:
            leftovers.append(Leftover(t, t.remaining_minutes, "Exam date is today or already passed - nothing can be scheduled before it."))
        else:
            active.append(t)

    if horizon_days is None:
        dated = [t.exam_date for t in active if t.exam_date]
        last = max(dated) if dated else start + timedelta(days=14)
        horizon_days = min(config.MAX_PLAN_HORIZON_DAYS, max(1, (last - start).days))

    for offset in range(horizon_days):
        day = start + timedelta(days=offset)
        candidates = [t for t in active if remaining[t.topic_id] > 0
                      and (t.exam_date is None or day < t.exam_date)
                      and (day, t.topic_id) not in taken]
        ranked = sorted(candidates, key=lambda t: (-score_task(t, day)[0], t.topic_id))
        for t in ranked:
            gap = break_minutes if used.get(day, 0) > 0 else 0
            day_free = daily_limit - used.get(day, 0) - gap
            cap = subject_caps.get(t.subject_id, daily_limit)
            subj_free = cap - used_subj.get((day, t.subject_id), 0)
            size = min(remaining[t.topic_id], block_cap(t.difficulty, max_block), day_free, subj_free)
            if size <= 0:
                continue
            if size < config.MIN_BLOCK_MINUTES and size < remaining[t.topic_id]:
                continue                       # skip tiny fragments; try another topic/day
            _, why = score_task(t, day)
            blocks.append(Block(day, t, int(size), "Recommended because: " + "; ".join(why) + "."))
            used[day] = used.get(day, 0) + gap + size
            used_subj[(day, t.subject_id)] = used_subj.get((day, t.subject_id), 0) + size
            remaining[t.topic_id] -= size
            taken.add((day, t.topic_id))

    for t in active:
        if remaining[t.topic_id] > 0:
            leftovers.append(Leftover(t, remaining[t.topic_id],
                                      "Not enough free study time before the exam. Raise the daily limit, "
                                      "move the exam date, or drop a topic."))
    return blocks, leftovers


# --------------------------------------------------------------------------- database wrappers
def _remaining_minutes(estimated_hours: float, status: str) -> int:
    mins = estimated_hours * 60 * (0.5 if status == "in_progress" else 1.0)
    return max(5, int(round(mins / 5.0)) * 5)


def build_tasks(conn, topic_ids: set[int] | None = None) -> list[Task]:
    threshold = db.get_setting(conn, "weak_threshold_pct", float)
    n_recent = db.get_setting(conn, "weak_recent_quizzes", int)
    weak = {int(r.topic_id): float(r.recent_avg_pct) for r in weak_topics(conn, int(threshold), n_recent).itertuples()}
    rows = conn.execute("""SELECT t.topic_id, t.topic_name, t.difficulty, t.estimated_hours, t.status,
                                  s.subject_id, s.subject_name, s.exam_date, s.priority
                           FROM topics t JOIN subjects s ON s.subject_id = t.subject_id
                           WHERE t.status <> 'completed' ORDER BY t.topic_id""").fetchall()
    tasks = []
    for r in rows:
        if topic_ids is not None and r["topic_id"] not in topic_ids:
            continue
        exam = date.fromisoformat(r["exam_date"]) if r["exam_date"] else None
        tasks.append(Task(r["topic_id"], r["topic_name"], r["subject_id"], r["subject_name"], exam, r["priority"],
                          r["difficulty"], _remaining_minutes(r["estimated_hours"], r["status"]), r["status"],
                          r["topic_id"] in weak, weak.get(r["topic_id"]), threshold))
    return tasks


def _usage(conn, start: date):
    """Minutes already committed (planned/completed rows) from `start` onward, plus used (date, topic) pairs."""
    used: dict[date, int] = {}
    used_subj: dict[tuple, int] = {}
    pairs: set = set()
    brk = db.get_setting(conn, "break_minutes", int)
    rows = conn.execute("""SELECT p.plan_date, p.topic_id, p.planned_minutes, t.subject_id FROM study_plan p
                           JOIN topics t ON t.topic_id = p.topic_id
                           WHERE p.plan_date >= ? AND p.status IN ('planned','completed')
                           ORDER BY p.plan_date, p.plan_id""", (start.isoformat(),)).fetchall()
    for r in rows:
        d = date.fromisoformat(r["plan_date"])
        used[d] = used.get(d, 0) + r["planned_minutes"] + (brk if used.get(d, 0) > 0 else 0)
        used_subj[(d, r["subject_id"])] = used_subj.get((d, r["subject_id"]), 0) + r["planned_minutes"]
        pairs.add((d, r["topic_id"]))
    return used, used_subj, pairs


def _caps(conn) -> dict[int, int]:
    return {r["subject_id"]: r["daily_minutes"] for r in conn.execute("SELECT subject_id, daily_minutes FROM subjects")}


def _insert_blocks(conn, blocks: list[Block]) -> None:
    conn.executemany("INSERT INTO study_plan(plan_date, topic_id, planned_minutes, reason, status) VALUES (?,?,?,?, 'planned')",
                     [(b.plan_date.isoformat(), b.task.topic_id, b.minutes, b.reason) for b in blocks])


def generate_plan(conn, start: date | None = None) -> tuple[list[Block], list[Leftover]]:
    """Rebuild the plan from `start` (default today). Replaces only future 'planned' rows;
    completed / missed history and past rows are kept."""
    start = start or date.today()
    conn.execute("DELETE FROM study_plan WHERE status = 'planned' AND plan_date >= ?", (start.isoformat(),))
    used, used_subj, pairs = _usage(conn, start)
    tasks = build_tasks(conn)
    blocks, leftovers = plan_days(tasks, start, db.get_setting(conn, "daily_limit_minutes", int), _caps(conn),
                                  used, used_subj, pairs, db.get_setting(conn, "break_minutes", int),
                                  db.get_setting(conn, "max_block_minutes", int))
    _insert_blocks(conn, blocks)
    conn.commit()
    return blocks, leftovers


def recover_missed(conn, today: date | None = None) -> tuple[list[Block], list[Leftover]]:
    """Move unfinished work from past days into the coming days without exceeding the daily limit.

    1. 'planned' rows dated before today are marked 'missed'.
    2. Missed minutes per topic are re-scheduled from today onward, around what is already planned.
    3. Whatever cannot fit stays 'missed' and is returned as a leftover - nothing is silently lost.
    """
    today = today or date.today()
    conn.execute("UPDATE study_plan SET status = 'missed' WHERE status = 'planned' AND plan_date < ?", (today.isoformat(),))
    missed = conn.execute("""SELECT p.plan_id, p.plan_date, p.topic_id, p.planned_minutes, t.status AS topic_status
                             FROM study_plan p JOIN topics t ON t.topic_id = p.topic_id
                             WHERE p.status = 'missed' AND p.rescheduled = 0 ORDER BY p.plan_date, p.plan_id""").fetchall()
    by_topic: dict[int, list] = {}
    for r in missed:
        if r["topic_status"] == "completed":
            conn.execute("UPDATE study_plan SET rescheduled = 1 WHERE plan_id = ?", (r["plan_id"],))  # nothing left to do
            continue
        by_topic.setdefault(r["topic_id"], []).append(r)

    tasks = []
    for t in build_tasks(conn, set(by_topic)):
        total = sum(r["planned_minutes"] for r in by_topic[t.topic_id])
        t.remaining_minutes = total
        t.origin_note = f"recovered from missed session on {by_topic[t.topic_id][0]['plan_date']}"
        tasks.append(t)

    used, used_subj, pairs = _usage(conn, today)
    blocks, leftovers = plan_days(tasks, today, db.get_setting(conn, "daily_limit_minutes", int), _caps(conn),
                                  used, used_subj, pairs, db.get_setting(conn, "break_minutes", int),
                                  db.get_setting(conn, "max_block_minutes", int))
    _insert_blocks(conn, blocks)
    left_by_topic = {}
    for lo in leftovers:
        left_by_topic[lo.task.topic_id] = left_by_topic.get(lo.task.topic_id, 0) + lo.minutes
    for tid, rows in by_topic.items():
        left = left_by_topic.get(tid, 0)
        for r in rows:
            conn.execute("UPDATE study_plan SET rescheduled = 1 WHERE plan_id = ?", (r["plan_id"],))
        if left > 0:   # keep one 'missed' row carrying the unplaced minutes so it is shown again next time
            conn.execute("UPDATE study_plan SET rescheduled = 0, planned_minutes = ? WHERE plan_id = ?",
                         (left, rows[0]["plan_id"]))
    conn.commit()
    return blocks, leftovers


def with_breaks(day_rows: list[dict], break_minutes: int) -> list[dict]:
    """For display only: insert a short break row between consecutive study blocks of one day."""
    out = []
    for i, r in enumerate(day_rows):
        if i > 0 and break_minutes > 0:
            out.append({"kind": "break", "minutes": break_minutes, "label": "Short break"})
        out.append({"kind": "study", **r})
    return out
