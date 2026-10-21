from datetime import date

import streamlit as st

from planner import db
from views.common import run_action, topic_options


def render(conn):
    st.header("Study sessions")
    topics = topic_options(conn)
    if not topics:
        st.info("Add topics first, then log your study sessions here.")
        return

    plan = db.plan_df(conn, "planned")
    today_items = plan[plan["plan_date"] == date.today().isoformat()] if not plan.empty else plan
    plan_map = {0: "Not from the plan"}
    plan_map.update({int(r["plan_id"]): f"{r['topic_name']} ({r['planned_minutes']} min planned)" for r in today_items.to_dict("records")})
    pid = st.selectbox("Log from today's plan (optional)", list(plan_map), format_func=lambda i: plan_map[i])
    default_topic, default_planned = list(topics)[0], 30
    if pid:
        r = today_items[today_items["plan_id"] == pid].iloc[0]
        default_topic, default_planned = int(r["topic_id"]), int(r["planned_minutes"])

    with st.form("log_session", clear_on_submit=False):
        tid = st.selectbox("Topic", list(topics), index=list(topics).index(default_topic), format_func=lambda i: topics[i])
        when = st.date_input("Date", value=date.today(), max_value=date.today())
        c1, c2 = st.columns(2)
        planned = c1.number_input("Planned minutes", 1, 720, default_planned, step=5)
        actual = c2.number_input("Actual minutes studied", 1, 720, default_planned, step=5)
        completed = st.checkbox("I completed what I planned for this session")
        notes = st.text_area("Notes (optional)", max_chars=500)
        if st.form_submit_button("Save session"):
            run_action(db.add_session, "Session saved.", conn, tid, when, planned, actual, completed, notes, pid or None)

    st.subheader("History")
    df = db.sessions_df(conn)
    if df.empty:
        st.info("No sessions logged yet.")
    else:
        df["completed"] = df["completed"].map({1: "Yes", 0: "No"})
        st.dataframe(df, hide_index=True)
