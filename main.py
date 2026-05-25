import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from admin_panel import admin_router
import database as db

# Включаем логирование, чтобы видеть работу бота в консоли
logging.basicConfig(level=logging.INFO)

async def main():
    # Инициализируем базу данных при старте
    db.init_db()
    
    # Создаем объекты бота и диспетчера для админки
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Подключаем наши кнопки и логику админки
    dp.include_router(admin_router)
    
    print("[Система] Главный бот-администратор запускается...")
    
    # Запускаем бота в режиме постоянного опроса (Polling)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("[Система] Бот успешно остановлен.")
