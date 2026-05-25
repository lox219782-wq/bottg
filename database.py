import os
import aiosqlite
from config import DB_PATH


async def init_db() -> None:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                session_name TEXT NOT NULL,
                api_id INTEGER NOT NULL,
                api_hash TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                sent_count INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                api_id INTEGER NOT NULL,
                api_hash TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mailing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                recipient TEXT NOT NULL,
                status TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def save_api_settings(api_id: int, api_hash: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO api_settings (id, api_id, api_hash)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET api_id=excluded.api_id,
                                           api_hash=excluded.api_hash,
                                           updated_at=CURRENT_TIMESTAMP
        """, (api_id, api_hash))
        await db.commit()


async def get_api_settings() -> tuple[int, str]:
    _default_api_id = 2040
    _default_api_hash = "b18441a1ff607e10a989891a5462e627"
    try:
        from config import DEFAULT_API_ID, DEFAULT_API_HASH
        _default_api_id = DEFAULT_API_ID
        _default_api_hash = DEFAULT_API_HASH
    except ImportError:
        pass
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT api_id, api_hash FROM api_settings WHERE id=1") as cursor:
            row = await cursor.fetchone()
            if row:
                return (row[0], row[1])
    return (_default_api_id, _default_api_hash)


async def add_account(phone: str, session_name: str, api_id: int, api_hash: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO accounts (phone, session_name, api_id, api_hash, active, sent_count)
            VALUES (?, ?, ?, ?, 1, 0)
        """, (phone, session_name, api_id, api_hash))
        await db.commit()


async def get_all_accounts() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE active=1") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def increment_sent(phone: str, count: int = 1) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE accounts SET sent_count = sent_count + ? WHERE phone=?",
            (count, phone)
        )
        await db.commit()


async def log_mailing(phone: str, recipient: str, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO mailing_log (phone, recipient, status) VALUES (?, ?, ?)",
            (phone, recipient, status)
        )
        await db.commit()


async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*), SUM(sent_count) FROM accounts WHERE active=1") as c:
            row = await c.fetchone()
            active = row[0] or 0
            total_sent = row[1] or 0
        async with db.execute("SELECT COUNT(*) FROM accounts WHERE active=0") as c:
            row = await c.fetchone()
            inactive = row[0] or 0
        async with db.execute(
            "SELECT COUNT(*) FROM mailing_log WHERE status='ok' AND date(sent_at)=date('now')"
        ) as c:
            row = await c.fetchone()
            sent_today = row[0] or 0
    return {
        "active": active,
        "inactive": inactive,
        "total_sent": total_sent,
        "sent_today": sent_today,
    }


async def deactivate_account(phone: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET active=0 WHERE phone=?", (phone,))
        await db.commit()
