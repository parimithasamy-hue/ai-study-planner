import streamlit as st

from planner import notes
from planner.validators import ValidationError


def render(conn):
    st.header("Notes assistant")
    st.caption("Paste notes or upload a .txt / .md file. The summary below works fully offline - no account, key or internet needed.")
    uploaded = st.file_uploader("Upload a text file (optional)", type=["txt", "md"])
    text = st.text_area("Or paste your notes", height=220)
    if uploaded is not None:
        try:
            text = notes.read_uploaded_text(uploaded.getvalue(), uploaded.name)
            st.success(f"Loaded {uploaded.name} ({len(text):,} characters). Pasted text is ignored while a file is uploaded.")
        except ValidationError as exc:
            st.error(str(exc))
            return
    n = st.slider("Sentences in the summary", 1, 10, 5)
    if st.button("Summarise (offline)"):
        try:
            st.session_state["notes_result"] = notes.summarize_offline(text, n)
        except ValidationError as exc:
            st.error(str(exc))
    result = st.session_state.get("notes_result")
    if result:
        st.subheader("Summary")
        for s in result["summary"]:
            st.markdown(f"- {s}")
        st.markdown("**Key terms:** " + ", ".join(result["keywords"]))
        if result["practice_questions"]:
            st.markdown("**Self-test questions found in your notes:**")
            for q in result["practice_questions"]:
                st.markdown(f"- {q}")
        st.caption("Offline mode picks the most important sentences by word frequency. It does not rewrite or fact-check your notes.")

    with st.expander("Optional: AI summary (needs your own API key - NOT required)"):
        st.warning("This sends your notes to an external AI service (Anthropic API) and may cost money. It stays off unless you "
                   "install the `anthropic` package, set the ANTHROPIC_API_KEY environment variable, tick the box and press the button.")
        ok, msg = notes.ai_available()
        st.caption(msg)
        agree = st.checkbox("I understand my notes will be sent to the AI service", disabled=not ok)
        if st.button("Summarise with AI", disabled=not (ok and agree)):
            try:
                with st.spinner("Asking the AI service..."):
                    st.markdown(notes.summarize_with_ai(text))
            except ValidationError as exc:
                st.error(str(exc))
