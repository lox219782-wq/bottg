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
MENU_BTN = "🏠 Главное меню"

# phone → Task: несколько рассылок могут работать одновременно
_mailing_tasks: dict[str, asyncio.Task] = {}


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
    waiting_for_mailing_account = State()
    waiting_for_mailing_templates = State()
    waiting_for_mailing_file = State()
    waiting_for_mailing_interval = State()
    # Остановка
    waiting_for_stop_account = State()
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


def get_mailing_active_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура во время активной рассылки: можно вернуться в меню не прерывая её."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_BTN)],
            [KeyboardButton(text=STOP_BTN)],
        ],
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
# ВЕРНУТЬСЯ В МЕНЮ (не останавливает рассылку)
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == MENU_BTN)
async def go_to_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    running = [p for p, t in _mailing_tasks.items() if not t.done()]
    if running:
        accounts_str = ", ".join(f"<code>{p[-7:]}</code>" for p in running)
        await message.answer(
            f"🏠 Главное меню\n\n🔄 Рассылка продолжается: {accounts_str}",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
    else:
        await message.answer("🏠 Главное меню", reply_markup=get_main_keyboard())


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
            "👥 <b>Аккаунты</b>\n\n❌ Нет добавленных аккаунтов.",
            parse_mode="HTML", reply_markup=get_main_keyboard(),
        )
        return
    lines = [f"👥 <b>Аккаунты ({len(accounts)})</b>\n"]
    for acc in accounts:
        phone = acc["phone"]
        is_running = phone in _mailing_tasks and not _mailing_tasks[phone].done()
        status = "🔄" if is_running else ("🟢" if acc.get("active", 1) else "🔴")
        lines.append(
            f"{status} <code>{phone}</code>\n"
            f"   📤 Отправлено: {acc['sent_count']}\n"
            f"   📅 Добавлен: {str(acc.get('added_at', ''))[:10]}"
            + (" (рассылка активна)" if is_running else "")
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
        f"✅ Шаблон добавлен! Всего: <b>{len(templates)}</b>\n\n" + _format_templates(templates),
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
        _format_templates(templates) + "\n\nВведите <b>номер</b> шаблона для изменения:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_template_edit_num)


@admin_router.message(States.waiting_for_template_edit_num)
async def edit_template_num(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    templates = await db.get_templates()
    if not text.isdigit() or not (1 <= int(text) <= len(templates)):
        await message.answer(f"❌ Введите номер от 1 до {len(templates)}:", reply_markup=get_back_keyboard())
        return
    idx = int(text) - 1
    chosen = templates[idx]
    await state.update_data(edit_template_id=chosen["id"], edit_template_num=int(text))
    await message.answer(
        f"✏️ <b>Шаблон #{text}</b>\n\n<i>Текущий текст:</i>\n{chosen['text']}\n\nВведите новый текст:",
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
    await db.update_template(data["edit_template_id"], message.text)
    await state.clear()
    templates = await db.get_templates()
    await message.answer(
        f"✅ Шаблон #{data['edit_template_num']} обновлён!\n\n" + _format_templates(templates),
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
        await message.answer(f"❌ Введите номер от 1 до {len(templates)}:", reply_markup=get_back_keyboard())
        return
    idx = int(text) - 1
    await db.delete_template(templates[idx]["id"])
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


def _running_accounts() -> list[str]:
    return [p for p, t in _mailing_tasks.items() if not t.done()]


@admin_router.message(F.text == "🚀 Запустить рассылку")
async def mailing_start(message: Message, state: FSMContext) -> None:
    accounts = await db.get_all_accounts()
    if not accounts:
        await message.answer(
            "⚠️ Нет активных аккаунтов.\nДобавьте через <b>📱 Добавить аккаунт</b>.",
            parse_mode="HTML", reply_markup=get_main_keyboard(),
        )
        return

    templates = await db.get_templates()
    if not templates:
        await message.answer(
            "⚠️ Нет шаблонов.\nДобавьте через <b>📝 Шаблоны</b>.",
            parse_mode="HTML", reply_markup=get_main_keyboard(),
        )
        return

    running = _running_accounts()
    lines = ["🚀 <b>Выберите аккаунт для рассылки</b>\n"]
    for i, acc in enumerate(accounts, 1):
        phone = acc["phone"]
        is_running = phone in running
        marker = " 🔄 (уже работает)" if is_running else ""
        lines.append(f"<b>{i}.</b> <code>{phone}</code>{marker}")
    lines.append("\nВведите номер аккаунта:")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_back_keyboard())
    await state.update_data(accounts=[acc["phone"] for acc in accounts])
    await state.set_state(States.waiting_for_mailing_account)


@admin_router.message(States.waiting_for_mailing_account)
async def mailing_got_account(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    account_phones: list[str] = data["accounts"]

    if not text.isdigit() or not (1 <= int(text) <= len(account_phones)):
        await message.answer(
            f"❌ Введите номер от 1 до {len(account_phones)}:",
            reply_markup=get_back_keyboard(),
        )
        return

    chosen_phone = account_phones[int(text) - 1]
    running = _running_accounts()
    if chosen_phone in running:
        await message.answer(
            f"⚠️ Аккаунт <code>{chosen_phone}</code> уже ведёт рассылку.\n"
            "Выберите другой или остановите текущую.",
            parse_mode="HTML", reply_markup=get_back_keyboard(),
        )
        return

    await state.update_data(mailing_phone=chosen_phone)

    # Показываем шаблоны и просим выбрать
    templates = await db.get_templates()
    lines = [
        f"✅ Аккаунт: <code>{chosen_phone}</code>\n",
        "📝 <b>Выберите шаблоны для этой рассылки:</b>\n",
    ]
    for i, t in enumerate(templates, 1):
        preview = t["text"][:60].replace("\n", " ")
        if len(t["text"]) > 60:
            preview += "..."
        lines.append(f"<b>{i}.</b> {preview}")
    lines.append(
        "\nВведите номера шаблонов через запятую: <code>1,3</code>\n"
        "Или <code>все</code> — использовать все шаблоны"
    )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_back_keyboard())
    await state.update_data(all_template_ids=[t["id"] for t in templates],
                            all_template_texts=[t["text"] for t in templates],
                            template_count=len(templates))
    await state.set_state(States.waiting_for_mailing_templates)


@admin_router.message(States.waiting_for_mailing_templates)
async def mailing_got_templates(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().lower()
    data = await state.get_data()
    all_texts: list[str] = data["all_template_texts"]
    count: int = data["template_count"]

    if text in ("все", "all", "всё"):
        chosen_texts = all_texts
    else:
        parts = [p.strip() for p in text.split(",")]
        chosen_texts = []
        for p in parts:
            if p.isdigit() and 1 <= int(p) <= count:
                chosen_texts.append(all_texts[int(p) - 1])
        if not chosen_texts:
            await message.answer(
                f"❌ Укажите номера от 1 до {count} через запятую, или <code>все</code>:",
                parse_mode="HTML", reply_markup=get_back_keyboard(),
            )
            return
        # убираем дубли сохраняя порядок
        seen: set[str] = set()
        unique: list[str] = []
        for t in chosen_texts:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        chosen_texts = unique

    await state.update_data(mailing_templates=chosen_texts)
    await message.answer(
        f"✅ Выбрано шаблонов: <b>{len(chosen_texts)}</b>\n\n"
        f"📂 Отправьте <b>.txt файл</b> со списком номеров\n"
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
        f"⏱ Введите интервал между сообщениями:\n\n"
        f"• <code>30</code> — фиксированные 30 секунд\n"
        f"• <code>120-360</code> — случайный интервал от 120 до 360 сек",
        parse_mode="HTML", reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_mailing_interval)


@admin_router.message(States.waiting_for_mailing_file)
async def mailing_file_wrong(message: Message) -> None:
    await message.answer("❌ Ожидается <b>.txt файл</b> — нажмите скрепку и выберите файл.",
                         parse_mode="HTML", reply_markup=get_back_keyboard())


@admin_router.message(States.waiting_for_mailing_interval)
async def mailing_got_interval(message: Message, state: FSMContext) -> None:
    parsed = _parse_interval(message.text or "")
    if parsed is None:
        await message.answer(
            "❌ Неверный формат.\n\nПримеры:\n• <code>30</code>\n• <code>120-360</code>",
            parse_mode="HTML", reply_markup=get_back_keyboard(),
        )
        return

    min_interval, max_interval = parsed
    data = await state.get_data()
    numbers: list[str] = data["numbers"]
    phone: str = data["mailing_phone"]
    templates: list[str] = data["mailing_templates"]
    await state.clear()

    accounts = await db.get_all_accounts()
    account = next((a for a in accounts if a["phone"] == phone), None)
    if not account:
        await message.answer("❌ Аккаунт не найден. Попробуйте снова.", reply_markup=get_main_keyboard())
        return

    if min_interval == max_interval:
        interval_text = f"{min_interval} сек"
    else:
        interval_text = f"{min_interval}–{max_interval} сек (случайно)"

    status_msg = await message.answer(
        f"🚀 <b>Рассылка запущена!</b>\n\n"
        f"👤 Аккаунт: <code>{phone}</code>\n"
        f"📋 Номеров: <b>{len(numbers)}</b>\n"
        f"📝 Шаблонов: <b>{len(templates)}</b>\n"
        f"⏱ Интервал: <b>{interval_text}</b>\n\n"
        f"Прогресс: 0/{len(numbers)}\n\n"
        f"<i>Можете вернуться в меню — рассылка продолжится в фоне</i>",
        parse_mode="HTML",
        reply_markup=get_mailing_active_keyboard(),
    )

    task = asyncio.create_task(
        _run_mailing(
            bot=message.bot,
            chat_id=message.chat.id,
            status_msg=status_msg,
            numbers=numbers,
            templates=templates,
            min_interval=min_interval,
            max_interval=max_interval,
            account=account,
        )
    )
    _mailing_tasks[phone] = task


async def _run_mailing(
    bot, chat_id: int, status_msg,
    numbers: list[str], templates: list[str],
    min_interval: int, max_interval: int,
    account: dict,
) -> None:
    phone = account["phone"]
    total = len(numbers)
    n_tpl = len(templates)

    counters = {"ok": 0, "no_tg": 0, "privacy": 0, "banned": 0, "error": 0, "done": 0}

    async def update_status() -> None:
        try:
            if min_interval == max_interval:
                interval_text = f"{min_interval} сек"
            else:
                interval_text = f"{min_interval}–{max_interval} сек"
            await status_msg.edit_text(
                f"⏳ <b>Рассылка: <code>{phone}</code></b>\n\n"
                f"Прогресс: {counters['done']}/{total}\n"
                f"✅ Отправлено: {counters['ok']}\n"
                f"⭕ Нет Telegram: {counters['no_tg']}\n"
                f"🔒 Приватность: {counters['privacy']}\n"
                f"❌ Ошибок: {counters['error']}\n"
                f"⏱ Интервал: {interval_text}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Перемешанные циклы шаблонов — без повторов подряд
    def _make_cycle(last_idx: int | None) -> list[int]:
        idxs = list(range(n_tpl))
        random.shuffle(idxs)
        if last_idx is not None and n_tpl > 1 and idxs[0] == last_idx:
            swap_pos = random.randint(1, n_tpl - 1)
            idxs[0], idxs[swap_pos] = idxs[swap_pos], idxs[0]
        return idxs

    tpl_queue = _make_cycle(None)
    tpl_pos = 0

    result_text = ""
    try:
        client = await ub_mgr.get_client(phone, account["api_id"], account["api_hash"])

        for i, recipient in enumerate(numbers):
            if tpl_pos >= len(tpl_queue):
                tpl_queue = _make_cycle(tpl_queue[-1])
                tpl_pos = 0
            tpl_idx = tpl_queue[tpl_pos]
            tpl_pos += 1
            text = templates[tpl_idx]

            try:
                status = await ub_mgr.send_to_phone(client, phone, recipient, text)
            except Exception as e:
                status = f"error: {e}"

            counters["done"] += 1
            if status == "ok":
                counters["ok"] += 1
            elif status == "no_telegram":
                counters["no_tg"] += 1
            elif status == "privacy":
                counters["privacy"] += 1
            elif status == "banned":
                counters["banned"] += 1
            else:
                counters["error"] += 1

            if counters["done"] % 5 == 0 or counters["done"] == total:
                asyncio.create_task(update_status())

            # Пауза только после успешной отправки
            if status == "ok" and i < len(numbers) - 1:
                wait = random.randint(min_interval, max_interval)
                logger.info("Аккаунт %s: следующее сообщение через %d сек", phone, wait)
                await asyncio.sleep(wait)

        result_text = (
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"👤 Аккаунт: <code>{phone}</code>\n"
            f"📋 Всего номеров: {total}\n"
            f"✅ Отправлено: {counters['ok']}\n"
            f"⭕ Нет Telegram: {counters['no_tg']}\n"
            f"🔒 Приватность: {counters['privacy']}\n"
            f"❌ Ошибок: {counters['error']}\n"
            f"🚫 Забанено: {counters['banned']}"
        )

    except asyncio.CancelledError:
        result_text = (
            f"🛑 <b>Рассылка остановлена</b>\n\n"
            f"👤 Аккаунт: <code>{phone}</code>\n"
            f"Обработано: {counters['done']}/{total}\n"
            f"✅ Отправлено: {counters['ok']} | "
            f"⭕ Нет TG: {counters['no_tg']} | "
            f"❌ Ошибок: {counters['error']}"
        )

    except Exception as e:
        result_text = (
            f"❌ <b>Рассылка прервана из-за ошибки</b>\n\n"
            f"👤 Аккаунт: <code>{phone}</code>\n"
            f"Обработано: {counters['done']}/{total}\n"
            f"Ошибка: <code>{e}</code>"
        )

    try:
        await status_msg.edit_text(result_text, parse_mode="HTML")
    except Exception:
        pass

    try:
        await bot.send_message(
            chat_id,
            result_text + "\n\n🏠 Главное меню",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# ОСТАНОВИТЬ РАССЫЛКУ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == STOP_BTN)
async def mailing_stop(message: Message, state: FSMContext) -> None:
    running = _running_accounts()

    if not running:
        await message.answer("ℹ️ Нет активных рассылок.", reply_markup=get_main_keyboard())
        return

    if len(running) == 1:
        phone = running[0]
        _mailing_tasks[phone].cancel()
        await message.answer(
            f"🛑 Останавливаю рассылку аккаунта <code>{phone}</code>...",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        return

    # Несколько рассылок — спрашиваем какую остановить
    lines = ["🛑 <b>Выберите рассылку для остановки:</b>\n"]
    for i, p in enumerate(running, 1):
        lines.append(f"<b>{i}.</b> <code>{p}</code>")
    lines.append("\nВведите номер (или <code>все</code> — остановить все):")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_back_keyboard())
    await state.update_data(running_phones=running)
    await state.set_state(States.waiting_for_stop_account)


@admin_router.message(States.waiting_for_stop_account)
async def stop_account_chosen(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().lower()
    data = await state.get_data()
    running: list[str] = data.get("running_phones", [])
    await state.clear()

    if text in ("все", "all", "всё"):
        for p in running:
            if p in _mailing_tasks and not _mailing_tasks[p].done():
                _mailing_tasks[p].cancel()
        await message.answer(
            f"🛑 Останавливаю все рассылки ({len(running)} шт.)...",
            reply_markup=get_main_keyboard(),
        )
        return

    if text.isdigit() and 1 <= int(text) <= len(running):
        phone = running[int(text) - 1]
        if phone in _mailing_tasks and not _mailing_tasks[phone].done():
            _mailing_tasks[phone].cancel()
        await message.answer(
            f"🛑 Останавливаю рассылку аккаунта <code>{phone}</code>...",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        return

    await message.answer(
        f"❌ Введите номер от 1 до {len(running)} или <code>все</code>:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )


# ──────────────────────────────────────────────────────────────
# 5. СТАТИСТИКА
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "📊 Статистика")
async def show_stats(message: Message) -> None:
    stats = await db.get_stats()
    accounts = await db.get_all_accounts()
    running = _running_accounts()

    lines = [
        "📊 <b>Статистика</b>\n",
        f"🟢 Активных аккаунтов: <b>{stats['active']}</b>",
        f"🔴 Отключённых: <b>{stats['inactive']}</b>",
        f"📤 Всего отправлено: <b>{stats['total_sent']}</b>",
        f"📅 Отправлено сегодня: <b>{stats['sent_today']}</b>",
    ]
    if running:
        lines.append(f"\n🔄 <b>Активных рассылок: {len(running)}</b>")
        for p in running:
            lines.append(f"   • <code>{p}</code>")

    if accounts:
        lines.append("\n<b>Аккаунты:</b>")
        for acc in accounts:
            phone = acc["phone"]
            is_running = phone in running
            s = "🔄" if is_running else ("🟢" if acc.get("active", 1) else "🔴")
            lines.append(f"  {s} <code>{phone}</code> — отправлено: {acc['sent_count']}")
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
        f"API_HASH: <code>{api_hash}</code>",
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
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_admins_keyboard())


@admin_router.message(F.text == "➕ Добавить админа")
async def add_admin_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "➕ <b>Добавить администратора</b>\n\n"
        "Введите Telegram ID. Узнать ID: @userinfobot",
        parse_mode="HTML", reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_new_admin_id)


@admin_router.message(States.waiting_for_new_admin_id)
async def add_admin_id(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ ID должен быть числом:", reply_markup=get_back_keyboard())
        return
    user_id = int(text)
    if user_id == message.from_user.id:
        await message.answer("❌ Нельзя добавить самого себя.", reply_markup=get_admins_keyboard())
        await state.clear()
        return
    added = await db.add_admin(user_id)
    if added:
        await message.answer(f"✅ Администратор <code>{user_id}</code> добавлен.",
                             parse_mode="HTML", reply_markup=get_admins_keyboard())
    else:
        await message.answer(f"ℹ️ <code>{user_id}</code> уже администратор.",
                             parse_mode="HTML", reply_markup=get_admins_keyboard())
    await state.clear()


@admin_router.message(F.text == "➖ Удалить админа")
async def remove_admin_start(message: Message, state: FSMContext) -> None:
    admins = await db.get_admins()
    if len(admins) <= 1:
        await message.answer("❌ Нельзя удалить последнего администратора.", reply_markup=get_admins_keyboard())
        return
    lines = ["➖ <b>Удалить администратора</b>\n"]
    for uid in admins:
        marker = " (вы)" if uid == message.from_user.id else ""
        lines.append(f"  • <code>{uid}</code>{marker}")
    lines.append("\nВведите ID для удаления:")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_back_keyboard())
    await state.set_state(States.waiting_for_remove_admin_id)


@admin_router.message(States.waiting_for_remove_admin_id)
async def remove_admin_id(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ ID должен быть числом:", reply_markup=get_back_keyboard())
        return
    user_id = int(text)
    if user_id == message.from_user.id:
        await message.answer("❌ Нельзя удалить самого себя.", reply_markup=get_admins_keyboard())
        await state.clear()
        return
    admins = await db.get_admins()
    if len(admins) <= 1:
        await message.answer("❌ Нельзя удалить последнего администратора.", reply_markup=get_admins_keyboard())
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
