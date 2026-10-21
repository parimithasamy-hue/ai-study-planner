import random
import unittest
from datetime import date, timedelta

from tests.helpers import fresh_db
from planner import db, scheduler
from planner.scheduler import Task, plan_days

TODAY = date(2026, 10, 21)


def make_task(i, sid=1, exam_in=10, prio=3, diff=3, mins=60, status="pending", weak=False):
    return Task(i, f"T{i}", sid, f"S{sid}", TODAY + timedelta(days=exam_in), prio, diff, mins, status,
                weak, 30.0 if weak else None, 50)


def day_totals(blocks, brk):
    """Total minutes (study + breaks between blocks) per day."""
    per = {}
    for b in blocks:
        per.setdefault(b.plan_date, []).append(b.minutes)
    return {d: sum(v) + brk * (len(v) - 1) for d, v in per.items()}


class PureSchedulerTests(unittest.TestCase):
    def test_never_exceeds_daily_limit_random(self):
        rng = random.Random(42)
        for trial in range(300):
            limit = rng.choice([30, 45, 60, 90, 120, 240])
            brk = rng.choice([0, 5, 10])
            tasks = [make_task(i, sid=rng.randint(1, 3), exam_in=rng.randint(1, 30), prio=rng.randint(1, 5),
                               diff=rng.randint(1, 5), mins=rng.choice([20, 45, 60, 150, 180]),
                               status=rng.choice(["pending", "in_progress"]), weak=rng.random() < .3) for i in range(rng.randint(1, 15))]
            caps = {1: rng.choice([30, 60, 120]), 2: 120, 3: 45}
            blocks, left = plan_days(tasks, TODAY, limit, caps, break_minutes=brk)
            for d, total in day_totals(blocks, brk).items():
                self.assertLessEqual(total, limit, (trial, d))
            per_subject = {}
            for b in blocks:
                per_subject[(b.plan_date, b.task.subject_id)] = per_subject.get((b.plan_date, b.task.subject_id), 0) + b.minutes
            for (d, sid), m in per_subject.items():
                self.assertLessEqual(m, caps[sid])
            # nothing silently dropped: scheduled + leftover == requested for every task
            sched = {}
            for b in blocks:
                sched[b.task.topic_id] = sched.get(b.task.topic_id, 0) + b.minutes
            lo = {}
            for l in left:
                lo[l.task.topic_id] = lo.get(l.task.topic_id, 0) + l.minutes
            for t in tasks:
                self.assertEqual(sched.get(t.topic_id, 0) + lo.get(t.topic_id, 0), t.remaining_minutes, (trial, t.topic_id))

    def test_no_duplicate_topic_per_day_and_never_on_or_after_exam(self):
        tasks = [make_task(i, exam_in=i % 6 + 1, mins=300) for i in range(1, 8)]
        blocks, _ = plan_days(tasks, TODAY, 240)
        seen = set()
        for b in blocks:
            key = (b.plan_date, b.task.topic_id)
            self.assertNotIn(key, seen)
            seen.add(key)
            self.assertLess(b.plan_date, b.task.exam_date)
            self.assertGreaterEqual(b.plan_date, TODAY)

    def test_insufficient_time_is_reported_not_dropped(self):
        t = make_task(1, exam_in=2, mins=600)
        blocks, left = plan_days([t], TODAY, 60)
        self.assertEqual(sum(b.minutes for b in blocks) + left[0].minutes, 600)
        self.assertGreater(left[0].minutes, 0)
        self.assertIn("Not enough", left[0].why)

    def test_exam_today_or_past_reported(self):
        _, left = plan_days([make_task(1, exam_in=0), make_task(2, exam_in=-3)], TODAY, 120)
        self.assertEqual(len(left), 2)

    def test_prioritisation_weak_hard_and_near_exam_first(self):
        far_easy = make_task(1, exam_in=25, diff=1, prio=2)
        near_weak_hard = make_task(2, exam_in=3, diff=5, prio=5, weak=True)
        blocks, _ = plan_days([far_easy, near_weak_hard], TODAY, 60)
        self.assertEqual(blocks[0].task.topic_id, 2)
        self.assertIn("weak quiz score", blocks[0].reason)
        self.assertIn("exam in", blocks[0].reason)

    def test_breaks_count_toward_limit(self):
        tasks = [make_task(i, mins=30, exam_in=20) for i in range(1, 5)]
        blocks, _ = plan_days(tasks, TODAY, 70, break_minutes=10)
        day0 = [b for b in blocks if b.plan_date == TODAY]
        self.assertEqual([b.minutes for b in day0], [30, 30])    # 30+10+30 = 70, a third block would not fit
        self.assertLessEqual(day_totals(blocks, 10)[TODAY], 70)

    def test_hard_topics_get_longer_blocks(self):
        blocks, _ = plan_days([make_task(1, diff=5, mins=200), make_task(2, diff=2, mins=200)], TODAY, 600)
        d0 = {b.task.topic_id: b.minutes for b in blocks if b.plan_date == TODAY}
        self.assertEqual(d0[1], 90)
        self.assertEqual(d0[2], 60)

    def test_every_block_has_a_reason(self):
        blocks, _ = plan_days([make_task(i) for i in range(1, 6)], TODAY, 120)
        self.assertTrue(blocks and all(b.reason.startswith("Recommended because:") for b in blocks))


class DatabaseSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db(self)
        db.save_settings(self.conn, 120, 50, 3, 5)

    def planned_rows(self):
        return self.conn.execute("""SELECT p.plan_date, p.topic_id, p.planned_minutes, t.subject_id
                                    FROM study_plan p JOIN topics t USING(topic_id)
                                    WHERE p.status IN ('planned','completed') ORDER BY p.plan_date, p.plan_id""").fetchall()

    def assert_db_within_limits(self, limit):
        per, keys = {}, set()
        for r in self.planned_rows():
            per.setdefault(r["plan_date"], []).append(r["planned_minutes"])
            self.assertNotIn((r["plan_date"], r["topic_id"]), keys)
            keys.add((r["plan_date"], r["topic_id"]))
        for d, v in per.items():
            self.assertLessEqual(sum(v) + 5 * (len(v) - 1), limit, d)

    def test_generate_plan_respects_limit_and_saves(self):
        blocks, left = scheduler.generate_plan(self.conn, TODAY)
        self.assertTrue(blocks)
        self.assert_db_within_limits(120)
        # completed topics are never scheduled
        done = {r[0] for r in self.conn.execute("SELECT topic_id FROM topics WHERE status='completed'")}
        self.assertFalse(done & {b.task.topic_id for b in blocks})

    def test_generate_twice_does_not_duplicate(self):
        scheduler.generate_plan(self.conn, TODAY)
        n1 = len(self.planned_rows())
        scheduler.generate_plan(self.conn, TODAY)
        self.assertEqual(n1, len(self.planned_rows()))
        self.assert_db_within_limits(120)

    def test_small_limit_returns_leftovers(self):
        db.save_settings(self.conn, 30, 50, 3, 5)
        blocks, left = scheduler.generate_plan(self.conn, TODAY)
        self.assertTrue(left, "with a 30-minute day some tasks cannot fit and must be reported")
        self.assert_db_within_limits(30)

    def test_weak_topics_are_marked_in_reasons(self):
        blocks, _ = scheduler.generate_plan(self.conn, TODAY)
        weak_blocks = [b for b in blocks if b.task.topic_id in (4, 34)]
        self.assertTrue(weak_blocks)
        self.assertTrue(all("weak quiz score" in b.reason for b in weak_blocks))

    def test_recovery_redistributes_without_exceeding_limit(self):
        # the supplied study_plan rows are dated 2026-10-22..24; pretend today is 2026-10-25 so they are missed
        scheduler.generate_plan(self.conn, date(2026, 10, 25))
        before_missed = self.conn.execute("SELECT COUNT(*) FROM study_plan WHERE plan_date < '2026-10-25'").fetchone()[0]
        self.assertEqual(before_missed, 6)
        blocks, left = scheduler.recover_missed(self.conn, date(2026, 10, 25))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM study_plan WHERE status='missed'").fetchone()[0], 6)
        self.assertTrue(blocks)
        self.assertTrue(all("recovered from missed" in b.reason for b in blocks))
        self.assert_db_within_limits(120)
        placed = sum(b.minutes for b in blocks) + sum(l.minutes for l in left)
        # topic 34 is already 'completed' in the supplied data, so its 40 missed minutes need no recovery
        self.assertEqual(placed, 45 + 45 + 30 + 60 + 45)               # every other missed minute is accounted for
        self.assertEqual(self.conn.execute("SELECT rescheduled FROM study_plan WHERE topic_id = 34").fetchone()[0], 1)
        # running it again must not duplicate work
        again, _ = scheduler.recover_missed(self.conn, date(2026, 10, 25))
        self.assertEqual(again, [])

    def test_recovery_respects_small_limit_and_reports_leftover(self):
        db.save_settings(self.conn, 30, 50, 3, 5)
        blocks, left = scheduler.recover_missed(self.conn, date(2026, 10, 25))
        self.assert_db_within_limits(30)
        self.assertEqual(sum(b.minutes for b in blocks) + sum(l.minutes for l in left), 225)   # 265 minus completed topic 34

    def test_subject_daily_cap_enforced(self):
        self.conn.execute("UPDATE subjects SET daily_minutes = 30 WHERE subject_id = 1")
        self.conn.commit()
        blocks, _ = scheduler.generate_plan(self.conn, TODAY)
        per = {}
        for b in blocks:
            if b.task.subject_id == 1:
                per[b.plan_date] = per.get(b.plan_date, 0) + b.minutes
        self.assertTrue(per and all(v <= 30 for v in per.values()))

    def test_with_breaks_display(self):
        rows = scheduler.with_breaks([{"a": 1}, {"a": 2}, {"a": 3}], 5)
        self.assertEqual([r["kind"] for r in rows], ["study", "break", "study", "break", "study"])


if __name__ == "__main__":
    unittest.main()
