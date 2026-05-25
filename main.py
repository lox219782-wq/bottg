import os
import asyncio
import sqlite3
from pyrogram import Client
from dotenv import load_dotenv

# Загружаем ключи из файла .env
load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

# Проверка, что ключи заполнены
if not API_ID or not API_HASH:
    raise ValueError("Ошибка: Проверьте, что файлы .env заполнен корректно!")

API_ID = int(API_ID)

# Настройки планировщика
MESSAGE_TEMPLATE = "Привет! Это автоматическое сообщение по расписанию."
SEND_INTERVAL = 600  # Интервал в секундах (600 секунд = 10 минут)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect("contacts_base.db")
    cursor = conn.cursor()
    # Создаем таблицу, если её нет. Храним только ID пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipients (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("[БД] База данных проверена и готова к работе.")

# Получение списка ID из базы данных
def get_recipients():
    conn = sqlite3.connect("contacts_base.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM recipients")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

# Очередь отправки по расписанию
async def scheduled_sender(app: Client):
    while True:
        user_ids = get_recipients()
        
        if not user_ids:
            print("[Планировщик] База пуста. Добавьте ID пользователей в contacts_base.db.")
        else:
            print(f"[Планировщик] Запуск цикла отправки для {len(user_ids)} контактов...")
            for u_id in user_ids:
                try:
                    # Отправка от лица твоего аккаунта
                    await app.send_message(chat_id=u_id, text=MESSAGE_TEMPLATE)
                    print(f"[Успешно] Сообщение отправлено пользователю: {u_id}")
                    
                    # Задержка 3 секунды между пользователями, чтобы не спамить в одну секунду
                    await asyncio.sleep(3) 
                except Exception as e:
                    print(f"[Ошибка] Не удалось отправить пользователю {u_id}: {e}")
                    
        print(f"[Ожидание] Следующий цикл отправки через {SEND_INTERVAL // 60} минут(ы)...")
        await asyncio.sleep(SEND_INTERVAL)

async def main():
    # Создаем/проверяем БД перед запуском сессии
    init_db()
    
    # Инициализируем клиента Pyrogram (создаст файл сессии my_telegram_account.session)
    app = Client("my_telegram_account", api_id=API_ID, api_hash=API_HASH)
    
    print("[Система] Запуск аккаунта...")
    async with app:
        print("[Система] Аккаунт успешно подключен!")
        # Запускаем бесконечный фоновый цикл планировщика
        await scheduled_sender(app)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Система] Бот остановлен пользователем.")
