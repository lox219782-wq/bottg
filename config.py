import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_IDS: list[int] = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

DB_PATH: str = os.getenv("DB_PATH", "bot.db")
SESSIONS_DIR: str = os.getenv("SESSIONS_DIR", "sessions")
UPLOADS_DIR: str = os.getenv("UPLOADS_DIR", "uploads") 
