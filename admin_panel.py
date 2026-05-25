import asyncio
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded
import database as db
import userbot_manager as ub_mgr
from config import ADMIN_IDS

admin_router = Router()

# Состояния для всех 5 кнопок
class MainStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()
    waiting_for_mailing_text = State()
    waiting_for_mailing_file = State()
    waiting_for_api_id = State()
    waiting_for_api_hash = State()
    waiting_for_check_file = State()

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📱 Добавить аккаунт (UserBot)")],
        [KeyboardButton(text="🚀 Запустить рекламу"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="⚙️ Настройка API"), KeyboardButton(text="🔍 Проверить базу")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# 1. ДОБАВИТЬ АККАУНТ
@admin_router.message(F.text == "📱 Добавить аккаунт (UserBot)")
async def add_acc_start(message: Message, state: FSMContext):
    await message.answer("Пришлите номер телефона (в формате +7...):")
    await state.set_state(MainStates.waiting_for_phone)

# ... (Логика авторизации через send_code как в предыдущих примерах)

# 2. ЗАПУСТИТЬ РЕКЛАМУ
@admin_router.message(F.text == "🚀 Запустить рекламу")
async def mailing_start(message: Message, state: FSMContext):
    await message.answer("Введите текст сообщения:")
    await state.set_state(MainStates.waiting_for_mailing_text)

@admin_router.message(MainStates.waiting_for_mailing_text)
async def mailing_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("Теперь отправьте файл (.txt) со списком контактов:")
    await state.set_state(MainStates.waiting_for_mailing_file)

# 3. СТАТИСТИКА
@admin_router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    # Логика: выбор из БД данных по сессиям и счетчикам отправки
    await message.answer("📊 Отчет по работе аккаунтов:\nАктивных: X | Всего отправлено: Y")

# 4. НАСТРОЙКА API
@admin_router.message(F.text == "⚙️ Настройка API")
async def api_settings(message: Message, state: FSMContext):
    await message.answer("Введите API_ID:")
    await state.set_state(MainStates.waiting_for_api_id)

@admin_router.message(MainStates.waiting_for_api_id)
async def get_api_id(message: Message, state: FSMContext):
    await state.update_data(api_id=message.text)
    await message.answer("Теперь введите API_HASH:")
    await state.set_state(MainStates.waiting_for_api_hash)

# 5. ПРОВЕРИТЬ БАЗУ
@admin_router.message(F.text == "🔍 Проверить базу")
async def check_base_start(message: Message, state: FSMContext):
    await message.answer("Отправьте файл с базой номеров для проверки:")
    await state.set_state(MainStates.waiting_for_check_file)
