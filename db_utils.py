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
        conn.execute('''CREATE TABLE IF NOT EXISTS comparison_sessions (
            session_id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            collection_name TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS comparison_session_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            request_name TEXT,
            method TEXT,
            status TEXT,
            match_percent REAL,
            stats_json TEXT,
            curl_details TEXT,
            resp_a_raw TEXT,
            resp_b_raw TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES comparison_sessions(session_id)
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

def start_comparison_session(session_id, collection_name):
    with get_db() as conn:
        conn.execute("INSERT INTO comparison_sessions (session_id, collection_name) VALUES (?, ?)", (session_id, collection_name))
        conn.commit()

def record_comparison_result(session_id, request_name, method, status, match_percent, stats, curl, resp_a, resp_b):
    import json
    with get_db() as conn:
        conn.execute('''INSERT INTO comparison_session_results 
            (session_id, request_name, method, status, match_percent, stats_json, curl_details, resp_a_raw, resp_b_raw) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (session_id, request_name, method, status, match_percent, json.dumps(stats), curl, json.dumps(resp_a), json.dumps(resp_b)))
        conn.commit()

def get_session_results(session_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM comparison_session_results WHERE session_id=? ORDER BY id ASC", (session_id,)).fetchall()
