import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root
load_dotenv()

DB_PATH = os.getenv("DB_PATH")
if not DB_PATH:
    raise RuntimeError("DB_PATH not set. Add DB_PATH to your .env file.")

DB_PATH = Path(DB_PATH).expanduser()

def get_conn():
    return sqlite3.connect(str(DB_PATH))
