# AI Study Planner

A beginner-friendly **Streamlit + SQLite + Pandas + Plotly** study planner. It is **rule-based and fully offline**:
no GPU, no local LLM, no API key needed for any core feature.

It is built on the database you supplied (`study_planner.db`, 4 subjects, 43 topics, 215 quiz questions, sample
sessions/quizzes/revisions/plan rows). The app opens **that same database** - nothing is duplicated or re-created.

## Quick start (Windows + VS Code)

1. Right-click `ai_study_planner_app.zip` -> **Extract All...** and pick a folder (e.g. `Documents`).
2. Open **VS Code** -> **File > Open Folder...** -> choose the extracted `study_planner_app` folder.
3. Open a terminal: **Terminal > New Terminal**.
4. (Recommended) create a virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   ```
5. Install and run:
   ```
   pip install -r requirements.txt
   streamlit run app.py
   ```
   The browser opens at http://localhost:8501. (Shortcut: double-click `run_app.bat`, which does steps 4-5 for you.)

macOS/Linux: use `source .venv/bin/activate` instead of step 4's second line.

## Pages

| Page | What it does |
|---|---|
| Dashboard | Subject progress, completed/pending topics, study hours, quiz average, upcoming exams, today's plan, weak topics, revision due |
| Subjects | Add/edit subjects: exam date, priority (1-5), daily study time |
| Topics | Add/edit topics: difficulty, estimated hours, status, last studied date |
| Timetable | Generate a rule-based plan, recover missed study, see leftovers that did not fit, reasons for each task |
| Quiz | Pick a topic, answer MCQs, see score and explanations; saved to SQLite |
| Weak topics & revision | Configurable weak-topic rule; revision reminders from last revision date + confidence; log revisions |
| Study sessions | Planned vs actual minutes, completion, notes |
| Analytics | Subject progress, daily study time, quiz result charts |
| Exam readiness | **Estimate only** from completion, revision and quizzes |
| Notes assistant | Offline extractive summary + key terms; optional, clearly-marked AI button |
| Export CSV | Progress, subject summary, quiz results, study plan, study sessions |
| Settings | Daily limit, weak threshold, breaks |

## How the rules work

**Timetable** (`planner/scheduler.py`). Each unfinished topic gets a score:
exam proximity (0-40, closer = higher) + 4 x subject priority + 3 x difficulty + 20 if weak + 5 if already in progress.
Days are filled highest score first. Rules enforced:

* Per day, **study minutes + breaks <= daily limit**, and minutes per subject <= that subject's own daily cap.
* One block per topic per day (no duplicates); nothing is scheduled on or after the exam day.
* Blocks are 60 min (90 min for difficulty 4-5); tiny fragments (<15 min) are avoided.
* A short break (default 5 min) sits between blocks and **counts toward the limit**. Breaks are shown in the timetable but not stored in the database.
* Work that does not fit is shown under **"Some work did not fit"** - never silently dropped.
* Every block stores a "Recommended because: ..." explanation.

**Missed-study recovery.** Planned items dated before today become `missed`; their minutes are re-planned from today
around what is already scheduled, under the same limits. Anything that still cannot fit stays visible. Missed topics that are
already `completed` need no recovery.

**Weak topics.** Weak = average of the last *N* quiz results is strictly below *T* %. Defaults: N = 3, T = 50 (both editable).
With N = 1, T = 50 it matches query #2 in the supplied `sample_queries.sql`.

**Revision reminders.** Next revision = last revision date (or last studied date if never revised) + interval by confidence:
1 -> 1 day, 2 -> 3, 3 -> 7, 4 -> 14, 5 -> 21.

**Exam readiness.** 50 % syllabus completion (by estimated hours, in-progress counts half) + 20 % revision + 30 % latest quiz scores.
Missing components are left out and weights rescaled. It is an **estimate, not a prediction or a guarantee**.

## Database

* Working database: `data/study_planner.db` (project-relative). Untouched supplied copy: `data/original/`.
  If the working file is deleted, it is re-created from `data/original/study_planner.db` on next start.
* On first open, a **safe migration (schema v1)** runs: it only *adds* things and never deletes or rewrites your rows. A backup copy is saved in `data/backups/` first.
  Added: `subjects.daily_minutes`, `study_sessions.planned_minutes`, `study_plan.rescheduled`, `quiz_questions.needs_review`,
  tables `settings` and `quiz_answers`, and a unique index on `study_plan(plan_date, topic_id)`.
* All SQL is parameterised.

### Things to know about the supplied sample data

* **Many quiz questions are generic and repeated across topics.** 115 of the 215 questions have exactly the same text under more than one topic
  (for example SQL questions under *Indexing* and *Relational Algebra*; networking questions under *Subnetting*, *Switching*, etc.; maths questions
  under *Calculus*, *Graph Theory*, ...). I did **not** change them (you asked to preserve them); they are flagged with `needs_review = 1`,
  and the quiz page warns when one appears. Replace them with real syllabus questions before relying on quiz scores.
* **The answer key is skewed:** 107 questions have answer A, 84 B, 24 C and none D. The quiz therefore shuffles answer positions by default
  (scoring still uses the original answer letter).
* One option is the literal text `None` (question 83). Pandas turns that into a missing value if you re-import the CSV without `keep_default_na=False`.
* Study history, quiz scores and plan rows are fictional demo data (dated October 2026).

## Optional AI summary (not required)

The Notes assistant works offline. If you *want* an AI summary: `pip install anthropic`, set the `ANTHROPIC_API_KEY` environment variable
(never put keys in the code), tick the consent box and press the AI button. Your notes are then sent to the Anthropic API and may cost money.
This path was **not exercised in testing** (it needs a key and internet).

## Tests

```
python -m unittest discover -s tests -t . -v
```
(or double-click `run_tests.bat`). They cover migrations and preservation of the supplied data, the supplied sample queries, validation,
quiz scoring/saving, weak-topic rules, scheduling limits (random stress tests), recovery, revision, readiness, notes and CSV export.

## Project layout

```
app.py                 Streamlit entry point (sidebar navigation)
planner/               Logic: db, scheduler, quiz, readiness, analytics, notes, exports, validators, config
views/                 One module per page
data/                  study_planner.db (working) + original/ (supplied DB, CSVs, sample_queries.sql)
tests/                 unittest suite
```

## Known limitations

* No delete buttons for subjects/topics (to protect data); use any SQLite tool if you need that.
* The planner is a heuristic, not an optimiser; it plans at most 60 days ahead.
* Timetable starts from today's date on your computer.
