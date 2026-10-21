"""Project-wide paths and default settings."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "study_planner.db"            # the working database
ORIGINAL_DB_PATH = DATA_DIR / "original" / "study_planner.db"  # untouched copy of the supplied DB
BACKUP_DIR = DATA_DIR / "backups"

# Defaults stored in the `settings` table (user can change them in the app).
DEFAULT_SETTINGS = {
    "daily_limit_minutes": "120",   # hard cap on scheduled minutes per day (study + breaks)
    "weak_threshold_pct": "50",     # a topic is "weak" if its recent average is below this %
    "weak_recent_quizzes": "3",     # how many most-recent quizzes are averaged
    "break_minutes": "5",           # short break between study blocks (counts toward the limit)
    "max_block_minutes": "60",      # longest block for ordinary topics (hard topics get 90)
}

MIN_BLOCK_MINUTES = 15       # avoid tiny fragments unless that is all that is left
HARD_TOPIC_BLOCK_MINUTES = 90
MAX_PLAN_HORIZON_DAYS = 60
