from datetime import date

import plotly.express as px
import streamlit as st

from planner import analytics, db, quiz, readiness
from views.common import empty_state


def render(conn):
    st.header("Dashboard")
    counts = analytics.topic_status_counts(conn)
    if counts["total"] == 0:
        empty_state("No topics yet. Add a subject and some topics to see your dashboard.")
        return
    avg = analytics.average_quiz_pct(conn)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Completed topics", f"{counts['completed']} / {counts['total']}")
    c2.metric("Pending topics", counts["pending"] + counts["in_progress"], help="Pending plus in-progress")
    c3.metric("Study hours logged", analytics.total_study_hours(conn))
    c4.metric("Average quiz score", "No quizzes yet" if avg is None else f"{avg}%")

    left, right = st.columns(2)
    with left:
        st.subheader("Subject progress")
        prog = analytics.subject_progress_df(conn)
        fig = px.bar(prog, x="subject_name", y="completion_pct", range_y=[0, 100], text="completion_pct",
                     labels={"subject_name": "Subject", "completion_pct": "Topics completed (%)"})
        st.plotly_chart(fig)
    with right:
        st.subheader("Upcoming exams")
        exams = analytics.upcoming_exams_df(conn)
        if exams.empty:
            empty_state("No upcoming exams. Add an exam date on the Subjects page.")
        else:
            st.dataframe(exams.rename(columns={"subject_name": "Subject", "exam_date": "Exam date",
                                               "priority": "Priority", "days_left": "Days left"}), hide_index=True)

    st.subheader("Today's plan")
    plan = db.plan_df(conn)
    today = plan[plan["plan_date"] == date.today().isoformat()] if not plan.empty else plan
    if today.empty:
        empty_state("Nothing planned for today. Open the Timetable page to generate a plan.")
    else:
        st.dataframe(today[["subject_name", "topic_name", "planned_minutes", "status", "reason"]], hide_index=True)

    st.subheader("Needs attention")
    a, b = st.columns(2)
    with a:
        st.markdown("**Weak topics** (recent quiz average below your threshold)")
        weak = quiz.weak_topics(conn, db.get_setting(conn, "weak_threshold_pct"), db.get_setting(conn, "weak_recent_quizzes"))
        if weak.empty:
            st.caption("None right now.")
        else:
            st.dataframe(weak[["subject_name", "topic_name", "recent_avg_pct"]], hide_index=True)
    with b:
        st.markdown("**Revision due**")
        rem = readiness.revision_reminders(conn)
        due = rem[rem["reminder"].isin(["Overdue", "Due today"])] if not rem.empty else rem
        if due.empty:
            st.caption("Nothing due today.")
        else:
            st.dataframe(due[["subject_name", "topic_name", "reminder", "days_overdue"]], hide_index=True)
