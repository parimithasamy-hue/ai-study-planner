import streamlit as st

from planner import readiness
from views.common import subject_options


def render(conn):
    st.header("Exam readiness (estimate)")
    st.warning(readiness.DISCLAIMER)
    subjects = subject_options(conn)
    if not subjects:
        st.info("Add a subject and topics to see a readiness estimate.")
        return
    st.caption("Formula: 50% syllabus completion + 20% revision (confidence, reduced if overdue) + 30% latest quiz scores. "
               "Components with no data are left out and the remaining weights are rescaled.")
    for sid, name in subjects.items():
        r = readiness.exam_readiness(conn, sid)
        with st.expander(name, expanded=True):
            if r["estimate"] is None:
                st.info(r["notes"][0])
                continue
            c1, c2 = st.columns([1, 2])
            c1.metric("Estimated readiness", f"{r['estimate']:.0f} / 100", help=r["band"])
            c1.caption(f"{r['band']} - data confidence: {r['data_confidence']}")
            comp = r["components"]
            c2.progress(min(1.0, r["estimate"] / 100))
            c2.write(f"Syllabus completion: **{comp['completion']}%**  |  Revision: **{'n/a' if comp['revision'] is None else str(comp['revision']) + '%'}**"
                     f"  |  Quizzes: **{'n/a' if comp['quiz'] is None else str(comp['quiz']) + '%'}** (coverage {r['quiz_coverage_pct']}% of topics)")
            for note in r["notes"]:
                st.caption("Note: " + note)
