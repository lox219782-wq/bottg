from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database as db
import userbot_manager as ub_mgr

admin_router = Router()

class MailingState(StatesGroup):
    choosing_bot = State()
    writing_text = State()
    setting_interval = State()
    waiting_for_file = State()

@admin_router.message(F.text == "🚀 Запустить рассылку")
async def start_mailing_flow(message: Message, state: FSMContext):
    bots = db.get_all_userbots()
    if not bots:
        await message.answer("Сначала добавьте аккаунты!")
        return
    kb = [[KeyboardButton(text=b[0])] for b in bots]
    await message.answer("Выберите аккаунт для рассылки:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    await state.set_state(MailingState.choosing_bot)

@admin_router.message(MailingState.choosing_bot)
async def choose_bot(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Введите текст рассылки:")
    await state.set_state(MailingState.writing_text)

@admin_router.message(MailingState.writing_text)
async def set_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("Введите интервал между сообщениями (в секундах):")
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
    
    # Получаем сессию
    bots = dict(db.get_all_userbots())
    session = bots[data['phone']]
    
    await message.answer("Рассылка запущена в фоновом режиме!")
    import asyncio
    asyncio.create_task(ub_mgr.start_mailing(data['phone'], session, data['text'], numbers, data['interval']))
    await state.clear()
