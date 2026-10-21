import random
import unittest

from tests.helpers import fresh_db
from planner import quiz
from planner.validators import ValidationError
from datetime import date


class QuizTests(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db(self)
        self.qs = quiz.fetch_questions(self.conn, 1, seed=1)

    def test_every_topic_has_questions(self):
        for tid in range(1, 44):
            self.assertGreaterEqual(len(quiz.fetch_questions(self.conn, tid)), 1)

    def test_all_correct_all_wrong_and_blank(self):
        perfect = quiz.score_answers(self.qs, {q["question_id"]: q["correct_option"] for q in self.qs})
        self.assertEqual((perfect.score, perfect.total, perfect.percent), (len(self.qs), len(self.qs), 100.0))
        wrong = {q["question_id"]: next(l for l in "ABCD" if l != q["correct_option"]) for q in self.qs}
        self.assertEqual(quiz.score_answers(self.qs, wrong).score, 0)
        self.assertEqual(quiz.score_answers(self.qs, {}).score, 0)       # unanswered counts as wrong

    def test_partial_score_and_explanations(self):
        answers = {q["question_id"]: q["correct_option"] for q in self.qs[:2]}
        res = quiz.score_answers(self.qs, answers)
        self.assertEqual(res.score, 2)
        self.assertTrue(all(d.explanation for d in res.details))

    def test_invalid_answer_and_empty_quiz(self):
        with self.assertRaises(ValidationError):
            quiz.score_answers(self.qs, {self.qs[0]["question_id"]: "Z"})
        with self.assertRaises(ValidationError):
            quiz.score_answers([], {})

    def test_shuffled_display_still_scores_by_original_letter(self):
        q = self.qs[0]
        order = quiz.option_order(q, True, random.Random(7))
        self.assertEqual(sorted(order), list("ABCD"))
        shown_correct = quiz.option_text(q, q["correct_option"])
        picked = next(l for l in order if quiz.option_text(q, l) == shown_correct)
        self.assertTrue(quiz.score_answers([q], {q["question_id"]: picked}).details[0].is_correct)

    def test_save_result_in_sqlite(self):
        before = self.conn.execute("SELECT COUNT(*) FROM quiz_results").fetchone()[0]
        res = quiz.score_answers(self.qs, {q["question_id"]: q["correct_option"] for q in self.qs[:3]})
        qid = quiz.save_result(self.conn, 1, res, date(2026, 10, 21))
        row = self.conn.execute("SELECT * FROM quiz_results WHERE quiz_id=?", (qid,)).fetchone()
        self.assertEqual((row["score"], row["total_questions"], row["quiz_date"]), (3, len(self.qs), "2026-10-21"))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM quiz_results").fetchone()[0], before + 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM quiz_answers WHERE quiz_id=?", (qid,)).fetchone()[0], len(self.qs))

    def test_weak_topics_threshold_is_configurable(self):
        w50 = set(quiz.weak_topics(self.conn, 50, 1)["topic_id"])
        w70 = set(quiz.weak_topics(self.conn, 70, 1)["topic_id"])
        self.assertEqual(w50, {4, 34})            # 40% and 40% in the supplied data
        self.assertTrue(w50 < w70)
        self.assertIn(17, w70)                    # 50% is not < 50 but is < 70
        self.assertNotIn(17, w50)                 # boundary: strictly below the threshold

    def test_weak_topics_uses_recent_average(self):
        for s in (0, 0):
            self.conn.execute("INSERT INTO quiz_results(topic_id, quiz_date, score, total_questions) VALUES (1,'2026-10-21',?,10)", (s,))
        self.conn.commit()
        self.assertIn(1, set(quiz.weak_topics(self.conn, 50, 3)["topic_id"]))   # (0+0+80)/3 = 26.7
        with self.assertRaises(ValidationError):
            quiz.weak_topics(self.conn, 0, 3)


if __name__ == "__main__":
    unittest.main()
