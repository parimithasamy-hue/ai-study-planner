"""Small helpers shared by all pages."""
from __future__ import annotations

import streamlit as st

from planner.validators import ValidationError


def flash(message: str, kind: str = "success") -> None:
    """Show a message on the next run (used after st.rerun())."""
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop("_flash", None)
    if item:
        kind, msg = item
        {"success": st.success, "error": st.error, "warning": st.warning, "info": st.info}.get(kind, st.info)(msg)


def run_action(action, success_message: str, *args, **kwargs) -> bool:
    """Run a database action; show a friendly message instead of a traceback."""
    try:
        action(*args, **kwargs)
    except ValidationError as exc:
        st.error(str(exc))
        return False
    except Exception as exc:  # unexpected - keep the app alive and tell the user what happened
        st.error(f"Something went wrong while saving ({type(exc).__name__}: {exc}). Your data was not changed.")
        return False
    flash(success_message)
    st.rerun()
    return True


def topic_options(conn) -> dict[int, str]:
    rows = conn.execute("""SELECT t.topic_id, s.subject_name, t.topic_name FROM topics t
                           JOIN subjects s ON s.subject_id = t.subject_id ORDER BY s.subject_name, t.topic_id""").fetchall()
    return {r["topic_id"]: f"{r['subject_name']} - {r['topic_name']}" for r in rows}


def subject_options(conn) -> dict[int, str]:
    return {r["subject_id"]: r["subject_name"] for r in conn.execute("SELECT subject_id, subject_name FROM subjects ORDER BY subject_name")}


def empty_state(message: str) -> None:
    st.info(message)
