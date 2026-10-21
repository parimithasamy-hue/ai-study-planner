# AI Study Planner — Complete Starter Database

This is a laptop-friendly SQLite starter database with CSV exports for a study-planning project.

## Included
- `study_planner.db`: ready-to-connect SQLite database
- CSV exports for every table
- `sample_queries.sql`: useful SQL analytics queries
- 4 sample subjects and 42 topics
- A quiz bank with multiple-choice questions and explanations
- Fictional demo study sessions, quiz results, revisions, and starter plan rows

## Important
All study history, quiz scores, and starter plan records are fictional sample data. The questions are starter practice questions for a demo, not an official syllabus or validated exam bank. Replace or edit them to match the target syllabus and review answers before publishing.

## Python connection
```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("study_planner.db")
df = pd.read_sql_query(
    """SELECT s.subject_name, t.topic_name, t.status, t.difficulty
       FROM topics t JOIN subjects s ON s.subject_id=t.subject_id""",
    conn
)
print(df.head())
conn.close()
```

## Rule-based examples
- Latest quiz score below 50%: recommend practice for that topic.
- Difficulty 4–5: allocate a larger study block.
- Topic not revised recently: add a revision reminder.
- Missed plan item: redistribute it across remaining available days.
- Exam approaching: prioritize incomplete and weak topics.

These rules are app logic; the database stores the inputs and history. This starter data does not itself implement the Streamlit application or a live AI API.
