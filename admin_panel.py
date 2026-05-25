import asyncio
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired

from config import ADMIN_IDS
import database as db
import userbot_manager as ub_mgr

admin_router = Router()

# Состояния FSM
class AddAccountState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()

class MailingState(StatesGroup):
    choosing_bot = State()
    writing_text = State()
    setting_interval = State()
    waiting_for_file = State()

class CheckPhonesState(StatesGroup):
    waiting_for_file = State()

class ChangeApiState(StatesGroup):
    waiting_for_api_id = State()
    waiting_for_api_hash = State()

# Клавиатура
def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📱 Добавить аккаунт (Юзербот)"), KeyboardButton(text="🚀 Запустить рассылку")],
        [KeyboardButton(text="📊 Статистика системы"), KeyboardButton(text="⚙️ Настройки API")],
        [KeyboardButton(text="🔍 Проверить базу номеров")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@admin_router.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer("👋 Добро пожаловать в панель управления!", reply_markup=get_main_keyboard())

# --- СТАТИСТИКА ---
@admin_router.message(F.text == "📊 Статистика системы")
async def show_stats(message: Message):
    if not is_admin(message.from_user.id): return
    userbots = db.get_all_userbots()
    
    conn = db.sqlite3.connect(db.DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*), SUM(has_telegram=1), SUM(has_telegram=2) FROM phone_checker")
        data = cursor.fetchone()
        total, with_tg, no_tg = (data[0] or 0, data[1] or 0, data[2] or 0)
    except:
        total, with_tg, no_tg = 0, 0, 0
    conn.close()
    
    await message.answer(
        f"📊 **Статистика:**\n"
        f"🤖 Активных аккаунтов: {len(userbots)}\n"
        f"📞 Всего номеров: {total}\n"
        f"✅ С ТГ: {with_tg} | ❌ Без ТГ: {no_tg}"
    )

# --- РАССЫЛКА ---
@admin_router.message(F.text == "🚀 Запустить рассылку")
async def start_mailing_flow(message: Message, state: FSMContext):
    bots = db.get_all_userbots()
    if not bots:
        await message.answer("❌ Сначала добавьте аккаунты!")
        return
    kb = [[KeyboardButton(text=b[0])] for b in bots]
    await message.answer("Выберите аккаунт для рассылки:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    await state.set_state(MailingState.choosing_bot)

@admin_router.message(MailingState.choosing_bot)
async def choose_bot(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Введите текст сообщения:")
    await state.set_state(MailingState.writing_text)

@admin_router.message(MailingState.writing_text)
async def set_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("Введите интервал между сообщениями (сек):")
    await state.set_state(MailingState.setting_interval)

@admin_router.message(MailingState.setting_interval)
async def set_interval(message: Message, state: FSMContext):
    await state.update_data(interval=int(message.text))
    await message.answer("Отправьте .txt файл с номерами:")
    await state.set_state(MailingState.waiting_for_file)

@admin_router.message(MailingState.waiting_for_file, F.document)
async def finish_mailing(message: Message, state: FSMContext):
    data = await state.get_data()
    file_info = await message.bot.get_file(message.document.file_id)
    file_bytes = await message.bot.download_file(file_info.file_path)
    numbers = file_bytes.read().decode('utf-8').splitlines()
    
    bots = dict(db.get_all_userbots())
    session = bots[data['phone']]
    
    await message.answer("✅ Рассылка запущена!")
    asyncio.create_task(ub_mgr.start_mailing(data['phone'], session, data['text'], numbers, data['interval']))
    await state.clear()

# --- API И АККАУНТЫ (Оставь старую логику тут) ---
# [Вставь сюда функции: show_api_settings, process_new_api_id, process_new_api_hash, start_add_account, process_phone, process_code, process_2fa, start_check_phones, process_phones_file из твоего предыдущего файла]
