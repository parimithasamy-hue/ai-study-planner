-- 1. Topic counts per subject
SELECT s.subject_name, COUNT(t.topic_id) AS topic_count
FROM subjects s LEFT JOIN topics t ON t.subject_id=s.subject_id
GROUP BY s.subject_id;

-- 2. Weak topics based on latest recorded quiz result (below 50%)
WITH ranked AS (
  SELECT q.*, ROW_NUMBER() OVER(PARTITION BY topic_id ORDER BY quiz_date DESC, quiz_id DESC) AS rn
  FROM quiz_results q
)
SELECT s.subject_name, t.topic_name,
       ROUND(100.0*r.score/r.total_questions, 1) AS score_percent
FROM ranked r
JOIN topics t ON t.topic_id=r.topic_id
JOIN subjects s ON s.subject_id=t.subject_id
WHERE r.rn=1 AND 1.0*r.score/r.total_questions < 0.5
ORDER BY score_percent;

-- 3. Study minutes by subject
SELECT s.subject_name, SUM(ss.duration_minutes) AS total_minutes
FROM study_sessions ss JOIN topics t ON t.topic_id=ss.topic_id
JOIN subjects s ON s.subject_id=t.subject_id
GROUP BY s.subject_id ORDER BY total_minutes DESC;

-- 4. Pending topics, hardest first
SELECT s.subject_name,t.topic_name,t.difficulty,t.estimated_hours
FROM topics t JOIN subjects s ON s.subject_id=t.subject_id
WHERE t.status <> 'completed' ORDER BY t.difficulty DESC;

-- 5. Question bank count per subject
SELECT s.subject_name, COUNT(q.question_id) AS question_count
FROM subjects s JOIN topics t ON t.subject_id=s.subject_id
JOIN quiz_questions q ON q.topic_id=t.topic_id
GROUP BY s.subject_id;
