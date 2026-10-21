import plotly.express as px
import streamlit as st

from planner import analytics, quiz
from views.common import empty_state


def render(conn):
    st.header("Analytics")
    prog = analytics.subject_progress_df(conn)
    if prog.empty or int(prog["total_topics"].sum()) == 0:
        empty_state("No topics yet - add subjects and topics to see analytics.")
        return

    st.subheader("Subject progress")
    long = prog.melt(id_vars="subject_name", value_vars=["completed_topics", "in_progress_topics", "pending_topics"],
                     var_name="Status", value_name="Topics")
    long["Status"] = long["Status"].str.replace("_topics", "").str.replace("_", " ")
    st.plotly_chart(px.bar(long, x="subject_name", y="Topics", color="Status", barmode="stack",
                           labels={"subject_name": "Subject"}))

    st.subheader("Daily study time")
    days = st.select_slider("Days to show", options=[7, 14, 30, 60], value=14)
    daily = analytics.study_minutes_by_day(conn, days)
    if int(daily["minutes"].sum()) == 0:
        empty_state("No study sessions in this period. Log a session on the Study sessions page.")
    else:
        fig = px.bar(daily, x="study_date", y=["planned_minutes", "minutes"], barmode="group",
                     labels={"value": "Minutes", "study_date": "Date", "variable": ""})
        fig.for_each_trace(lambda t: t.update(name={"planned_minutes": "Planned", "minutes": "Actual"}.get(t.name, t.name)))
        st.plotly_chart(fig)

    st.subheader("Quiz results")
    qr = quiz.quiz_results_df(conn)
    if qr.empty:
        empty_state("No quiz results yet - take a quiz first.")
    else:
        fig = px.scatter(qr, x="quiz_date", y="percent", color="subject_name", hover_name="topic_name",
                         range_y=[0, 100], labels={"percent": "Score (%)", "quiz_date": "Date", "subject_name": "Subject"})
        fig.update_traces(marker={"size": 11})
        st.plotly_chart(fig)
        avg = qr.groupby("subject_name", as_index=False)["percent"].mean().round(1)
        st.plotly_chart(px.bar(avg, x="subject_name", y="percent", range_y=[0, 100], text="percent",
                               labels={"percent": "Average score (%)", "subject_name": "Subject"}))
