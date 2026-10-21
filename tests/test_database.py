import csv
import unittest

from tests.helpers import ROOT, fresh_db
from planner import config, db
from planner.validators import ValidationError
from datetime import date


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db(self)

    def test_supplied_data_preserved_after_migration(self):
        for table in ["subjects", "topics", "quiz_questions", "quiz_results", "study_sessions", "revision_history", "study_plan"]:
            with open(config.DATA_DIR / "original" / f"{table}.csv", newline="", encoding="utf-8") as f:
                expected = sum(1 for _ in csv.DictReader(f))
            actual = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            self.assertEqual(expected, actual, table)

    def test_questions_answers_explanations_unchanged(self):
        with open(config.DATA_DIR / "original" / "quiz_questions.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                r = self.conn.execute("SELECT * FROM quiz_questions WHERE question_id=?", (row["question_id"],)).fetchone()
                self.assertEqual(r["correct_option"], row["correct_option"])
                self.assertEqual(r["explanation"], row["explanation"])
                self.assertEqual(r["question_text"], row["question_text"])
                self.assertEqual(r["topic_id"], int(row["topic_id"]))

    def test_migration_is_idempotent_and_versioned(self):
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        db.migrate(self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0], 4)

    def test_foreign_keys_ok_and_integrity(self):
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_supplied_sample_queries_still_run(self):
        sql = (config.DATA_DIR / "original" / "sample_queries.sql").read_text(encoding="utf-8")
        statements = [s.strip() for s in sql.split(";") if "SELECT" in s.upper()]
        self.assertEqual(len(statements), 5)
        for s in statements:
            self.conn.execute(s).fetchall()

    def test_original_weak_topic_query_matches_app_default(self):
        from planner.quiz import weak_topics
        expected = {r[0] for r in self.conn.execute("""
            WITH ranked AS (SELECT q.*, ROW_NUMBER() OVER(PARTITION BY topic_id ORDER BY quiz_date DESC, quiz_id DESC) rn FROM quiz_results q)
            SELECT topic_id FROM ranked WHERE rn=1 AND 1.0*score/total_questions < 0.5""")}
        got = set(weak_topics(self.conn, 50, 1)["topic_id"])
        self.assertEqual(expected, got)

    def test_subject_crud_and_validation(self):
        sid = db.add_subject(self.conn, "  Physics ", "2026-12-01", 3, 60, today=date(2026, 10, 21))
        self.assertEqual(self.conn.execute("SELECT subject_name FROM subjects WHERE subject_id=?", (sid,)).fetchone()[0], "Physics")
        with self.assertRaises(ValidationError):
            db.add_subject(self.conn, "Physics", "2026-12-01", 3, 60, today=date(2026, 10, 21))   # duplicate
        with self.assertRaises(ValidationError):
            db.add_subject(self.conn, "Chem", "2026-10-01", 3, 60, today=date(2026, 10, 21))      # past exam
        with self.assertRaises(ValidationError):
            db.add_subject(self.conn, "Chem", "31-12-2026", 3, 60)                                  # bad format
        with self.assertRaises(ValidationError):
            db.add_subject(self.conn, "", "2026-12-01", 3, 60)
        with self.assertRaises(ValidationError):
            db.add_subject(self.conn, "Chem", "2027-01-01", 9, 60)                                  # priority
        db.update_subject(self.conn, sid, "Physics II", "2026-12-05", 4, 90, today=date(2026, 10, 21))
        row = self.conn.execute("SELECT * FROM subjects WHERE subject_id=?", (sid,)).fetchone()
        self.assertEqual((row["subject_name"], row["priority"], row["daily_minutes"]), ("Physics II", 4, 90))

    def test_sql_injection_text_is_stored_literally(self):
        evil = "x'); DROP TABLE subjects;--"
        db.add_subject(self.conn, evil, None, 3, 60)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0], 5)

    def test_topic_crud_and_validation(self):
        tid = db.add_topic(self.conn, 1, "Decorators", 4, 2.0, today=date(2026, 10, 21))
        with self.assertRaises(ValidationError):
            db.add_topic(self.conn, 1, "Decorators", 4, 2.0)
        with self.assertRaises(ValidationError):
            db.add_topic(self.conn, 1, "Bad", 7, 2.0)
        with self.assertRaises(ValidationError):
            db.add_topic(self.conn, 1, "Bad2", 3, -1)
        with self.assertRaises(ValidationError):
            db.add_topic(self.conn, 1, "Future", 3, 1, last_studied="2999-01-01")
        db.update_topic(self.conn, tid, "Decorators", 4, 2.5, "completed", "2026-10-20", today=date(2026, 10, 21))
        r = self.conn.execute("SELECT * FROM topics WHERE topic_id=?", (tid,)).fetchone()
        self.assertEqual((r["status"], r["estimated_hours"], r["last_studied_date"]), ("completed", 2.5, "2026-10-20"))

    def test_session_updates_topic_and_plan(self):
        pid = self.conn.execute("SELECT plan_id FROM study_plan LIMIT 1").fetchone()[0]
        tid = self.conn.execute("SELECT topic_id FROM study_plan WHERE plan_id=?", (pid,)).fetchone()[0]
        db.add_session(self.conn, tid, "2026-10-21", 45, 40, True, "ok", plan_id=pid)
        self.assertEqual(self.conn.execute("SELECT status FROM study_plan WHERE plan_id=?", (pid,)).fetchone()[0], "completed")
        self.assertEqual(self.conn.execute("SELECT last_studied_date FROM topics WHERE topic_id=?", (tid,)).fetchone()[0], "2026-10-21")
        with self.assertRaises(ValidationError):
            db.add_session(self.conn, tid, "2026-10-21", 45, 0, True)

    def test_settings_validation(self):
        db.save_settings(self.conn, 90, 60, 2, 10)
        self.assertEqual(db.get_setting(self.conn, "daily_limit_minutes"), 90)
        with self.assertRaises(ValidationError):
            db.save_settings(self.conn, 5, 60, 2, 10)
        with self.assertRaises(ValidationError):
            db.save_settings(self.conn, 90, 100, 2, 10)


if __name__ == "__main__":
    unittest.main()
