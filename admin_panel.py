import asyncio
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired

from config import ADMIN_IDS, API_ID, API_HASH
import database as db

admin_router = Router()

# Состояния для диалога добавления аккаунта
class AddAccountState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()

# Главное меню
def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📱 Добавить аккаунт (Юзербот)")],
        [KeyboardButton(text="📊 Статистика системы")],
        [KeyboardButton(text="🔍 Проверить базу номеров")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@admin_router.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer("👋 Добро пожаловать в панель управления Комбайном!", reply_markup=get_main_keyboard())

@admin_router.message(F.text == "📊 Статистика системы")
async def show_stats(message: Message):
    if not is_admin(message.from_user.id): return
    
    userbots_count = len(db.get_all_userbots())
    conn = db.sqlite3.connect(db.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(case when has_telegram=1 then 1 else 0 end), SUM(case when has_telegram=2 then 1 else 0 end) FROM phone_checker")
    total_phones, with_tg, no_tg = cursor.fetchone()
    conn.close()
    
    total_phones, with_tg, no_tg = total_phones or 0, with_tg or 0, no_tg or 0
    unverified = total_phones - with_tg - no_tg
    
    await message.answer(
        f"📊 **Статистика системы:**\n\n"
        f"🤖 Активных аккаунтов: {userbots_count}\n"
        f"📞 Номеров в базе: {total_phones} (✅ С ТГ: {with_tg}, ❌ Без: {no_tg}, ⏳ Ожидают: {unverified})"
    )

# --- ЛОГИКА ДОБАВЛЕНИЯ АККАУНТА ---

@admin_router.message(F.text == "📱 Добавить аккаунт (Юзербот)")
async def start_add_account(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    
    await message.answer("Введите номер телефона аккаунта в международном формате (например, `+79991234567`):")
    await state.set_state(AddAccountState.waiting_for_phone)

@admin_router.message(AddAccountState.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "")
    await message.answer("⏳ Связываюсь с Telegram, отправляю код...")
    
    # Создаем временный клиент Pyrogram для авторизации
    client = Client(f"temp_{phone}", api_id=int(API_ID), api_hash=API_HASH, in_memory=True)
    await client.connect()
    
    try:
        # Запрашиваем код у Телеграма
        code_hash = await client.send_code(phone)
        
        # Сохраняем данные в память сессии админки, чтобы использовать на следующем шаге
        await state.update_data(phone=phone, code_hash=code_hash.phone_code_hash, client=client)
        
        await message.answer("✅ Код отправлен! Введите полученный код из SMS или уведомления Telegram:")
        await state.set_state(AddAccountState.waiting_for_code)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки кода: {e}\nПопробуйте заново.")
        await state.clear()

@admin_router.message(AddAccountState.waiting_for_code)
async def process_code(message: Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    
    phone = data['phone']
    code_hash = data['code_hash']
    client = data['client']
    
    try:
        # Пытаемся войти с кодом
        await client.sign_in(phone, code_hash, code)
        
        # Если вошли без 2FA, сохраняем сессию в виде строки
        session_string = await client.export_session_string()
        db.add_userbot(phone, session_string)
        
        await message.answer(f"🎉 Аккаунт `{phone}` успешно добавлен в систему и готов к работе!", reply_markup=get_main_keyboard())
        await client.disconnect()
        await state.clear()
        
    except SessionPasswordNeeded:
        # Если включена двухфакторка
        await message.answer("🔒 Этот аккаунт защищен облачным паролем (2FA).\nВведите ваш пароль:")
        await state.set_state(AddAccountState.waiting_for_2fa)
        
    except (PhoneCodeInvalid, PhoneCodeExpired):
        await message.answer("❌ Неверный или устаревший код. Попробуйте еще раз ввести код:")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        await client.disconnect()
        await state.clear()

@admin_router.message(AddAccountState.waiting_for_2fa)
async def process_2fa(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    
    phone = data['phone']
    client = data['client']
    
    try:
        # Входим с паролем 2FA
        await client.check_password(password)
        
        # Сохраняем сессию в базу данных
        session_string = await client.export_session_string()
        db.add_userbot(phone, session_string)
        
        await message.answer(f"🎉 Аккаунт `{phone}` (с 2FA) успешно добавлен!", reply_markup=get_main_keyboard())
        await client.disconnect()
        await state.clear()
        
    except Exception as e:
        await message.answer(f"❌ Неверный пароль или произошла ошибка: {e}\nВведите пароль еще раз:")

# Заглушка для чекера (сделаем следующим шагом)
@admin_router.message(F.text == "🔍 Проверить базу номеров")
async def check_phones_prompt(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer("⚙️ Логика загрузки номеров будет добавлена в следующем файле.")
