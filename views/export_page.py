from datetime import date

import streamlit as st

from planner import exports

LABELS = {"progress": "Topic progress", "subject_summary": "Subject summary", "quiz_results": "Quiz results",
          "study_plan": "Study plan", "study_sessions": "Study sessions"}


def render(conn):
    st.header("Export CSV")
    st.caption("Downloads are plain CSV files that open in Excel, Google Sheets or Python.")
    for key, df in exports.exports(conn).items():
        with st.expander(f"{LABELS[key]} ({len(df)} rows)"):
            if df.empty:
                st.info("Nothing to export yet.")
                continue
            st.dataframe(df.head(10), hide_index=True)
            st.download_button(f"Download {LABELS[key]} CSV", exports.to_csv_bytes(df),
                               file_name=f"{key}_{date.today().isoformat()}.csv", mime="text/csv", key=f"dl_{key}")
