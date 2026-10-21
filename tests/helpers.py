import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from planner import config, db  # noqa: E402


def fresh_db(testcase):
    """Copy the SUPPLIED original database into a temp dir and migrate it. Returns an open connection."""
    tmp = tempfile.mkdtemp()
    testcase.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
    path = Path(tmp) / "t.db"
    shutil.copyfile(config.ORIGINAL_DB_PATH, path)
    old = config.BACKUP_DIR
    config.BACKUP_DIR = Path(tmp) / "backups"
    testcase.addCleanup(setattr, config, "BACKUP_DIR", old)
    conn = db.get_connection(path)
    testcase.addCleanup(conn.close)
    return conn
