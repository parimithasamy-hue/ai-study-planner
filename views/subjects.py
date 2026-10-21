from datetime import date, datetime

import streamlit as st

from planner import db
from views.common import run_action


def render(conn):
    st.header("Subjects")
    df = db.subjects_df(conn)
    if df.empty:
        st.info("No subjects yet - add your first one below.")
    else:
        st.dataframe(df.rename(columns={"subject_id": "ID", "subject_name": "Subject", "exam_date": "Exam date",
                                        "priority": "Priority (1-5)", "daily_minutes": "Daily study time (min)"}),
                     hide_index=True)

    add_tab, edit_tab = st.tabs(["Add subject", "Edit subject"])
    with add_tab:
        with st.form("add_subject", clear_on_submit=True):
            name = st.text_input("Subject name")
            has_exam = st.checkbox("This subject has an exam date", value=True)
            exam = st.date_input("Exam date", value=date.today())
            c1, c2 = st.columns(2)
            priority = c1.slider("Priority (5 = most important)", 1, 5, 3)
            minutes = c2.number_input("Daily study time for this subject (minutes)", 15, 720, 60, step=15)
            if st.form_submit_button("Add subject"):
                run_action(db.add_subject, f"Added subject '{name.strip()}'.", conn, name, exam if has_exam else None, priority, minutes)
    with edit_tab:
        if df.empty:
            st.caption("Nothing to edit yet.")
            return
        labels = {int(r.subject_id): r.subject_name for r in df.itertuples()}
        sid = st.selectbox("Choose a subject", list(labels), format_func=lambda i: labels[i])
        row = df[df["subject_id"] == sid].iloc[0]
        with st.form(f"edit_subject_{sid}"):
            name = st.text_input("Subject name", value=row["subject_name"])
            current = datetime.strptime(row["exam_date"], "%Y-%m-%d").date() if row["exam_date"] else date.today()
            has_exam = st.checkbox("This subject has an exam date", value=bool(row["exam_date"]))
            exam = st.date_input("Exam date", value=current)
            c1, c2 = st.columns(2)
            priority = c1.slider("Priority (5 = most important)", 1, 5, int(row["priority"]))
            minutes = c2.number_input("Daily study time for this subject (minutes)", 15, 720, int(row["daily_minutes"]), step=15)
            if st.form_submit_button("Save changes"):
                run_action(db.update_subject, "Subject updated.", conn, sid, name, exam if has_exam else None, priority, minutes)
