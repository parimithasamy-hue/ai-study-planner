from datetime import date

import pandas as pd
import streamlit as st

from planner import db, scheduler
from views.common import run_action


def _leftover_rows(leftovers):
    return [{"Subject": l.task.subject_name, "Topic": l.task.topic_name, "Minutes not scheduled": l.minutes,
             "Why": l.why} for l in leftovers]


def render(conn):
    st.header("Timetable")
    limit = db.get_setting(conn, "daily_limit_minutes")
    brk = db.get_setting(conn, "break_minutes")
    st.caption(f"Daily limit: **{limit} min** (study + breaks) - change it on the Settings page. "
               "Each subject also has its own daily cap (Subjects page). The planner never schedules past these limits.")

    c1, c2 = st.columns(2)
    done = False
    if c1.button("Generate / refresh timetable"):
        try:
            blocks, leftovers = scheduler.generate_plan(conn)
            st.session_state["leftovers"] = _leftover_rows(leftovers)
            st.session_state["plan_msg"] = f"Scheduled {len(blocks)} study blocks from today."
            done = True
        except Exception as exc:
            conn.rollback()
            st.error(f"Could not generate the timetable ({type(exc).__name__}: {exc}).")
    if c2.button("Recover missed study"):
        try:
            blocks, leftovers = scheduler.recover_missed(conn)
            st.session_state["leftovers"] = _leftover_rows(leftovers)
            st.session_state["plan_msg"] = (f"Moved missed work into {len(blocks)} new block(s)." if blocks
                                            else "No missed work needed to be moved.")
            done = True
        except Exception as exc:
            conn.rollback()
            st.error(f"Could not recover missed study ({type(exc).__name__}: {exc}).")
    if done:
        st.rerun()      # outside try/except so Streamlit's rerun signal is never swallowed

    if st.session_state.get("plan_msg"):
        st.success(st.session_state.pop("plan_msg"))
    if st.session_state.get("leftovers"):
        st.warning("Some work did not fit before the exam. Nothing was dropped - it is listed here:")
        st.dataframe(pd.DataFrame(st.session_state["leftovers"]), hide_index=True)

    plan = db.plan_df(conn)
    today = date.today().isoformat()
    missed = plan[(plan["status"] == "missed") & (plan["rescheduled"] == 0)] if not plan.empty else plan
    if not missed.empty:
        st.error(f"{len(missed)} missed item(s) are waiting to be rescheduled. Press 'Recover missed study'.")
        st.dataframe(missed[["plan_date", "subject_name", "topic_name", "planned_minutes"]], hide_index=True)
    overdue = plan[(plan["status"] == "planned") & (plan["plan_date"] < today)] if not plan.empty else plan
    if not overdue.empty:
        st.warning(f"{len(overdue)} planned item(s) are from earlier days and were not completed. "
                   "'Recover missed study' will move them forward.")

    upcoming = plan[(plan["plan_date"] >= today) & (plan["status"].isin(["planned", "completed"]))] if not plan.empty else plan
    if upcoming.empty:
        st.info("No timetable yet. Press 'Generate / refresh timetable' to build one from your subjects, topics and quiz scores.")
        return

    show_all = st.checkbox("Show every day (default: next 7 days with plans)", value=False)
    days = sorted(upcoming["plan_date"].unique())
    for day in (days if show_all else days[:7]):
        rows = upcoming[upcoming["plan_date"] == day].to_dict("records")
        study = sum(r["planned_minutes"] for r in rows)
        total = study + brk * max(0, len(rows) - 1)
        with st.expander(f"{day} - {study} min study, {total} of {limit} min used incl. breaks", expanded=(day == days[0])):
            table = []
            for item in scheduler.with_breaks(rows, brk):
                if item["kind"] == "break":
                    table.append({"Type": "Break", "Subject": "", "Topic": "", "Minutes": item["minutes"], "Why": "Short rest between blocks", "Status": ""})
                else:
                    table.append({"Type": "Study", "Subject": item["subject_name"], "Topic": item["topic_name"],
                                  "Minutes": item["planned_minutes"], "Why": item["reason"], "Status": item["status"]})
            st.dataframe(pd.DataFrame(table), hide_index=True)

    st.subheader("Update a plan item")
    labels = {int(r["plan_id"]): f"{r['plan_date']} - {r['topic_name']} ({r['planned_minutes']} min, {r['status']})"
              for r in upcoming.to_dict("records")}
    pid = st.selectbox("Plan item", list(labels), format_func=lambda i: labels[i])
    status = st.radio("Set status", ["planned", "completed", "missed"], horizontal=True)
    if st.button("Update status"):
        run_action(db.set_plan_status, "Plan item updated.", conn, pid, status)
