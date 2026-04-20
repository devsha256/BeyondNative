import sqlite3
from logger import log

def get_db():
    conn = sqlite3.connect('settings.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS log_report_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            data TEXT
        )''')
        conn.commit()

def get_setting(key, default=""):
    try:
        with get_db() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if row:
                return row["value"]
    except Exception as e:
        log.error(f"DB Error fetching {key}: {e}")
    return default

def set_setting(key, value):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
