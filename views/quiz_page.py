import random

import streamlit as st

from planner import quiz
from views.common import run_action, topic_options  # noqa: F401  (run_action kept for symmetry)


def _clear_quiz_keys():
    for k in [k for k in st.session_state if str(k).startswith("quiz_q_")]:
        del st.session_state[k]


def render(conn):
    st.header("Quiz")
    topics = topic_options(conn)
    if not topics:
        st.info("Add topics first - quizzes are built per topic.")
        return
    state = st.session_state.get("quiz")

    if state is None:
        tid = st.selectbox("Choose a topic", list(topics), format_func=lambda i: topics[i])
        available = conn.execute("SELECT COUNT(*) FROM quiz_questions WHERE topic_id = ?", (tid,)).fetchone()[0]
        if available == 0:
            st.info("This topic has no quiz questions yet.")
            return
        n = st.slider("Number of questions", 1, available, available) if available > 1 else 1
        shuffle = st.checkbox("Shuffle answer positions", value=True,
                              help="Recommended: in the supplied question bank the correct answer is mostly A or B.")
        if st.button("Start quiz"):
            questions = quiz.fetch_questions(conn, tid, limit=n)
            rng = random.Random()
            _clear_quiz_keys()
            st.session_state["quiz"] = {"topic_id": tid, "questions": questions, "result": None, "quiz_id": None,
                                        "orders": {q["question_id"]: quiz.option_order(q, shuffle, rng) for q in questions}}
            st.rerun()
        return

    questions = state["questions"]
    st.subheader(topics.get(state["topic_id"], "Quiz"))
    if any(q.get("needs_review") for q in questions):
        st.warning("Some questions in this quiz are generic questions that the supplied question bank reuses under several "
                   "topics, so they may not match this topic exactly. They still count toward your score.")

    if state["result"] is None:
        with st.form("quiz_form"):
            for i, q in enumerate(questions, 1):
                st.markdown(f"**Q{i}. {q['question_text']}**")
                st.radio("Your answer", state["orders"][q["question_id"]], index=None, key=f"quiz_q_{q['question_id']}",
                         format_func=lambda letter, q=q: quiz.option_text(q, letter), label_visibility="collapsed")
            submitted = st.form_submit_button("Submit answers")
        if submitted:
            answers = {q["question_id"]: st.session_state.get(f"quiz_q_{q['question_id']}") for q in questions}
            unanswered = sum(1 for v in answers.values() if v is None)
            try:
                result = quiz.score_answers(questions, answers)
                state["quiz_id"] = quiz.save_result(conn, state["topic_id"], result)
            except Exception as exc:
                st.error(f"Could not score or save the quiz ({type(exc).__name__}: {exc}).")
                return
            state["result"] = result
            state["unanswered"] = unanswered
            st.rerun()
        if st.button("Cancel quiz"):
            st.session_state["quiz"] = None
            _clear_quiz_keys()
            st.rerun()
        return

    result = state["result"]
    (st.success if result.percent >= 50 else st.warning)(f"Score: {result.score} / {result.total} ({result.percent}%) - saved.")
    if state.get("unanswered"):
        st.caption(f"{state['unanswered']} unanswered question(s) were counted as wrong.")
    for i, d in enumerate(result.details, 1):
        with st.expander(f"Q{i}: {'Correct' if d.is_correct else 'Incorrect'} - {d.question_text}", expanded=not d.is_correct):
            st.write(f"Your answer: {'(none)' if d.chosen is None else d.options[d.chosen]}")
            st.write(f"Correct answer: {d.options[d.correct]}")
            st.info(d.explanation)
    if st.button("Take another quiz"):
        st.session_state["quiz"] = None
        _clear_quiz_keys()
        st.rerun()
