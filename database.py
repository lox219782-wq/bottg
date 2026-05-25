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

def update_task(phone, text, interval):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO tasks (phone, text, interval, status) VALUES (?, ?, ?, 'ready')", (phone, text, interval))
    conn.commit()
    conn.close()

# Добавь сюда остальные функции из старого файла (get_all_userbots, add_userbot, etc.)
