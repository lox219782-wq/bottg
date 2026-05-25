import sqlite3

DB_PATH = "bot_system.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Таблица аккаунтов-юзерботов
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
            has_telegram INTEGER DEFAULT 0,
            telegram_id INTEGER DEFAULT NULL,
            username TEXT DEFAULT NULL
        )
    """)

    # 3. Новая таблица для настроек API (ID и HASH)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    # Записываем стандартные ключи, если таблица пустая
    cursor.execute("INSERT OR IGNORE INTO api_settings (key, value) VALUES ('api_id', '2040')")
    cursor.execute("INSERT OR IGNORE INTO api_settings (key, value) VALUES ('api_hash', 'b18441a1ff607e10a989891a5462e627')")
    
    conn.commit()
    conn.close()
    print("[БД] База данных успешно инициализирована.")

# --- Функции для динамического изменения API ---
def get_api_credentials():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM api_settings")
    data = dict(cursor.fetchall())
    conn.close()
    # Возвращаем кортеж (api_id, api_hash)
    return data.get('api_id', '2040'), data.get('api_hash', 'b18441a1ff607e10a989891a5462e627')

def update_api_credentials(api_id: str, api_hash: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO api_settings (key, value) VALUES ('api_id', ?)", (api_id,))
    cursor.execute("INSERT OR REPLACE INTO api_settings (key, value) VALUES ('api_hash', ?)", (api_hash,))
    conn.commit()
    conn.close()

# --- Остальные функции (оставляем без изменений) ---
def add_userbot(phone: str, session_string: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO userbots (phone, session_string, status) VALUES (?, ?, 'active')", (phone, session_string))
    conn.commit()
    conn.close()

def get_all_userbots():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT phone, session_string FROM userbots WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    return rows

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
    cursor.execute("UPDATE phone_checker SET has_telegram = ?, telegram_id = ?, username = ? WHERE phone = ?", (status, tg_id, username, phone))
    conn.commit()
    conn.close()
