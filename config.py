import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]

# Добавь эти строки:
SESSIONS_DIR = "sessions"
UPLOADS_DIR = "uploads"

# Создаем папки, если их нет
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

if not BOT_TOKEN:
    raise ValueError("Критическая ошибка: Токен бота (BOT_TOKEN) не найден!")
if not ADMIN_IDS:
    raise ValueError("Критическая ошибка: Список ADMIN_IDS пуст!")
