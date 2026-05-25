import sqlite3

DB_PATH = "bot_system.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS userbots (phone TEXT PRIMARY KEY, session_string TEXT NOT NULL)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS tasks (
        phone TEXT PRIMARY KEY, 
        text TEXT, 
        interval INTEGER, 
        status TEXT DEFAULT 'idle'
    )""")
    cursor.execute("CREATE TABLE IF NOT EXISTS api_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    cursor.execute("INSERT OR IGNORE INTO api_settings VALUES ('api_id', '2040'), ('api_hash', 'b18441a1ff607e10a989891a5462e627')")
    conn.commit()
    conn.close()

def get_api_credentials():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM api_settings")
    data = dict(cursor.fetchall())
    conn.close()
    return data.get('api_id', '2040'), data.get('api_hash', 'b18441a1ff607e10a989891a5462e627')

def add_userbot(phone, session_string):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO userbots (phone, session_string) VALUES (?, ?)", (phone, session_string))
    conn.commit()
    conn.close()

def get_all_userbots():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT phone, session_string FROM userbots")
    rows = cursor.fetchall()
    conn.close()
    return rows
