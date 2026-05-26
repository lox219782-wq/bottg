import asyncio
import inspect
import logging
import os
import random
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, Document
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Filter
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeExpired, PhoneCodeInvalid
import database as db
import userbot_manager as ub_mgr
from config import ADMIN_IDS, UPLOADS_DIR

logger = logging.getLogger(__name__)
admin_router = Router()

BACK = "🔙 Назад"
STOP_BTN = "🛑 Остановить рассылку"

_mailing_task: asyncio.Task | None = None


class IsAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        if message.from_user is None:
            return False
        try:
            return await db.is_admin(message.from_user.id)
        except Exception:
            return message.from_user.id in ADMIN_IDS


admin_router.message.filter(IsAdmin())


class States(StatesGroup):
    # Аккаунты
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()
    # API
    waiting_for_api_id = State()
    waiting_for_api_hash = State()
    # Рассылка
    waiting_for_mailing_file = State()
    waiting_for_mailing_interval = State()
    # Шаблоны
    waiting_for_template_add = State()
    waiting_for_template_edit_num = State()
    waiting_for_template_edit_text = State()
    waiting_for_template_delete_num = State()
    # Администраторы
    waiting_for_new_admin_id = State()
    waiting_for_remove_admin_id = State()


# ──────────────────────────────────────────────────────────────
# КЛАВИАТУРЫ
# ──────────────────────────────────────────────────────────────

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Аккаунты"), KeyboardButton(text="📱 Добавить аккаунт")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Настройка API")],
            [KeyboardButton(text="🚀 Запустить рассылку")],
            [KeyboardButton(text="📝 Шаблоны"), KeyboardButton(text="🔑 Администраторы")],
        ],
        resize_keyboard=True,
    )


def get_back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BACK)]],
        resize_keyboard=True,
    )


def get_stop_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=STOP_BTN)]],
        resize_keyboard=True,
    )


def get_templates_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить шаблон"), KeyboardButton(text="✏️ Изменить шаблон")],
            [KeyboardButton(text="🗑 Удалить шаблон")],
            [KeyboardButton(text=BACK)],
        ],
        resize_keyboard=True,
    )


def get_admins_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить админа"), KeyboardButton(text="➖ Удалить админа")],
            [KeyboardButton(text=BACK)],
        ],
        resize_keyboard=True,
    )


# ──────────────────────────────────────────────────────────────
# НАЗАД
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == BACK)
async def go_back(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current in (
        States.waiting_for_phone,
        States.waiting_for_code,
        States.waiting_for_2fa,
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
    await message.answer("👋 Добро пожаловать!\n\nВыберите действие:", reply_markup=get_main_keyboard())


# ──────────────────────────────────────────────────────────────
# 1. АККАУНТЫ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "👥 Аккаунты")
async def show_accounts(message: Message) -> None:
    accounts = await db.get_all_accounts()
    if not accounts:
        await message.answer(
            "👥 <b>Аккаунты</b>\n\n❌ Нет добавленных аккаунтов.\n\nНажмите <b>📱 Добавить аккаунт</b>.",
            parse_mode="HTML", reply_markup=get_main_keyboard(),
        )
        return
    lines = [f"👥 <b>Аккаунты ({len(accounts)})</b>\n"]
    for acc in accounts:
        status = "🟢" if acc.get("active", 1) else "🔴"
        lines.append(
            f"{status} <code>{acc['phone']}</code>\n"
            f"   📤 Отправлено: {acc['sent_count']}\n"
            f"   📅 Добавлен: {str(acc.get('added_at', ''))[:10]}"
        )
    await message.answer("\n\n".join(lines), parse_mode="HTML", reply_markup=get_main_keyboard())


# ──────────────────────────────────────────────────────────────
# 2. ДОБАВИТЬ АККАУНТ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "📱 Добавить аккаунт")
async def add_account_start(message: Message, state: FSMContext) -> None:
    api_id, api_hash = await db.get_api_settings()
    if not api_id or not api_hash:
        await message.answer(
            "⚠️ Сначала настройте API через <b>⚙️ Настройка API</b>.",
            parse_mode="HTML", reply_markup=get_main_keyboard(),
        )
        return
    await message.answer(
        "📱 <b>Добавление аккаунта</b>\n\nВведите номер телефона в формате <code>+79001234567</code>:",
        parse_mode="HTML", reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_phone)


@admin_router.message(States.waiting_for_phone)
async def add_acc_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip() if message.text else ""
    if not phone.startswith("+") or not phone[1:].isdigit() or len(phone) < 10:
        await message.answer(
            "❌ Некорректный номер. Формат: <code>+79001234567</code>",
            parse_mode="HTML", reply_markup=get_back_keyboard(),
        )
        return

    api_id, api_hash = await db.get_api_settings()
    await message.answer("⏳ Отправляю код...", reply_markup=get_back_keyboard())

    client = Client(
        name=f"temp_{phone.replace('+', '')}",
        api_id=api_id,
        api_hash=api_hash,
        in_memory=True,
        no_updates=True,
    )
    try:
        await client.connect()
        sent = await client.send_code(phone)
        ub_mgr._clients[f"__temp_{phone}"] = client
        await state.update_data(phone=phone, api_id=api_id, api_hash=api_hash,
                                phone_code_hash=sent.phone_code_hash)
        await message.answer(
            "📨 Код отправлен в Telegram.\n\nВведите код без пробелов (например: <code>12345</code>):",
            parse_mode="HTML", reply_markup=get_back_keyboard(),
        )
        await state.set_state(States.waiting_for_code)
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML", reply_markup=get_main_keyboard())
        await state.clear()


@admin_router.message(States.waiting_for_code)
async def add_acc_code(message: Message, state: FSMContext) -> None:
    code = "".join((message.text or "").split())
    data = await state.get_data()
    phone: str = data["phone"]
    phone_code_hash: str = data["phone_code_hash"]
    api_id: int = data["api_id"]
    api_hash: str = data["api_hash"]

    if not code.isdigit():
        await message.answer("❌ Только цифры. Попробуйте ещё раз:", reply_markup=get_back_keyboard())
        return

    client: Client | None = ub_mgr._clients.get(f"__temp_{phone}")
    if not client:
        await message.answer("❌ Сессия истекла. Начните заново.", reply_markup=get_main_keyboard())
        await state.clear()
        return

    try:
        await client.sign_in(phone, phone_code_hash, code)
        await _finalize_account(message, state, client, phone, api_id, api_hash)
    except SessionPasswordNeeded:
        await message.answer("🔐 Введите пароль 2FA:", reply_markup=get_back_keyboard())
        await state.set_state(States.waiting_for_2fa)
    except PhoneCodeExpired:
        await _cleanup_temp(phone)
        await message.answer(
            "⏰ Код истёк. Нажмите <b>📱 Добавить аккаунт</b> снова.",
            parse_mode="HTML", reply_markup=get_main_keyboard(),
        )
        await state.clear()
    except PhoneCodeInvalid:
        await message.answer("❌ Неверный код. Попробуйте ещё раз:", reply_markup=get_back_keyboard())
    except Exception as e:
        err = str(e)
        if "SESSION_PASSWORD_NEEDED" in err:
            await message.answer("🔐 Введите пароль 2FA:", reply_markup=get_back_keyboard())
            await state.set_state(States.waiting_for_2fa)
        elif "PHONE_CODE_EXPIRED" in err:
            await _cleanup_temp(phone)
            await message.answer(
                "⏰ Код истёк. Нажмите <b>📱 Добавить аккаунт</b> снова.",
                parse_mode="HTML", reply_markup=get_main_keyboard(),
            )
            await state.clear()
        elif "PHONE_CODE_INVALID" in err:
            await message.answer("❌ Неверный код. Попробуйте ещё раз:", reply_markup=get_back_keyboard())
        else:
            await _cleanup_temp(phone)
            await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML", reply_markup=get_main_keyboard())
            await state.clear()


@admin_router.message(States.waiting_for_2fa)
async def add_acc_2fa(message: Message, state: FSMContext) -> None:
    password = message.text.strip() if message.text else ""
    data = await state.get_data()
    phone: str = data["phone"]
    api_id: int = data["api_id"]
    api_hash: str = data["api_hash"]

    client: Client | None = ub_mgr._clients.get(f"__temp_{phone}")
    if not client:
        await message.answer("❌ Сессия истекла. Начните заново.", reply_markup=get_main_keyboard())
        await state.clear()
        return

    try:
        await client.check_password(password)
        await _finalize_account(message, state, client, phone, api_id, api_hash)
    except Exception as e:
        await message.answer(
            f"❌ Неверный пароль: <code>{e}</code>\n\nПопробуйте ещё раз:",
            parse_mode="HTML", reply_markup=get_back_keyboard(),
        )


async def _finalize_account(
    message: Message, state: FSMContext, client: Client,
    phone: str, api_id: int, api_hash: str,
) -> None:
    try:
        raw_result = client.export_session_string()
        session_string = await raw_result if inspect.isawaitable(raw_result) else raw_result
    except Exception as e:
        await _cleanup_temp(phone)
        await message.answer(f"❌ Ошибка экспорта сессии: <code>{e}</code>",
                             parse_mode="HTML", reply_markup=get_main_keyboard())
        await state.clear()
        return

    if not session_string:
        await _cleanup_temp(phone)
        await message.answer("❌ Сессия пустая — добавьте аккаунт заново.", reply_markup=get_main_keyboard())
        await state.clear()
        return

    await db.add_account(phone, session_string, api_id, api_hash)
    ub_mgr._clients[phone] = client
    ub_mgr._clients.pop(f"__temp_{phone}", None)

    await message.answer(
        f"✅ Аккаунт <code>{phone}</code> добавлен!\nСессия сохранена в базу данных.",
        parse_mode="HTML", reply_markup=get_main_keyboard(),
    )
    await state.clear()


async def _cleanup_temp(phone: str) -> None:
    client = ub_mgr._clients.pop(f"__temp_{phone}", None)
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────
# 3. ШАБЛОНЫ
# ──────────────────────────────────────────────────────────────

def _format_templates(templates: list[dict]) -> str:
    if not templates:
        return "📝 <b>Шаблоны</b>\n\n<i>Шаблонов нет. Нажмите ➕ Добавить шаблон</i>"
    lines = [f"📝 <b>Шаблоны ({len(templates)})</b>\n"]
    for i, t in enumerate(templates, 1):
        preview = t["text"][:80].replace("\n", " ")
        if len(t["text"]) > 80:
            preview += "..."
        lines.append(f"<b>{i}.</b> {preview}")
    return "\n\n".join(lines)


@admin_router.message(F.text == "📝 Шаблоны")
async def show_templates(message: Message, state: FSMContext) -> None:
    await state.clear()
    templates = await db.get_templates()
    await message.answer(
        _format_templates(templates),
        parse_mode="HTML",
        reply_markup=get_templates_keyboard(),
    )


@admin_router.message(F.text == "➕ Добавить шаблон")
async def add_template_start(message: Message, state: FSMContext) -> None:
    templates = await db.get_templates()
    if len(templates) >= 10:
        await message.answer(
            "❌ Максимум 10 шаблонов. Удалите один перед добавлением.",
            reply_markup=get_templates_keyboard(),
        )
        return
    await message.answer(
        "➕ <b>Новый шаблон</b>\n\nВведите текст сообщения:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_template_add)


@admin_router.message(States.waiting_for_template_add)
async def add_template_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Введите текстовое сообщение:", reply_markup=get_back_keyboard())
        return
    await db.add_template(message.text)
    templates = await db.get_templates()
    await state.clear()
    await message.answer(
        f"✅ Шаблон добавлен! Всего шаблонов: <b>{len(templates)}</b>\n\n"
        + _format_templates(templates),
        parse_mode="HTML",
        reply_markup=get_templates_keyboard(),
    )


@admin_router.message(F.text == "✏️ Изменить шаблон")
async def edit_template_start(message: Message, state: FSMContext) -> None:
    templates = await db.get_templates()
    if not templates:
        await message.answer("❌ Нет шаблонов для изменения.", reply_markup=get_templates_keyboard())
        return
    await message.answer(
        _format_templates(templates) + "\n\nВведите <b>номер</b> шаблона который хотите изменить:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_template_edit_num)


@admin_router.message(States.waiting_for_template_edit_num)
async def edit_template_num(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    templates = await db.get_templates()
    if not text.isdigit() or not (1 <= int(text) <= len(templates)):
        await message.answer(
            f"❌ Введите номер от 1 до {len(templates)}:",
            reply_markup=get_back_keyboard(),
        )
        return
    idx = int(text) - 1
    chosen = templates[idx]
    await state.update_data(edit_template_id=chosen["id"], edit_template_num=int(text))
    await message.answer(
        f"✏️ <b>Шаблон #{text}</b>\n\n<i>Текущий текст:</i>\n{chosen['text']}\n\n"
        f"Введите новый текст:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_template_edit_text)


@admin_router.message(States.waiting_for_template_edit_text)
async def edit_template_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Введите текстовое сообщение:", reply_markup=get_back_keyboard())
        return
    data = await state.get_data()
    template_id: int = data["edit_template_id"]
    num: int = data["edit_template_num"]
    await db.update_template(template_id, message.text)
    await state.clear()
    templates = await db.get_templates()
    await message.answer(
        f"✅ Шаблон #{num} обновлён!\n\n" + _format_templates(templates),
        parse_mode="HTML",
        reply_markup=get_templates_keyboard(),
    )


@admin_router.message(F.text == "🗑 Удалить шаблон")
async def delete_template_start(message: Message, state: FSMContext) -> None:
    templates = await db.get_templates()
    if not templates:
        await message.answer("❌ Нет шаблонов для удаления.", reply_markup=get_templates_keyboard())
        return
    await message.answer(
        _format_templates(templates) + "\n\nВведите <b>номер</b> шаблона для удаления:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_template_delete_num)


@admin_router.message(States.waiting_for_template_delete_num)
async def delete_template_num(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    templates = await db.get_templates()
    if not text.isdigit() or not (1 <= int(text) <= len(templates)):
        await message.answer(
            f"❌ Введите номер от 1 до {len(templates)}:",
            reply_markup=get_back_keyboard(),
        )
        return
    idx = int(text) - 1
    chosen = templates[idx]
    await db.delete_template(chosen["id"])
    await state.clear()
    templates = await db.get_templates()
    await message.answer(
        f"✅ Шаблон #{text} удалён!\n\n" + _format_templates(templates),
        parse_mode="HTML",
        reply_markup=get_templates_keyboard(),
    )


# ──────────────────────────────────────────────────────────────
# 4. РАССЫЛКА
# ──────────────────────────────────────────────────────────────

def _parse_interval(text: str) -> tuple[int, int] | None:
    """
    Парсит интервал. Форматы:
      "30"       → (30, 30)  — фиксированный
      "120-360"  → (120, 360) — диапазон
    Возвращает None если формат неверный.
    """
    text = text.strip().replace(" ", "")
    if "-" in text:
        parts = text.split("-", 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            lo, hi = int(parts[0]), int(parts[1])
            if lo >= 1 and hi >= lo:
                return (lo, hi)
        return None
    if text.isdigit() and int(text) >= 1:
        v = int(text)
        return (v, v)
    return None


@admin_router.message(F.text == "🚀 Запустить рассылку")
async def mailing_start(message: Message, state: FSMContext) -> None:
    global _mailing_task
    if _mailing_task and not _mailing_task.done():
        await message.answer(
            "⚠️ Рассылка уже запущена!\nНажмите <b>🛑 Остановить рассылку</b> чтобы остановить.",
            parse_mode="HTML", reply_markup=get_stop_keyboard(),
        )
        return

    accounts = await db.get_all_accounts()
    if not accounts:
        await message.answer(
            "⚠️ Нет активных аккаунтов.\nДобавьте аккаунт через <b>📱 Добавить аккаунт</b>.",
            parse_mode="HTML", reply_markup=get_main_keyboard(),
        )
        return

    templates = await db.get_templates()
    if not templates:
        await message.answer(
            "⚠️ Нет шаблонов сообщений.\nДобавьте шаблоны через <b>📝 Шаблоны</b>.",
            parse_mode="HTML", reply_markup=get_main_keyboard(),
        )
        return

    await message.answer(
        f"📂 <b>Рассылка — Шаг 1/2</b>\n\n"
        f"📝 Шаблонов: <b>{len(templates)}</b> (будут использоваться по очереди)\n\n"
        f"Отправьте <b>.txt файл</b> со списком номеров телефонов\n"
        f"(один номер на строку, формат: +79001234567)",
        parse_mode="HTML", reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_mailing_file)


@admin_router.message(States.waiting_for_mailing_file, F.document)
async def mailing_got_file(message: Message, state: FSMContext) -> None:
    doc: Document = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Нужен файл <b>.txt</b>. Попробуйте ещё раз:",
                             parse_mode="HTML", reply_markup=get_back_keyboard())
        return

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    file_path = os.path.join(UPLOADS_DIR, doc.file_name)
    await message.bot.download(doc, destination=file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        lines_raw = [line.strip() for line in f if line.strip()]

    numbers = []
    for n in lines_raw:
        clean = n.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if clean.lstrip("+").isdigit() and len(clean) >= 10:
            numbers.append(clean if clean.startswith("+") else f"+{clean}")

    if not numbers:
        await message.answer("❌ Файл не содержит телефонных номеров.", reply_markup=get_main_keyboard())
        await state.clear()
        return

    await state.update_data(numbers=numbers)
    await message.answer(
        f"✅ Загружено <b>{len(numbers)}</b> номеров.\n\n"
        f"⏱ <b>Шаг 2/2:</b> Введите интервал между сообщениями\n\n"
        f"Форматы:\n"
        f"• <code>30</code> — фиксированные 30 секунд\n"
        f"• <code>120-360</code> — случайный интервал от 120 до 360 секунд",
        parse_mode="HTML", reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_mailing_interval)


@admin_router.message(States.waiting_for_mailing_file)
async def mailing_file_wrong(message: Message) -> None:
    await message.answer("❌ Ожидается <b>.txt файл</b> — нажмите скрепку и выберите файл.",
                         parse_mode="HTML", reply_markup=get_back_keyboard())


@admin_router.message(States.waiting_for_mailing_interval)
async def mailing_got_interval(message: Message, state: FSMContext) -> None:
    global _mailing_task

    parsed = _parse_interval(message.text or "")
    if parsed is None:
        await message.answer(
            "❌ Неверный формат.\n\n"
            "Примеры:\n• <code>30</code>\n• <code>120-360</code>",
            parse_mode="HTML", reply_markup=get_back_keyboard(),
        )
        return

    min_interval, max_interval = parsed
    data = await state.get_data()
    numbers: list[str] = data["numbers"]
    await state.clear()

    accounts = await db.get_all_accounts()
    templates = await db.get_templates()
    active_accounts = accounts[:10]
    n_acc = len(active_accounts)

    if min_interval == max_interval:
        interval_text = f"{min_interval} сек"
    else:
        interval_text = f"{min_interval}–{max_interval} сек (случайно)"

    status_msg = await message.answer(
        f"🚀 <b>Рассылка запущена!</b>\n\n"
        f"📋 Номеров: <b>{len(numbers)}</b>\n"
        f"⏱ Интервал: <b>{interval_text}</b>\n"
        f"👤 Аккаунтов: <b>{n_acc}</b> (параллельно)\n"
        f"📝 Шаблонов: <b>{len(templates)}</b> (по очереди)\n\n"
        f"Прогресс: 0/{len(numbers)}",
        parse_mode="HTML", reply_markup=get_stop_keyboard(),
    )

    _mailing_task = asyncio.create_task(
        _run_mailing(
            bot=message.bot,
            chat_id=message.chat.id,
            status_msg=status_msg,
            numbers=numbers,
            templates=[t["text"] for t in templates],
            min_interval=min_interval,
            max_interval=max_interval,
            accounts=active_accounts,
        )
    )


async def _run_mailing(
    bot, chat_id: int, status_msg,
    numbers: list[str], templates: list[str],
    min_interval: int, max_interval: int,
    accounts: list[dict],
) -> None:
    total = len(numbers)
    n_acc = len(accounts)
    n_tpl = len(templates)

    counters = {"ok": 0, "no_tg": 0, "privacy": 0, "banned": 0, "error": 0, "done": 0}
    per_acc = {acc["phone"]: {"ok": 0, "no_tg": 0, "fail": 0} for acc in accounts}
    lock = asyncio.Lock()

    async def update_status() -> None:
        try:
            if min_interval == max_interval:
                interval_text = f"{min_interval} сек"
            else:
                interval_text = f"{min_interval}–{max_interval} сек"
            lines = [
                f"⏳ <b>Рассылка в процессе...</b>\n",
                f"Прогресс: {counters['done']}/{total}",
                f"✅ Отправлено: {counters['ok']}",
                f"⭕ Нет Telegram: {counters['no_tg']}",
                f"🔒 Приватность: {counters['privacy']}",
                f"❌ Ошибок: {counters['error']}",
                f"⏱ Интервал: {interval_text}",
            ]
            if n_acc > 1:
                lines.append("\n<b>По аккаунтам:</b>")
                for phone, s in per_acc.items():
                    lines.append(f"  <code>{phone[-7:]}</code>: ✅{s['ok']} ⭕{s['no_tg']} ❌{s['fail']}")
            await status_msg.edit_text("\n".join(lines), parse_mode="HTML")
        except Exception:
            pass

    async def worker(account: dict, my_numbers: list[str], start_tpl_idx: int) -> None:
        phone = account["phone"]
        try:
            client = await ub_mgr.get_client(phone, account["api_id"], account["api_hash"])
        except Exception as e:
            logger.warning("Не удалось получить клиент %s: %s", phone, e)
            async with lock:
                counters["error"] += len(my_numbers)
                counters["done"] += len(my_numbers)
            return

        last_tpl_idx: int | None = None

        for i, recipient in enumerate(my_numbers):
            # Случайный шаблон, но не тот же что предыдущий
            if n_tpl == 1:
                tpl_idx = 0
            else:
                available = [j for j in range(n_tpl) if j != last_tpl_idx]
                tpl_idx = random.choice(available)
            last_tpl_idx = tpl_idx
            text = templates[tpl_idx]

            try:
                status = await ub_mgr.send_to_phone(client, phone, recipient, text)
            except Exception as e:
                status = f"error: {e}"

            async with lock:
                counters["done"] += 1
                if status == "ok":
                    counters["ok"] += 1
                    per_acc[phone]["ok"] += 1
                elif status == "no_telegram":
                    counters["no_tg"] += 1
                    per_acc[phone]["no_tg"] += 1
                elif status == "privacy":
                    counters["privacy"] += 1
                    per_acc[phone]["fail"] += 1
                elif status == "banned":
                    counters["banned"] += 1
                    per_acc[phone]["fail"] += 1
                else:
                    counters["error"] += 1
                    per_acc[phone]["fail"] += 1

                if counters["done"] % 5 == 0 or counters["done"] == total:
                    asyncio.create_task(update_status())

            # Пауза только если сообщение успешно отправлено
            # Если номера нет в Telegram — сразу переходим к следующему без ожидания
            if status == "ok" and i < len(my_numbers) - 1:
                wait = random.randint(min_interval, max_interval)
                logger.info("Аккаунт %s: следующее сообщение через %d сек", phone, wait)
                await asyncio.sleep(wait)

    # Делим номера между аккаунтами и задаём каждому стартовый индекс шаблона
    worker_coros = []
    for idx, account in enumerate(accounts):
        my_slice = numbers[idx::n_acc]
        if my_slice:
            # Каждый аккаунт начинает с другого шаблона → равномерное распределение
            worker_coros.append(worker(account, my_slice, start_tpl_idx=idx % n_tpl))

    result_text = ""
    try:
        await asyncio.gather(*worker_coros)

        result_text = (
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"📋 Всего номеров: {total}\n"
            f"✅ Отправлено: {counters['ok']}\n"
            f"⭕ Нет Telegram: {counters['no_tg']}\n"
            f"🔒 Приватность: {counters['privacy']}\n"
            f"❌ Ошибок: {counters['error']}\n"
            f"🚫 Забанено аккаунтов: {counters['banned']}\n"
        )
        if n_acc > 1:
            result_text += "\n<b>По аккаунтам:</b>\n"
            for phone, s in per_acc.items():
                result_text += f"  <code>{phone}</code>: ✅{s['ok']} ⭕{s['no_tg']} ❌{s['fail']}\n"

    except asyncio.CancelledError:
        result_text = (
            f"🛑 <b>Рассылка остановлена</b>\n\n"
            f"Обработано: {counters['done']}/{total}\n"
            f"✅ Отправлено: {counters['ok']} | "
            f"⭕ Нет Telegram: {counters['no_tg']} | "
            f"❌ Ошибок: {counters['error']}"
        )

    try:
        await status_msg.edit_text(result_text, parse_mode="HTML")
    except Exception:
        pass

    try:
        await bot.send_message(chat_id, "🏠 Главное меню", reply_markup=get_main_keyboard())
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# СТОП
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == STOP_BTN)
async def mailing_stop(message: Message) -> None:
    global _mailing_task
    if _mailing_task and not _mailing_task.done():
        _mailing_task.cancel()
        await message.answer("🛑 Останавливаю рассылку...", reply_markup=get_main_keyboard())
    else:
        await message.answer("ℹ️ Рассылка не запущена.", reply_markup=get_main_keyboard())


# ──────────────────────────────────────────────────────────────
# 5. СТАТИСТИКА
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "📊 Статистика")
async def show_stats(message: Message) -> None:
    stats = await db.get_stats()
    accounts = await db.get_all_accounts()
    lines = [
        "📊 <b>Статистика</b>\n",
        f"🟢 Активных аккаунтов: <b>{stats['active']}</b>",
        f"🔴 Отключённых: <b>{stats['inactive']}</b>",
        f"📤 Всего отправлено: <b>{stats['total_sent']}</b>",
        f"📅 Отправлено сегодня: <b>{stats['sent_today']}</b>",
    ]
    global _mailing_task
    if _mailing_task and not _mailing_task.done():
        lines.append("\n🔄 <b>Рассылка сейчас активна</b>")
    if accounts:
        lines.append("\n<b>Аккаунты:</b>")
        for acc in accounts:
            s = "🟢" if acc.get("active", 1) else "🔴"
            lines.append(f"  {s} <code>{acc['phone']}</code> — отправлено: {acc['sent_count']}")
    else:
        lines.append("\n<i>Аккаунты не добавлены</i>")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_main_keyboard())


# ──────────────────────────────────────────────────────────────
# 6. НАСТРОЙКА API
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "⚙️ Настройка API")
async def api_settings_start(message: Message, state: FSMContext) -> None:
    current = await db.get_api_settings()
    status = (
        f"\n\n<i>Текущий API_ID: <code>{current[0]}</code></i>" if current[0]
        else "\n\n<i>API ещё не настроен</i>"
    )
    await message.answer(
        f"⚙️ <b>Настройка API Telegram</b>{status}\n\n"
        f"Шаг 1/2: Введите <b>API_ID</b>\n"
        f"Получить: my.telegram.org → App configuration",
        parse_mode="HTML", reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_api_id)


@admin_router.message(States.waiting_for_api_id)
async def get_api_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("❌ API_ID — это число. Попробуйте ещё раз:", reply_markup=get_back_keyboard())
        return
    await state.update_data(api_id=int(text))
    await message.answer(
        f"✅ API_ID: <code>{text}</code>\n\nШаг 2/2: Введите <b>API_HASH</b>:",
        parse_mode="HTML", reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_api_hash)


@admin_router.message(States.waiting_for_api_hash)
async def get_api_hash(message: Message, state: FSMContext) -> None:
    api_hash = message.text.strip() if message.text else ""
    if len(api_hash) < 10:
        await message.answer("❌ API_HASH слишком короткий. Скопируйте с my.telegram.org:",
                             reply_markup=get_back_keyboard())
        return
    data = await state.get_data()
    api_id: int = data["api_id"]
    await db.save_api_settings(api_id, api_hash)
    await state.clear()
    await message.answer(
        f"✅ <b>API настроен!</b>\n\n"
        f"API_ID: <code>{api_id}</code>\n"
        f"API_HASH: <code>{api_hash}</code>\n\n"
        f"Теперь добавьте аккаунт через <b>📱 Добавить аккаунт</b>.",
        parse_mode="HTML", reply_markup=get_main_keyboard(),
    )


# ──────────────────────────────────────────────────────────────
# 7. АДМИНИСТРАТОРЫ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "🔑 Администраторы")
async def show_admins(message: Message, state: FSMContext) -> None:
    await state.clear()
    admins = await db.get_admins()
    lines = [f"🔑 <b>Администраторы ({len(admins)})</b>\n"]
    for uid in admins:
        lines.append(f"  • <code>{uid}</code>")
    lines.append(f"\n<i>Ваш ID: <code>{message.from_user.id}</code></i>")
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=get_admins_keyboard(),
    )


@admin_router.message(F.text == "➕ Добавить админа")
async def add_admin_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "➕ <b>Добавить администратора</b>\n\n"
        "Введите Telegram ID пользователя.\n"
        "Чтобы узнать ID — перешлите сообщение боту @userinfobot",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_new_admin_id)


@admin_router.message(States.waiting_for_new_admin_id)
async def add_admin_id(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ ID должен быть числом. Попробуйте ещё раз:", reply_markup=get_back_keyboard())
        return

    user_id = int(text)
    if user_id == message.from_user.id:
        await message.answer("❌ Нельзя добавить самого себя — вы уже администратор.",
                             reply_markup=get_admins_keyboard())
        await state.clear()
        return

    added = await db.add_admin(user_id)
    if added:
        await message.answer(f"✅ Администратор <code>{user_id}</code> добавлен.",
                             parse_mode="HTML", reply_markup=get_admins_keyboard())
    else:
        await message.answer(f"ℹ️ Пользователь <code>{user_id}</code> уже является администратором.",
                             parse_mode="HTML", reply_markup=get_admins_keyboard())
    await state.clear()


@admin_router.message(F.text == "➖ Удалить админа")
async def remove_admin_start(message: Message, state: FSMContext) -> None:
    admins = await db.get_admins()
    if len(admins) <= 1:
        await message.answer("❌ Нельзя удалить последнего администратора.",
                             reply_markup=get_admins_keyboard())
        return
    lines = ["➖ <b>Удалить администратора</b>\n", "Текущие администраторы:"]
    for uid in admins:
        marker = " (вы)" if uid == message.from_user.id else ""
        lines.append(f"  • <code>{uid}</code>{marker}")
    lines.append("\nВведите ID администратора которого хотите удалить:")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_back_keyboard())
    await state.set_state(States.waiting_for_remove_admin_id)


@admin_router.message(States.waiting_for_remove_admin_id)
async def remove_admin_id(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ ID должен быть числом. Попробуйте ещё раз:", reply_markup=get_back_keyboard())
        return

    user_id = int(text)
    if user_id == message.from_user.id:
        await message.answer("❌ Нельзя удалить самого себя из администраторов.",
                             reply_markup=get_admins_keyboard())
        await state.clear()
        return

    admins = await db.get_admins()
    if len(admins) <= 1:
        await message.answer("❌ Нельзя удалить последнего администратора.",
                             reply_markup=get_admins_keyboard())
        await state.clear()
        return

    removed = await db.remove_admin(user_id)
    if removed:
        await message.answer(f"✅ Администратор <code>{user_id}</code> удалён.",
                             parse_mode="HTML", reply_markup=get_admins_keyboard())
    else:
        await message.answer(f"❌ Администратор <code>{user_id}</code> не найден.",
                             parse_mode="HTML", reply_markup=get_admins_keyboard())
    await state.clear()
