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

BACK = "🔙 Назад"


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


# ──────────────────────────────────────────────────────────────
# КЛАВИАТУРЫ
# ──────────────────────────────────────────────────────────────

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Добавить аккаунт (UserBot)")],
            [KeyboardButton(text="🚀 Запустить рекламу"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="⚙️ Настройка API"), KeyboardButton(text="🔍 Проверить базу")],
        ],
        resize_keyboard=True,
    )


def get_back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BACK)]],
        resize_keyboard=True,
    )


# ──────────────────────────────────────────────────────────────
# УНИВЕРСАЛЬНАЯ КНОПКА НАЗАД — работает в любом состоянии
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == BACK)
async def go_back(message: Message, state: FSMContext) -> None:
    current = await state.get_state()

    # Если был открыт временный pyrogram-клиент — закрываем его
    if current in (
        MainStates.waiting_for_phone,
        MainStates.waiting_for_code,
        MainStates.waiting_for_2fa,
    ):
        data = await state.get_data()
        phone = data.get("phone")
        if phone:
            client = ub_mgr._clients.pop(f"__temp_{phone}", None)
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    await state.clear()
    await message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())


# ──────────────────────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в панель управления UserBot-рассылкой!\n\n"
        "Выберите действие из меню ниже:",
        reply_markup=get_main_keyboard(),
    )


# ──────────────────────────────────────────────────────────────
# 1. ДОБАВИТЬ АККАУНТ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "📱 Добавить аккаунт (UserBot)")
async def add_acc_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "📱 <b>Добавление аккаунта</b>\n\n"
        "Введите номер телефона в формате <code>+79001234567</code>:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(MainStates.waiting_for_phone)


@admin_router.message(MainStates.waiting_for_phone)
async def add_acc_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip() if message.text else ""
    if not phone.startswith("+") or not phone[1:].isdigit() or len(phone) < 10:
        await message.answer(
            "❌ Некорректный номер.\nВведите в формате <code>+79001234567</code>:",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        return

    api_id, api_hash = await db.get_api_settings()
    session_name = f"acc_{phone.replace('+', '')}"
    os.makedirs(SESSIONS_DIR, exist_ok=True)

    await message.answer("⏳ Отправляю код подтверждения...", reply_markup=get_back_keyboard())

    client = await ub_mgr.create_temp_client(api_id, api_hash, session_name)
    try:
        await client.connect()
        sent = await client.send_code(phone)
        ub_mgr._clients[f"__temp_{phone}"] = client
        await state.update_data(
            phone=phone,
            session_name=session_name,
            api_id=api_id,
            api_hash=api_hash,
            phone_code_hash=sent.phone_code_hash,
        )
        await message.answer(
            "📨 Код отправлен в Telegram.\n\n"
            "Введите код <b>без пробелов</b> (например: <code>12345</code>):",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(MainStates.waiting_for_code)
    except Exception as e:
        await client.disconnect()
        await message.answer(
            f"❌ Ошибка при отправке кода: <code>{e}</code>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()


@admin_router.message(MainStates.waiting_for_code)
async def add_acc_code(message: Message, state: FSMContext) -> None:
    # Убираем пробелы — Telegram показывает код как "1 2 3 4 5"
    code = "".join((message.text or "").split())
    data = await state.get_data()
    phone: str = data["phone"]
    phone_code_hash: str = data["phone_code_hash"]
    api_id: int = data["api_id"]
    api_hash: str = data["api_hash"]
    session_name: str = data["session_name"]

    if not code.isdigit():
        await message.answer(
            "❌ Код должен содержать только цифры. Введите ещё раз:",
            reply_markup=get_back_keyboard(),
        )
        return

    client: Client | None = ub_mgr._clients.get(f"__temp_{phone}")
    if not client:
        await message.answer("❌ Сессия истекла. Начните заново.", reply_markup=get_main_keyboard())
        await state.clear()
        return

    try:
        await client.sign_in(phone, phone_code_hash, code)
        await db.add_account(phone, session_name, api_id, api_hash)
        ub_mgr._clients[phone] = client
        ub_mgr._clients.pop(f"__temp_{phone}", None)
        await message.answer(
            f"✅ Аккаунт <code>{phone}</code> успешно добавлен!",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
    except SessionPasswordNeeded:
        await message.answer(
            "🔐 На аккаунте включена двухфакторная аутентификация.\n\nВведите пароль 2FA:",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(MainStates.waiting_for_2fa)
    except PhoneCodeExpired:
        ub_mgr._clients.pop(f"__temp_{phone}", None)
        try:
            await client.disconnect()
        except Exception:
            pass
        await message.answer(
            "⏰ Код действительно истёк (Telegram даёт ~2 минуты).\n\n"
            "Нажмите <b>📱 Добавить аккаунт</b> и запросите новый код.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
    except PhoneCodeInvalid:
        await message.answer(
            "❌ Неверный код. Проверьте цифры и введите ещё раз:",
            reply_markup=get_back_keyboard(),
        )
    except Exception as e:
        # Показываем точную ошибку — помогает диагностировать
        err = str(e)
        if "SESSION_PASSWORD_NEEDED" in err:
            await message.answer(
                "🔐 Требуется пароль 2FA. Введите пароль:",
                reply_markup=get_back_keyboard(),
            )
            await state.set_state(MainStates.waiting_for_2fa)
        elif "PHONE_CODE_EXPIRED" in err:
            ub_mgr._clients.pop(f"__temp_{phone}", None)
            await message.answer(
                "⏰ Код истёк. Нажмите <b>📱 Добавить аккаунт</b> и попробуйте снова.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard(),
            )
            await state.clear()
        elif "PHONE_CODE_INVALID" in err:
            await message.answer(
                "❌ Неверный код. Проверьте цифры и введите ещё раз:",
                reply_markup=get_back_keyboard(),
            )
        else:
            await message.answer(
                f"❌ Ошибка при входе:\n<code>{e}</code>\n\nПопробуйте заново.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard(),
            )
            await state.clear()


@admin_router.message(MainStates.waiting_for_2fa)
async def add_acc_2fa(message: Message, state: FSMContext) -> None:
    password = message.text.strip() if message.text else ""
    data = await state.get_data()
    phone: str = data["phone"]
    api_id: int = data["api_id"]
    api_hash: str = data["api_hash"]
    session_name: str = data["session_name"]

    client: Client | None = ub_mgr._clients.get(f"__temp_{phone}")
    if not client:
        await message.answer("❌ Сессия истекла. Начните заново.", reply_markup=get_main_keyboard())
        await state.clear()
        return

    try:
        await client.check_password(password)
        await db.add_account(phone, session_name, api_id, api_hash)
        ub_mgr._clients[phone] = client
        ub_mgr._clients.pop(f"__temp_{phone}", None)
        await message.answer(
            f"✅ Аккаунт <code>{phone}</code> добавлен (2FA прошёл успешно)!",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
    except Exception as e:
        await message.answer(
            f"❌ Неверный пароль 2FA: <code>{e}</code>\n\nПопробуйте ещё раз:",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )


# ──────────────────────────────────────────────────────────────
# 2. ЗАПУСТИТЬ РЕКЛАМУ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "🚀 Запустить рекламу")
async def mailing_start(message: Message, state: FSMContext) -> None:
    accounts = await db.get_all_accounts()
    if not accounts:
        await message.answer(
            "⚠️ Нет активных аккаунтов.\n"
            "Сначала добавьте аккаунт через <b>📱 Добавить аккаунт</b>.",
            parse_mode="HTML",
        )
        return
    await message.answer(
        "🚀 <b>Запуск рассылки</b>\n\n"
        "Шаг 1/2: Введите текст сообщения, которое будет отправлено контактам:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(MainStates.waiting_for_mailing_text)


@admin_router.message(MainStates.waiting_for_mailing_text)
async def mailing_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, введите текстовое сообщение:",
            reply_markup=get_back_keyboard(),
        )
        return
    await state.update_data(mailing_text=message.text)
    await message.answer(
        f"✅ Текст сохранён.\n\n"
        f"Шаг 2/2: Отправьте <b>.txt файл</b> со списком контактов\n"
        f"(один номер или @username на строку):",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(MainStates.waiting_for_mailing_file)


@admin_router.message(MainStates.waiting_for_mailing_file, F.document)
async def mailing_file(message: Message, state: FSMContext) -> None:
    doc: Document = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer(
            "❌ Нужен файл в формате <b>.txt</b>. Попробуйте ещё раз:",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        return

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    file_path = os.path.join(UPLOADS_DIR, doc.file_name)
    await message.bot.download(doc, destination=file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        contacts = [line.strip() for line in f if line.strip()]

    if not contacts:
        await message.answer(
            "❌ Файл пустой или не содержит контактов.",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
        return

    data = await state.get_data()
    text: str = data["mailing_text"]
    await state.clear()

    status_msg = await message.answer(
        f"🚀 Начинаю рассылку по <b>{len(contacts)}</b> контактам...\n"
        f"Пожалуйста, подождите — это может занять время.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )

    async def progress(done: int, total: int, res: dict) -> None:
        try:
            await status_msg.edit_text(
                f"⏳ <b>Рассылка в процессе...</b>\n\n"
                f"Прогресс: {done}/{total}\n"
                f"✅ Успешно: {res['ok']} | ❌ Ошибок: {res['fail']}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    results = await ub_mgr.run_mailing(text, contacts, progress_callback=progress)

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Всего контактов: {len(contacts)}\n"
        f"✅ Отправлено: {results['ok']}\n"
        f"❌ Ошибок: {results['fail']}",
        parse_mode="HTML",
    )


@admin_router.message(MainStates.waiting_for_mailing_file)
async def mailing_file_wrong(message: Message) -> None:
    await message.answer(
        "❌ Ожидается <b>.txt файл</b> — нажмите скрепку и выберите файл.\n"
        "Или нажмите 🔙 Назад для отмены.",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )


# ──────────────────────────────────────────────────────────────
# 3. СТАТИСТИКА
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "📊 Статистика")
async def show_stats(message: Message) -> None:
    stats = await db.get_stats()
    accounts = await db.get_all_accounts()

    lines = [
        "📊 <b>Статистика</b>\n",
        f"🟢 Активных аккаунтов: <b>{stats['active']}</b>",
        f"🔴 Отключённых аккаунтов: <b>{stats['inactive']}</b>",
        f"👥 Контактов в базе (с Telegram): <b>{stats['contacts']}</b>",
        f"📤 Всего отправлено сообщений: <b>{stats['total_sent']}</b>",
        f"📅 Отправлено сегодня: <b>{stats['sent_today']}</b>",
    ]

    if accounts:
        lines.append("\n<b>Аккаунты:</b>")
        for acc in accounts:
            status = "🟢" if acc["active"] else "🔴"
            lines.append(f"  {status} <code>{acc['phone']}</code> — отправлено: {acc['sent_count']}")
    else:
        lines.append("\n<i>Аккаунты не добавлены</i>")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_main_keyboard())


# ──────────────────────────────────────────────────────────────
# 4. НАСТРОЙКА API
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "⚙️ Настройка API")
async def api_settings_start(message: Message, state: FSMContext) -> None:
    current = await db.get_api_settings()
    status = (
        f"\n\n<i>Текущий API_ID: <code>{current[0]}</code></i>" if current
        else "\n\n<i>API ещё не настроен</i>"
    )
    await message.answer(
        f"⚙️ <b>Настройка API Telegram</b>{status}\n\n"
        f"Шаг 1/2: Введите <b>API_ID</b>\n"
        f"Получить на сайте: my.telegram.org → App configuration",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(MainStates.waiting_for_api_id)


@admin_router.message(MainStates.waiting_for_api_id)
async def get_api_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer(
            "❌ API_ID — это число (например: <code>1234567</code>).\nПопробуйте ещё раз:",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        return
    await state.update_data(api_id=int(text))
    await message.answer(
        f"✅ API_ID сохранён: <code>{text}</code>\n\n"
        f"Шаг 2/2: Введите <b>API_HASH</b>\n"
        f"(строка вида: <code>abc123def456...</code>)",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(MainStates.waiting_for_api_hash)


@admin_router.message(MainStates.waiting_for_api_hash)
async def get_api_hash(message: Message, state: FSMContext) -> None:
    api_hash = message.text.strip() if message.text else ""
    if len(api_hash) < 10:
        await message.answer(
            "❌ API_HASH слишком короткий. Скопируйте его с my.telegram.org:",
            reply_markup=get_back_keyboard(),
        )
        return
    data = await state.get_data()
    api_id: int = data["api_id"]
    await db.save_api_settings(api_id, api_hash)
    await state.clear()
    await message.answer(
        f"✅ <b>API успешно настроен!</b>\n\n"
        f"API_ID: <code>{api_id}</code>\n"
        f"API_HASH: <code>{api_hash}</code>\n\n"
        f"Теперь можно добавлять аккаунты.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ──────────────────────────────────────────────────────────────
# 5. ПРОВЕРИТЬ БАЗУ (проверка номеров на наличие Telegram)
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "🔍 Проверить базу")
async def check_base_start(message: Message, state: FSMContext) -> None:
    accounts = await db.get_all_accounts()
    if not accounts:
        await message.answer(
            "⚠️ Нет активных аккаунтов для проверки.\n"
            "Сначала добавьте аккаунт через <b>📱 Добавить аккаунт</b>.",
            parse_mode="HTML",
        )
        return

    contacts_count = await db.get_contacts_count()
    hint = ""
    if contacts_count:
        hint = f"\n\n📋 Уже в базе: <b>{contacts_count}</b> контактов с Telegram"

    await message.answer(
        "🔍 <b>Проверка базы номеров</b>\n\n"
        "Отправьте <b>.txt файл</b> со списком номеров телефонов\n"
        "(один номер на строку, формат: +79001234567).\n\n"
        "Бот проверит каждый номер — есть ли у него Telegram,\n"
        "и сохранит найденных в базу для рассылки."
        f"{hint}",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(MainStates.waiting_for_check_file)


@admin_router.message(MainStates.waiting_for_check_file, F.document)
async def check_base_file(message: Message, state: FSMContext) -> None:
    doc: Document = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer(
            "❌ Нужен файл в формате <b>.txt</b>. Попробуйте ещё раз:",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        return

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    file_path = os.path.join(UPLOADS_DIR, f"check_{doc.file_name}")
    await message.bot.download(doc, destination=file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    # Нормализуем номера — добавляем + если нет
    numbers = []
    for n in raw_lines:
        if n.lstrip("+").isdigit():
            numbers.append(n if n.startswith("+") else f"+{n}")

    await state.clear()

    if not numbers:
        await message.answer(
            "❌ Файл пустой или не содержит телефонных номеров.",
            reply_markup=get_main_keyboard(),
        )
        return

    status_msg = await message.answer(
        f"🔍 Начинаю проверку <b>{len(numbers)}</b> номеров...\n"
        f"⏳ Это займёт некоторое время.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )

    async def progress(done: int, total: int, found_count: int) -> None:
        try:
            await status_msg.edit_text(
                f"🔍 <b>Проверка в процессе...</b>\n\n"
                f"Обработано: {done}/{total}\n"
                f"✅ Найдено с Telegram: {found_count}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    result = await ub_mgr.check_contacts(numbers, progress_callback=progress)

    if "error" in result:
        await status_msg.edit_text(
            f"❌ Ошибка: {result['error']}",
            reply_markup=get_main_keyboard(),
        )
        return

    found = result["found"]
    new_count = 0
    if found:
        new_count = await db.save_contacts(found)

    total_in_db = await db.get_contacts_count()

    lines = [
        "✅ <b>Проверка завершена!</b>\n",
        f"📋 Всего номеров в файле: <b>{len(numbers)}</b>",
        f"✅ Есть Telegram: <b>{len(found)}</b>",
        f"❌ Нет Telegram: <b>{result['not_found']}</b>",
        f"🆕 Новых добавлено в базу: <b>{new_count}</b>",
        f"📊 Всего в базе контактов: <b>{total_in_db}</b>",
    ]

    if found[:5]:
        lines.append("\n<b>Примеры найденных:</b>")
        for c in found[:5]:
            name = c.get("first_name") or ""
            username = f" @{c['username']}" if c.get("username") else ""
            lines.append(f"  ✅ <code>{c['phone']}</code> {name}{username}")
        if len(found) > 5:
            lines.append(f"  <i>... и ещё {len(found) - 5}</i>")

    await status_msg.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


@admin_router.message(MainStates.waiting_for_check_file)
async def check_base_wrong(message: Message) -> None:
    await message.answer(
        "❌ Ожидается <b>.txt файл</b> — нажмите скрепку и выберите файл.\n"
        "Или нажмите 🔙 Назад для отмены.",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
