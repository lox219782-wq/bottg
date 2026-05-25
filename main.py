import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import database as db
import userbot_manager as ub_mgr
from admin_router import admin_router
from config import BOT_TOKEN, ADMIN_IDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    await db.init_db()
    logger.info("База данных инициализирована")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "✅ Бот запущен и готов к работе!")
        except Exception:
            pass

    logger.info("Бот запущен. ADMIN_IDS: %s", ADMIN_IDS)


async def on_shutdown(bot: Bot) -> None:
    await ub_mgr.disconnect_all()
    logger.info("Все UserBot-клиенты отключены. Бот остановлен.")


async def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан! Установите переменную окружения BOT_TOKEN.")
        sys.exit(1)

    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS не задан — бот не будет отвечать ни одному пользователю!")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Запуск polling...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
