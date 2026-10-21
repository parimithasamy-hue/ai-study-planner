import unittest
from datetime import date, timedelta

from tests.helpers import fresh_db
from planner import analytics, db, exports, notes, readiness
from planner.validators import ValidationError, check_exam_date, parse_date

TODAY = date(2026, 10, 21)


class ValidatorTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(check_exam_date("2026-11-01", TODAY), "2026-11-01")
        self.assertEqual(check_exam_date("2026-10-21", TODAY), "2026-10-21")      # today is allowed
        for bad in ["2026-10-20", "2026-02-30", "tomorrow", "", None, "2026/11/01"]:
            with self.assertRaises(ValidationError):
                check_exam_date(bad, TODAY)
        self.assertEqual(check_exam_date("2026-10-01", TODAY, allow_unchanged="2026-10-01"), "2026-10-01")
        self.assertEqual(parse_date(date(2026, 1, 2)), date(2026, 1, 2))


class ReadinessAndRevisionTests(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db(self)

    def test_revision_interval_depends_on_confidence(self):
        df = readiness.revision_reminders(self.conn, TODAY)
        low = df[df.topic_id == 4].iloc[0]       # confidence 2 on 2026-10-20 -> every 3 days
        high = df[df.topic_id == 25].iloc[0]     # confidence 5 on 2026-10-21 -> every 21 days
        self.assertEqual((low.interval_days, low.due_date), (3, "2026-10-23"))
        self.assertEqual((high.interval_days, high.due_date), (21, "2026-11-11"))
        self.assertEqual(low.reminder, "Upcoming")
        later = readiness.revision_reminders(self.conn, date(2026, 10, 30))
        self.assertEqual(later[later.topic_id == 4].iloc[0].reminder, "Overdue")
        self.assertEqual(later.iloc[0].reminder, "Overdue")                    # overdue sorted first

    def test_never_revised_topic_uses_last_studied(self):
        df = readiness.revision_reminders(self.conn, TODAY)
        r = df[df.topic_id == 2].iloc[0]         # in progress, studied 2026-10-18, never revised
        self.assertEqual(r.last_revised, "never")
        self.assertEqual(r.due_date, "2026-10-25")

    def test_readiness_range_notes_and_disclaimer(self):
        for sid in (1, 2, 3, 4):
            r = readiness.exam_readiness(self.conn, sid, TODAY)
            self.assertTrue(0 <= r["estimate"] <= 100)
            self.assertIn("not a guarantee", r["disclaimer"].lower())
        r3 = readiness.exam_readiness(self.conn, 3, TODAY)
        self.assertEqual(r3["data_confidence"], "low")
        self.assertTrue(any("low-confidence" in n for n in r3["notes"]))

    def test_readiness_improves_with_progress(self):
        before = readiness.exam_readiness(self.conn, 1, TODAY)["estimate"]
        self.conn.execute("UPDATE topics SET status='completed' WHERE subject_id=1")
        self.conn.commit()
        self.assertGreater(readiness.exam_readiness(self.conn, 1, TODAY)["estimate"], before)

    def test_readiness_empty_subject(self):
        sid = db.add_subject(self.conn, "Empty", None, 3, 60)
        self.assertIsNone(readiness.exam_readiness(self.conn, sid, TODAY)["estimate"])


class AnalyticsExportTests(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db(self)

    def test_dashboard_numbers_match_supplied_data(self):
        c = analytics.topic_status_counts(self.conn)
        self.assertEqual(c["total"], 43)
        prog = analytics.subject_progress_df(self.conn)
        self.assertEqual(int(prog.total_topics.sum()), 43)
        self.assertEqual(analytics.total_study_hours(self.conn), round((45+50+35+40+55+35+30+35+40+35+25)/60, 1))
        self.assertEqual(len(analytics.upcoming_exams_df(self.conn, TODAY)), 4)
        self.assertEqual(len(analytics.study_minutes_by_day(self.conn, 14, TODAY)), 14)

    def test_empty_states_do_not_crash(self):
        for t in ("quiz_results", "study_sessions", "revision_history", "study_plan"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.commit()
        self.assertIsNone(analytics.average_quiz_pct(self.conn))
        self.assertEqual(analytics.total_study_hours(self.conn), 0)
        self.assertTrue(readiness.revision_reminders(self.conn, TODAY) is not None)
        self.assertEqual(int(analytics.study_minutes_by_day(self.conn, 7, TODAY).minutes.sum()), 0)

    def test_csv_export_and_formula_injection_guard(self):
        db.add_subject(self.conn, "=HYPERLINK(\"x\")", None, 3, 60)
        data = exports.to_csv_bytes(exports.exports(self.conn)["subject_summary"])
        text = data.decode("utf-8-sig")
        self.assertTrue(text.startswith("subject_id,subject_name"))
        self.assertIn("'=HYPERLINK", text)
        self.assertNotIn(",=HYPERLINK", text)
        for name, df in exports.exports(self.conn).items():
            self.assertTrue(exports.to_csv_bytes(df).startswith(b"\xef\xbb\xbf"), name)


class NotesTests(unittest.TestCase):
    TEXT = ("Normalization is the process of organising data to reduce redundancy. "
            "A table in first normal form has atomic values. "
            "Second normal form removes partial dependencies on a composite key. "
            "Third normal form removes transitive dependencies between non-key columns. "
            "Good normalization helps prevent update anomalies and keeps data consistent. "
            "Students often forget that denormalization can speed up reads.")

    def test_offline_summary(self):
        r = notes.summarize_offline(self.TEXT, 3)
        self.assertEqual(len(r["summary"]), 3)
        self.assertTrue(all(s in self.TEXT for s in r["summary"]))
        self.assertIn("normalization", r["keywords"])
        self.assertTrue(r["practice_questions"])

    def test_validation_and_uploads(self):
        with self.assertRaises(ValidationError):
            notes.summarize_offline("too short")
        with self.assertRaises(ValidationError):
            notes.read_uploaded_text(b"x", "notes.exe")
        self.assertEqual(notes.read_uploaded_text("héllo".encode("utf-8"), "a.txt"), "héllo")
        self.assertEqual(notes.read_uploaded_text("héllo".encode("latin-1"), "a.TXT"), "héllo")

    def test_ai_is_optional(self):
        import os
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            ok, _ = notes.ai_available()
            self.assertFalse(ok)
            with self.assertRaises(ValidationError):
                notes.summarize_with_ai(self.TEXT)
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
