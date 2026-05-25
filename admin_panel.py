import asyncio
import os
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, Document
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Filter
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeExpired, PhoneCodeInvalid
import database as db
import userbot_manager as ub_mgr
from config import ADMIN_IDS, SESSIONS_DIR, UPLOADS_DIR

admin_router = Router()


class IsAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in ADMIN_IDS


admin_router.message.filter(IsAdmin())


class MainStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()
    waiting_for_mailing_text = State()
    waiting_for_mailing_file = State()
    waiting_for_api_id = State()
    waiting_for_api_hash = State()
    waiting_for_check_file = State()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📱 Добавить аккаунт (UserBot)")],
        [KeyboardButton(text="🚀 Запустить рекламу"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="⚙️ Настройка API"), KeyboardButton(text="🔍 Проверить базу")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


@admin_router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в панель управления UserBot-рассылкой!",
        reply_markup=get_main_keyboard(),
    )


# ──────────────────────────────────────────────────────────────
# 1. ДОБАВИТЬ АККАУНТ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "📱 Добавить аккаунт (UserBot)")
async def add_acc_start(message: Message, state: FSMContext) -> None:
    settings = await db.get_api_settings()
    if not settings:
        await message.answer(
            "⚠️ Сначала настройте API через кнопку ⚙️ Настройка API"
        )
        return
    await message.answer("Введите номер телефона аккаунта (формат: +79001234567):")
    await state.set_state(MainStates.waiting_for_phone)


@admin_router.message(MainStates.waiting_for_phone)
async def add_acc_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip() if message.text else ""
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("❌ Некорректный номер. Введите в формате +79001234567:")
        return

    settings = await db.get_api_settings()
    if not settings:
        await message.answer("⚠️ API не настроен. Воспользуйтесь ⚙️ Настройка API")
        await state.clear()
        return

    api_id, api_hash = settings
    session_name = f"acc_{phone.replace('+', '')}"
    os.makedirs(SESSIONS_DIR, exist_ok=True)

    client = await ub_mgr.create_temp_client(api_id, api_hash, session_name)

    try:
        await client.connect()
        sent = await client.send_code(phone)
        await state.update_data(
            phone=phone,
            session_name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            phone_code_hash=sent.phone_code_hash,
        )
        await message.answer("📨 Код отправлен. Введите код из Telegram (без пробелов):")
        await state.update_data(_client_ref=id(client))
        client._phone_temp = phone
        ub_mgr._clients[f"__temp_{phone}"] = client
        await state.set_state(MainStates.waiting_for_code)
    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка при отправке кода: {e}")
        await state.clear()


@admin_router.message(MainStates.waiting_for_code)
async def add_acc_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip() if message.text else ""
    data = await state.get_data()
    phone: str = data["phone"]
    phone_code_hash: str = data["phone_code_hash"]
    api_id: int = data["api_id"]
    api_hash: str = data["api_hash"]
    session_name: str = data["session_name"]

    client: Client = ub_mgr._clients.get(f"__temp_{phone}")
    if not client:
        await message.answer("❌ Сессия истекла. Начните заново.")
        await state.clear()
        return

    try:
        await client.sign_in(phone, phone_code_hash, code)
        await db.add_account(phone, session_name, api_id, api_hash)
        ub_mgr._clients[phone] = client
        del ub_mgr._clients[f"__temp_{phone}"]
        await message.answer(
            f"✅ Аккаунт {phone} успешно добавлен!",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
    except SessionPasswordNeeded:
        await message.answer("🔐 Требуется пароль двухфакторной аутентификации. Введите пароль:")
        await state.set_state(MainStates.waiting_for_2fa)
    except PhoneCodeExpired:
        await client.disconnect()
        del ub_mgr._clients[f"__temp_{phone}"]
        await message.answer("❌ Код истёк. Попробуйте снова.")
        await state.clear()
    except PhoneCodeInvalid:
        await message.answer("❌ Неверный код. Введите ещё раз:")
    except Exception as e:
        await message.answer(f"❌ Ошибка входа: {e}")
        await state.clear()


@admin_router.message(MainStates.waiting_for_2fa)
async def add_acc_2fa(message: Message, state: FSMContext) -> None:
    password = message.text.strip() if message.text else ""
    data = await state.get_data()
    phone: str = data["phone"]
    api_id: int = data["api_id"]
    api_hash: str = data["api_hash"]
    session_name: str = data["session_name"]

    client: Client = ub_mgr._clients.get(f"__temp_{phone}")
    if not client:
        await message.answer("❌ Сессия истекла. Начните заново.")
        await state.clear()
        return

    try:
        await client.check_password(password)
        await db.add_account(phone, session_name, api_id, api_hash)
        ub_mgr._clients[phone] = client
        del ub_mgr._clients[f"__temp_{phone}"]
        await message.answer(
            f"✅ Аккаунт {phone} добавлен (2FA прошёл успешно)!",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Неверный пароль 2FA: {e}")


# ──────────────────────────────────────────────────────────────
# 2. ЗАПУСТИТЬ РЕКЛАМУ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "🚀 Запустить рекламу")
async def mailing_start(message: Message, state: FSMContext) -> None:
    accounts = await db.get_all_accounts()
    if not accounts:
        await message.answer("⚠️ Нет активных аккаунтов. Добавьте хотя бы один через 📱 Добавить аккаунт.")
        return
    await message.answer("✏️ Введите текст сообщения для рассылки:")
    await state.set_state(MainStates.waiting_for_mailing_text)


@admin_router.message(MainStates.waiting_for_mailing_text)
async def mailing_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Пожалуйста, введите текстовое сообщение.")
        return
    await state.update_data(mailing_text=message.text)
    await message.answer(
        "📁 Отправьте .txt файл со списком контактов (один номер/username на строку):"
    )
    await state.set_state(MainStates.waiting_for_mailing_file)


@admin_router.message(MainStates.waiting_for_mailing_file, F.document)
async def mailing_file(message: Message, state: FSMContext) -> None:
    doc: Document = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Пожалуйста, отправьте файл в формате .txt")
        return

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    file_path = os.path.join(UPLOADS_DIR, doc.file_name)
    await message.bot.download(doc, destination=file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        contacts = [line.strip() for line in f if line.strip()]

    if not contacts:
        await message.answer("❌ Файл пустой или не содержит контактов.")
        await state.clear()
        return

    data = await state.get_data()
    text: str = data["mailing_text"]
    await state.clear()

    status_msg = await message.answer(
        f"🚀 Начинаю рассылку по {len(contacts)} контактам...\nПожалуйста, подождите."
    )

    async def progress(done: int, total: int, res: dict) -> None:
        try:
            await status_msg.edit_text(
                f"⏳ Прогресс: {done}/{total}\n"
                f"✅ Успешно: {res['ok']} | ❌ Ошибок: {res['fail']}"
            )
        except Exception:
            pass

    results = await ub_mgr.run_mailing(text, contacts, progress_callback=progress)

    await status_msg.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"📤 Всего контактов: {len(contacts)}\n"
        f"✅ Отправлено: {results['ok']}\n"
        f"❌ Ошибок: {results['fail']}",
        reply_markup=get_main_keyboard(),
    )


@admin_router.message(MainStates.waiting_for_mailing_file)
async def mailing_file_wrong(message: Message) -> None:
    await message.answer("❌ Ожидается .txt файл. Пожалуйста, отправьте файл с контактами.")


# ──────────────────────────────────────────────────────────────
# 3. СТАТИСТИКА
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "📊 Статистика")
async def show_stats(message: Message) -> None:
    stats = await db.get_stats()
    accounts = await db.get_all_accounts()

    lines = [
        "📊 <b>Статистика рассылки</b>\n",
        f"🟢 Активных аккаунтов: <b>{stats['active']}</b>",
        f"🔴 Отключённых: <b>{stats['inactive']}</b>",
        f"📤 Всего отправлено сообщений: <b>{stats['total_sent']}</b>",
        f"📅 Отправлено сегодня: <b>{stats['sent_today']}</b>",
    ]

    if accounts:
        lines.append("\n<b>Аккаунты:</b>")
        for acc in accounts:
            lines.append(f"  • {acc['phone']} — отправлено: {acc['sent_count']}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ──────────────────────────────────────────────────────────────
# 4. НАСТРОЙКА API
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "⚙️ Настройка API")
async def api_settings_start(message: Message, state: FSMContext) -> None:
    current = await db.get_api_settings()
    hint = ""
    if current:
        hint = f"\n\n(Текущий API_ID: <code>{current[0]}</code>)"
    await message.answer(
        f"🔧 Введите <b>API_ID</b> (число) из my.telegram.org:{hint}",
        parse_mode="HTML",
    )
    await state.set_state(MainStates.waiting_for_api_id)


@admin_router.message(MainStates.waiting_for_api_id)
async def get_api_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("❌ API_ID должен быть числом. Попробуйте ещё раз:")
        return
    await state.update_data(api_id=int(text))
    await message.answer("Теперь введите <b>API_HASH</b> (строка):", parse_mode="HTML")
    await state.set_state(MainStates.waiting_for_api_hash)


@admin_router.message(MainStates.waiting_for_api_hash)
async def get_api_hash(message: Message, state: FSMContext) -> None:
    api_hash = message.text.strip() if message.text else ""
    if len(api_hash) < 10:
        await message.answer("❌ Слишком короткий API_HASH. Введите корректное значение:")
        return
    data = await state.get_data()
    api_id: int = data["api_id"]
    await db.save_api_settings(api_id, api_hash)
    await state.clear()
    await message.answer(
        f"✅ API настроен!\nAPI_ID: <code>{api_id}</code>\nAPI_HASH: <code>{api_hash}</code>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ──────────────────────────────────────────────────────────────
# 5. ПРОВЕРИТЬ БАЗУ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "🔍 Проверить базу")
async def check_base_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "📁 Отправьте .txt файл с базой номеров для проверки (один номер на строку):"
    )
    await state.set_state(MainStates.waiting_for_check_file)


@admin_router.message(MainStates.waiting_for_check_file, F.document)
async def check_base_file(message: Message, state: FSMContext) -> None:
    doc: Document = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Пожалуйста, отправьте .txt файл.")
        return

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    file_path = os.path.join(UPLOADS_DIR, f"check_{doc.file_name}")
    await message.bot.download(doc, destination=file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        numbers = [line.strip() for line in f if line.strip()]

    await state.clear()

    if not numbers:
        await message.answer("❌ Файл пустой.", reply_markup=get_main_keyboard())
        return

    accounts = await db.get_all_accounts()
    active_phones = {a["phone"] for a in accounts}

    found = [n for n in numbers if n in active_phones]
    not_found = [n for n in numbers if n not in active_phones]

    result_lines = [
        f"🔍 <b>Результат проверки базы</b>\n",
        f"📋 Всего номеров в файле: <b>{len(numbers)}</b>",
        f"✅ Найдено в активных аккаунтах: <b>{len(found)}</b>",
        f"❌ Не найдено: <b>{len(not_found)}</b>",
    ]

    if found:
        result_lines.append("\n<b>Найденные номера:</b>")
        for n in found[:20]:
            result_lines.append(f"  ✅ {n}")
        if len(found) > 20:
            result_lines.append(f"  ... и ещё {len(found) - 20}")

    await message.answer(
        "\n".join(result_lines),
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


@admin_router.message(MainStates.waiting_for_check_file)
async def check_base_wrong(message: Message) -> None:
    await message.answer("❌ Ожидается .txt файл. Пожалуйста, отправьте файл с номерами.")
