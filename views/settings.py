import streamlit as st

from planner import config, db
from views.common import run_action


def render(conn):
    st.header("Settings")
    with st.form("settings"):
        limit = st.number_input("Daily study limit (minutes, includes breaks)", 15, 960, db.get_setting(conn, "daily_limit_minutes"), step=15)
        c1, c2 = st.columns(2)
        thr = c1.slider("Weak-topic threshold (%)", 1, 99, db.get_setting(conn, "weak_threshold_pct"))
        n = c2.slider("Recent quizzes to average", 1, 10, db.get_setting(conn, "weak_recent_quizzes"))
        brk = st.slider("Break between study blocks (minutes)", 0, 30, db.get_setting(conn, "break_minutes"))
        if st.form_submit_button("Save settings"):
            run_action(db.save_settings, "Settings saved. Regenerate the timetable to apply them.", conn, limit, thr, n, brk)

    st.subheader("About your data")
    flagged = conn.execute("SELECT COUNT(*) FROM quiz_questions WHERE needs_review = 1").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM quiz_questions").fetchone()[0]
    st.write(f"Database file: `{config.DB_PATH}`")
    st.write(f"Question bank: {total} questions. **{flagged}** reuse the exact same question text under more than one topic "
             "(a property of the supplied sample data), so they may not match every topic they are attached to. "
             "Review and replace them with questions for your real syllabus.")
    st.caption("To start over with the supplied demo data, close the app, delete data/study_planner.db and start it again - "
               "it is re-created from data/original/study_planner.db.")
