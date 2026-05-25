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

class AddAccountState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()

class CheckPhonesState(StatesGroup):
    waiting_for_file = State()

# Новые состояния для изменения API
class ChangeApiState(StatesGroup):
    waiting_for_api_id = State()
    waiting_for_api_hash = State()

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📱 Добавить аккаунт (Юзербот)")],
        [KeyboardButton(text="📊 Статистика системы"), KeyboardButton(text="⚙️ Настройки API")],
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

# --- УПРАВЛЕНИЕ API ИЗ БОТА ---
@admin_router.message(F.text == "⚙️ Настройки API")
async def show_api_settings(message: Message):
    if not is_admin(message.from_user.id): return
    api_id, api_hash = db.get_api_credentials()
    await message.answer(
        f"⚙️ **Текущие настройки Telegram API:**\n\n"
        f"🔑 **API_ID:** `{api_id}`\n"
        f"🔑 **API_HASH:** `{api_hash}`\n\n"
        f"Чтобы изменить их, введите новый **API_ID** (только цифры) или отправьте /cancel для отмены:"
    )
    await ChangeApiState.waiting_for_api_id.set()

@admin_router.message(ChangeApiState.waiting_for_api_id)
async def process_new_api_id(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await message.answer("Отменено.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    if not message.text.isdigit():
        await message.answer("❌ API_ID должен состоять только из цифр! Введите еще раз:")
        return
    await state.update_data(new_api_id=message.text.strip())
    await message.answer("Теперь введите новый **API_HASH** (строка из букв и цифр):")
    await ChangeApiState.waiting_for_api_hash.set()

@admin_router.message(ChangeApiState.waiting_for_api_hash)
async def process_new_api_hash(message: Message, state: FSMContext):
    data = await state.get_data()
    new_api_id = data['new_api_id']
    new_api_hash = message.text.strip()
    
    db.update_api_credentials(new_api_id, new_api_hash)
    await message.answer("✅ API ключи успешно обновлены в базе данных!", reply_markup=get_main_keyboard())
    await state.clear()

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
    api_id, api_hash = db.get_api_credentials()
    client = Client(f"temp_{phone}", api_id=int(api_id), api_hash=api_hash, in_memory=True)
    await client.connect()
    try:
        code_hash = await client.send_code(phone)
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
    phone, code_hash, client = data['phone'], data['code_hash'], data['client']
    try:
        await client.sign_in(phone, code_hash, code)
        session_string = await client.export_session_string()
        db.add_userbot(phone, session_string)
        await message.answer(f"🎉 Аккаунт `{phone}` успешно добавлен!", reply_markup=get_main_keyboard())
        await client.disconnect()
        await state.clear()
    except SessionPasswordNeeded:
        await message.answer("🔒 Этот аккаунт защищен 2FA паролем. Введите ваш пароль:")
        await state.set_state(AddAccountState.waiting_for_2fa)
    except (PhoneCodeInvalid, PhoneCodeExpired):
        await message.answer("❌ Неверный код. Введите код еще раз:")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        await client.disconnect()
        await state.clear()

@admin_router.message(AddAccountState.waiting_for_2fa)
async def process_2fa(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    phone, client = data['phone'], data['client']
    try:
        await client.check_password(password)
        session_string = await client.export_session_string()
        db.add_userbot(phone, session_string)
        await message.answer(f"🎉 Аккаунт `{phone}` успешно добавлен!", reply_markup=get_main_keyboard())
        await client.disconnect()
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Неверный пароль. Введите пароль еще раз:")

# --- ЛОГИКА ЗАГРУЗКИ НОМЕРОВ ---
@admin_router.message(F.text == "🔍 Проверить базу номеров")
async def start_check_phones(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    active_bots = db.get_all_userbots()
    if not active_bots:
        await message.answer("❌ Сначала добавьте хотя бы один аккаунт (Юзербот), иначе проверять будет нечем!")
        return
    await message.answer("📂 Пожалуйста, отправьте `.txt` файл со списком номеров (каждый номер с новой строки):")
    await state.set_state(CheckPhonesState.waiting_for_file)

@admin_router.message(CheckPhonesState.waiting_for_file, F.document)
async def process_phones_file(message: Message, state: FSMContext):
    document = message.document
    if not document.file_name.endswith('.txt'):
        await message.answer("❌ Ошибка: Система принимает только текстовые файлы `.txt`!")
        return
    await message.answer("📥 Скачиваю и обрабатываю файл...")
    file_info = await message.bot.get_file(document.file_id)
    file_bytes = await message.bot.download_file(file_info.file_path)
    content = file_bytes.read().decode('utf-8')
    phones = [p.strip().replace(" ", "").replace("-", "") for p in content.split('\n') if p.strip()]
    if not phones:
        await message.answer("❌ Файл пуст.")
        await state.clear()
        return
    db.upload_phones(phones)
    await message.answer(f"✅ Успешно загружено номеров: {len(phones)} шт.\n🚀 Запускаю процесс проверки...")
    await state.clear()
    asyncio.create_task(run_checker_flow(message))

async def run_checker_flow(message: Message):
    success = await ub_mgr.start_mass_checking()
    if success:
        await message.answer("🏁 Проверка части номеров успешно завершена! Проверьте вкладку 📊 Статистика системы.")
    else:
        await message.answer("⚠️ Проверка завершилась. Возможно, закончились номера или аккаунт ушел в флуд-вейт.")
