from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from config import ADMIN_IDS
import database as db

admin_router = Router()

# Функция для создания главного меню с кнопками
def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📱 Добавить аккаунт (Юзербот)")],
        [KeyboardButton(text="📊 Статистика системы")],
        [KeyboardButton(text="🔍 Проверить базу номеров")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# Проверка: является ли пользователь админом
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# Обработка команды /start
@admin_router.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Доступ заблокирован. Вы не являетесь администратором этой системы.")
        return
    
    await message.answer(
        "👋 Добро пожаловать в панель управления Комбайном!\n"
        "Здесь вы можете управлять вашими юзерботами и проверять номера.",
        reply_markup=get_main_keyboard()
    )

# Обработка кнопки "Статистика"
@admin_router.message(F.text == "📊 Статистика системы")
async def show_stats(message: Message):
    if not is_admin(message.from_user.id): return
    
    # Считаем данные из БД
    userbots_count = len(db.get_all_userbots())
    
    conn = db.sqlite3.connect(db.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(case when has_telegram=1 then 1 else 0 end), SUM(case when has_telegram=2 then 1 else 0 end) FROM phone_checker")
    total_phones, with_tg, no_tg = cursor.fetchone()
    conn.close()
    
    total_phones = total_phones or 0
    with_tg = with_tg or 0
    no_tg = no_tg or 0
    unverified = total_phones - with_tg - no_tg
    
    await message.answer(
        f"📊 **Текущая статистика системы:**\n\n"
        f"🤖 Активных аккаунтов (юзерботов): {userbots_count}\n"
        f"📞 Всего номеров в базе чекера: {total_phones}\n"
        f"   └ ✅ Есть Telegram: {with_tg}\n"
        f"   └ ❌ Нет Telegram: {no_tg}\n"
        f"   └ ⏳ Ожидают проверки: {unverified}"
    )

# Временные заглушки для других кнопок (их логику мы допишем в следующих файлах)
@admin_router.message(F.text == "📱 Добавить аккаунт (Юзербот)")
async def add_account_prompt(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer("⚙️ Модуль добавления аккаунтов подготавливается. Скоро мы настроим безопасный ввод сессии!")

@admin_router.message(F.text == "🔍 Проверить базу номеров")
async def check_phones_prompt(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer("⚙️ Функция массовой загрузки номеров (.txt файлом) будет активна после подключения модулей юзерботов.")
