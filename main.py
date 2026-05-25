import os
from dotenv import load_dotenv

load_dotenv()

api_id = os.getenv("TELEGRAM_API_ID")
api_hash = os.getenv("TELEGRAM_API_HASH")

print("--- ТЕСТ СЕКРЕТОВ GitHub ---")
print(f"Считанный TELEGRAM_API_ID: {api_id}")
print(f"Считанный TELEGRAM_API_HASH: {api_hash}")

try:
    # Проверяем, превращается ли ID в нормальное число
    api_id_int = int(api_id)
    print(f"[УСПЕШНО] API_ID успешно преобразован в число: {api_id_int}")
except Exception as e:
    print(f"[ОШИБКА] Не удалось перевести API_ID в число. В секретах записано: '{api_id}'. Ошибка: {e}")
