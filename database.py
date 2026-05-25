import sqlite3

DB_PATH = "bot_system.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Таблица аккаунтов-юзерботов (храним строку сессии Pyrogram)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS userbots (
            phone TEXT PRIMARY KEY,
            session_string TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
    """)
    
    # 2. Таблица номеров для чекера
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS phone_checker (
            phone TEXT PRIMARY KEY,
            has_telegram INTEGER DEFAULT 0, -- 0 - не проверен, 1 - есть ТГ, 2 - нет ТГ
            telegram_id INTEGER DEFAULT NULL,
            username TEXT DEFAULT NULL
        )
    """)
    
    conn.commit()
    conn.close()
    print("[БД] База данных успешно инициализирована.")

# --- Функции для работы с юзерботами ---
def add_userbot(phone: str, session_string: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO userbots (phone, session_string, status) VALUES (?, ?, 'active')",
        (phone, session_string)
    )
    conn.commit()
    conn.close()

def get_all_userbots():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT phone, session_string FROM userbots WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- Функции для работы с чекером номеров ---
def upload_phones(phone_list: list):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for phone in phone_list:
        cursor.execute("INSERT OR IGNORE INTO phone_checker (phone, has_telegram) VALUES (?, 0)", (phone,))
    conn.commit()
    conn.close()

def get_unverified_phones(limit=100):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT phone FROM phone_checker WHERE has_telegram = 0 LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def update_phone_status(phone: str, status: int, tg_id=None, username=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE phone_checker SET has_telegram = ?, telegram_id = ?, username = ? WHERE phone = ?",
        (status, tg_id, username, phone)
    )
    conn.commit()
    conn.close()
