import os
from dotenv import load_dotenv

load_dotenv()

# Читаем секреты
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

# Превращаем строку с ID админов (например, "123,456") в список чисел
raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]

# Проверка, что критические данные на месте
if not BOT_TOKEN:
    raise ValueError("Критическая ошибка: Токен бота (BOT_TOKEN) не найден в секретах!")
if not ADMIN_IDS:
    raise ValueError("Критическая ошибка: Список ADMIN_IDS пуст или заполнен неверно!")
