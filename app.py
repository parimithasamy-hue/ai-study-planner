"""AI Study Planner - run with:  streamlit run app.py"""
import streamlit as st

from planner import db
from views import (analytics_page, dashboard, export_page, notes_page, quiz_page, readiness_page, revision,
                   sessions, settings, subjects, timetable, topics)
from views.common import show_flash

st.set_page_config(page_title="AI Study Planner", page_icon="📚", layout="wide")

PAGES = {
    "Dashboard": dashboard,
    "Subjects": subjects,
    "Topics": topics,
    "Timetable": timetable,
    "Quiz": quiz_page,
    "Weak topics & revision": revision,
    "Study sessions": sessions,
    "Analytics": analytics_page,
    "Exam readiness": readiness_page,
    "Notes assistant": notes_page,
    "Export CSV": export_page,
    "Settings": settings,
}

st.sidebar.title("AI Study Planner")
page = st.sidebar.radio("Go to", list(PAGES), label_visibility="collapsed")
st.sidebar.caption("Rule-based and fully offline. Demo data in the supplied database is fictional.")

try:
    conn = db.get_connection()
except Exception as exc:
    st.error(f"Could not open the database ({type(exc).__name__}: {exc}). "
             "Make sure data/study_planner.db exists, or delete it so it is re-created from data/original/.")
    st.stop()

try:
    show_flash()
    PAGES[page].render(conn)
except Exception as exc:  # last-resort guard so a bug never shows a raw traceback to a student
    if type(exc).__name__ in ("RerunException", "StopException"):   # Streamlit control-flow exceptions
        raise
    st.error(f"Something unexpected happened on this page ({type(exc).__name__}: {exc}). "
             "Your saved data is safe. Try another page or restart the app.")
finally:
    conn.close()
