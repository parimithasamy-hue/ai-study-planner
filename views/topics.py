from datetime import date, datetime

import streamlit as st

from planner import db
from views.common import run_action, subject_options

STATUSES = ["pending", "in_progress", "completed"]


def render(conn):
    st.header("Topics")
    subjects = subject_options(conn)
    if not subjects:
        st.info("Add a subject first (Subjects page), then come back to add topics.")
        return
    choice = st.selectbox("Filter by subject", [0] + list(subjects), format_func=lambda i: "All subjects" if i == 0 else subjects[i])
    df = db.topics_df(conn, None if choice == 0 else choice)
    if df.empty:
        st.info("This subject has no topics yet - add one below.")
    else:
        st.dataframe(df.drop(columns=["subject_id"]).rename(columns={
            "topic_id": "ID", "subject_name": "Subject", "topic_name": "Topic", "difficulty": "Difficulty (1-5)",
            "estimated_hours": "Est. hours", "status": "Status", "last_studied_date": "Last studied"}), hide_index=True)

    add_tab, edit_tab = st.tabs(["Add topic", "Edit topic"])
    with add_tab:
        with st.form("add_topic", clear_on_submit=True):
            sid = st.selectbox("Subject", list(subjects), format_func=lambda i: subjects[i],
                               index=list(subjects).index(choice) if choice else 0)
            name = st.text_input("Topic name")
            c1, c2, c3 = st.columns(3)
            diff = c1.slider("Difficulty", 1, 5, 3)
            hours = c2.number_input("Estimated hours", 0.25, 40.0, 1.0, step=0.25)
            status = c3.selectbox("Status", STATUSES)
            has_last = st.checkbox("Set a last studied date")
            last = st.date_input("Last studied date", value=date.today(), max_value=date.today())
            if st.form_submit_button("Add topic"):
                run_action(db.add_topic, f"Added topic '{name.strip()}'.", conn, sid, name, diff, hours, status, last if has_last else None)
    with edit_tab:
        if df.empty:
            st.caption("Nothing to edit yet.")
            return
        labels = {int(r.topic_id): f"{r.subject_name} - {r.topic_name}" for r in df.itertuples()}
        tid = st.selectbox("Choose a topic", list(labels), format_func=lambda i: labels[i])
        row = df[df["topic_id"] == tid].iloc[0]
        with st.form(f"edit_topic_{tid}"):
            name = st.text_input("Topic name", value=row["topic_name"])
            c1, c2, c3 = st.columns(3)
            diff = c1.slider("Difficulty", 1, 5, int(row["difficulty"]))
            hours = c2.number_input("Estimated hours", 0.25, 40.0, float(row["estimated_hours"]), step=0.25)
            status = c3.selectbox("Status", STATUSES, index=STATUSES.index(row["status"]))
            has_last = st.checkbox("Has a last studied date", value=bool(row["last_studied_date"]))
            cur = datetime.strptime(row["last_studied_date"], "%Y-%m-%d").date() if row["last_studied_date"] else date.today()
            last = st.date_input("Last studied date", value=cur, max_value=date.today())
            if st.form_submit_button("Save changes"):
                run_action(db.update_topic, "Topic updated.", conn, tid, name, diff, hours, status, last if has_last else None)
