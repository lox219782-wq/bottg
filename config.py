import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]

if not BOT_TOKEN:
    raise ValueError("Критическая ошибка: Токен бота (BOT_TOKEN) не найден!")
if not ADMIN_IDS:
    raise ValueError("Критическая ошибка: Список ADMIN_IDS пуст!")
