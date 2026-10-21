from datetime import date

import streamlit as st

from planner import db, quiz, readiness
from views.common import run_action, topic_options


def render(conn):
    st.header("Weak topics and revision")
    thr = db.get_setting(conn, "weak_threshold_pct")
    n = db.get_setting(conn, "weak_recent_quizzes")

    st.subheader("Weak-topic detection")
    st.caption(f"Rule: a topic is **weak** when the average of its last **{n}** quiz result(s) is **below {thr}%**. "
               "Change the numbers here and press Save.")
    c1, c2, c3 = st.columns([2, 2, 1])
    new_thr = c1.slider("Threshold (%)", 1, 99, thr)
    new_n = c2.slider("Recent quizzes to average", 1, 10, n)
    if c3.button("Save rule"):
        run_action(db.save_settings, "Weak-topic rule saved.", conn, db.get_setting(conn, "daily_limit_minutes"),
                   new_thr, new_n, db.get_setting(conn, "break_minutes"))
    weak = quiz.weak_topics(conn, thr, n)
    if weak.empty:
        st.success("No weak topics under the current rule.") if conn.execute("SELECT 1 FROM quiz_results LIMIT 1").fetchone() \
            else st.info("No quiz results yet - take a quiz to see weak topics.")
    else:
        st.dataframe(weak.rename(columns={"subject_name": "Subject", "topic_name": "Topic", "recent_avg_pct": "Recent average (%)",
                                          "threshold_pct": "Threshold (%)", "quizzes_averaged": "Quizzes averaged"}).drop(columns=["topic_id"]),
                     hide_index=True)

    st.subheader("Revision reminders")
    st.caption("Next revision = last revision date + interval. Interval by confidence (1-5): 1 -> 1 day, 2 -> 3, 3 -> 7, 4 -> 14, 5 -> 21 days. "
               "Topics studied but never revised use the last studied date and a default confidence of 3.")
    rem = readiness.revision_reminders(conn)
    if rem.empty:
        st.info("No studied topics yet, so nothing to revise.")
    else:
        st.dataframe(rem.drop(columns=["topic_id"]).rename(columns={
            "subject_name": "Subject", "topic_name": "Topic", "last_revised": "Last revised", "confidence": "Confidence",
            "interval_days": "Interval (days)", "due_date": "Due", "days_overdue": "Days overdue", "reminder": "Reminder", "why": "Why"}),
            hide_index=True)

    st.subheader("Log a revision")
    topics = topic_options(conn)
    if not topics:
        return
    with st.form("log_revision", clear_on_submit=True):
        tid = st.selectbox("Topic", list(topics), format_func=lambda i: topics[i])
        when = st.date_input("Revision date", value=date.today(), max_value=date.today())
        conf = st.slider("How confident do you feel? (1 = not at all, 5 = very)", 1, 5, 3)
        notes = st.text_input("Notes (optional)", max_chars=200)
        if st.form_submit_button("Save revision"):
            run_action(db.add_revision, "Revision logged.", conn, tid, when, conf, notes)
