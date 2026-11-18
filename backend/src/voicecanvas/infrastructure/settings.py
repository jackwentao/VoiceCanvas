import os
from pathlib import Path

from dotenv import load_dotenv


def shot_db_path() -> Path:
    load_dotenv()
    default_path = Path(__file__).resolve().parents[3] / "data" / "svg-shots.sqlite3"
    return Path(os.getenv("VOICECANVAS_SHOT_DB_PATH", str(default_path)))
