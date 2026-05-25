import os
import asyncio
import sqlite3
from pyrogram import Client
from dotenv import load_dotenv

# 1. ЗАГРУЗКА НАСТРОЕК
load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

if not API_ID or not API_HASH:
    raise ValueError("Ошибка: Проверьте, что секреты TELEGRAM_API_ID и TELEGRAM_API_HASH добавлены в Settings -> Secrets!")

# ==================== НАСТРОЙКИ БОТА ====================
# Текст сообщения, который будет уходить людям
MESSAGE_TEMPLATE = "Привет! Это автоматическое сообщение от моего личного аккаунта."

# Интервал отправки в секундах (600 секунд = 10 минут)
SEND_INTERVAL = 600

# КОНТАКТ ДЛЯ ТЕСТА: Вставь сюда ID человека, которому бот напишет сразу при запуске
# (Узнать ID можно через бот @userinfobot)
TEST_USER_ID = 8707262803  
# ========================================================


# 2. РАБОТА С БАЗОЙ ДАННЫХ
def setup_database():
    conn = sqlite3.connect("contacts_base.db")
    cursor = conn.cursor()
    
    # Создаем таблицу, если её нет
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipients (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    """)
    
    # Сразу автоматически добавляем твой тестовый ID в базу, чтобы не делать это вручную
    cursor.execute("INSERT OR IGNORE INTO recipients (user_id, username) VALUES (?, ?)", (TEST_USER_ID, "TestContact"))
    
    conn.commit()
    conn.close()
    print("[БД] База данных успешно настроена. Тестовый ID добавлен.")


def get_recipients():
    conn = sqlite3.connect("contacts_base.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM recipients")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


# 3. АВТОМАТИЧЕСКАЯ РАССЫЛКА
async def scheduled_sender(app: Client):
    while True:
        user_ids = get_recipients()
        
        if not user_ids:
            print("[Планировщик] Список получателей пуст.")
        else:
            print(f"[Планировщик] Начинаю отправку для {len(user_ids)} контактов...")
            for u_id in user_ids:
                try:
                    # Отправка сообщения от твоего имени
                    await app.send_message(chat_id=u_id, text=MESSAGE_TEMPLATE)
                    print(f"[Успешно] Сообщение отправлено на ID: {u_id}")
                    await asyncio.sleep(3) # Задержка между сообщениями
                except Exception as e:
                    print(f"[Ошибка] Не удалось отправить на ID {u_id}: {e}")
                    
        print(f"[Ожидание] Следующий запуск через {SEND_INTERVAL // 60} минут...")
        await asyncio.sleep(SEND_INTERVAL)


# 4. ГЛАВНЫЙ ЗАПУСК
async def main():
    # Настраиваем БД и добавляем юзера
    setup_database()
    
    # Запускаем клиент
    app = Client("my_telegram_account", api_id=int(API_ID), api_hash=API_HASH)
    
    print("[Система] Подключение к аккаунту Telegram...")
    async with app:
        print("[Система] Авторизация успешна! Юзербот работает.")
        # Запускаем бесконечный цикл рассылки
        await scheduled_sender(app)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Система] Бот выключен.")
