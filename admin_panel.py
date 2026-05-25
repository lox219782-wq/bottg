import asyncio
import inspect
import logging
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
from config import ADMIN_IDS, UPLOADS_DIR

logger = logging.getLogger(__name__)
admin_router = Router()

BACK = "🔙 Назад"
STOP_BTN = "🛑 Остановить рассылку"

_mailing_task: asyncio.Task | None = None


class IsAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in ADMIN_IDS


admin_router.message.filter(IsAdmin())


class States(StatesGroup):
    # Добавление аккаунта
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()
    # Настройка API
    waiting_for_api_id = State()
    waiting_for_api_hash = State()
    # Рассылка
    waiting_for_mailing_file = State()
    waiting_for_mailing_text = State()
    waiting_for_mailing_interval = State()


# ──────────────────────────────────────────────────────────────
# КЛАВИАТУРЫ
# ──────────────────────────────────────────────────────────────

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Аккаунты"), KeyboardButton(text="📱 Добавить аккаунт")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Настройка API")],
            [KeyboardButton(text="🚀 Запустить рассылку")],
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


# ──────────────────────────────────────────────────────────────
# НАЗАД — любое состояние
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
    await message.answer(
        "👋 Добро пожаловать!\n\nВыберите действие:",
        reply_markup=get_main_keyboard(),
    )


# ──────────────────────────────────────────────────────────────
# 1. АККАУНТЫ
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "👥 Аккаунты")
async def show_accounts(message: Message) -> None:
    accounts = await db.get_all_accounts()
    if not accounts:
        await message.answer(
            "👥 <b>Аккаунты</b>\n\n"
            "❌ Нет добавленных аккаунтов.\n\n"
            "Нажмите <b>📱 Добавить аккаунт</b>.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
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
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        return
    await message.answer(
        "📱 <b>Добавление аккаунта</b>\n\n"
        "Введите номер телефона в формате <code>+79001234567</code>:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_phone)


@admin_router.message(States.waiting_for_phone)
async def add_acc_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip() if message.text else ""
    if not phone.startswith("+") or not phone[1:].isdigit() or len(phone) < 10:
        await message.answer(
            "❌ Некорректный номер. Формат: <code>+79001234567</code>",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
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
            "📨 Код отправлен в Telegram.\n\n"
            "Введите код без пробелов (например: <code>12345</code>):",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(States.waiting_for_code)
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        await message.answer(
            f"❌ Ошибка: <code>{e}</code>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
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
            await message.answer(
                f"❌ Ошибка: <code>{e}</code>",
                parse_mode="HTML", reply_markup=get_main_keyboard(),
            )
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
        await message.answer(f"❌ Ошибка экспорта сессии: <code>{e}</code>", parse_mode="HTML",
                             reply_markup=get_main_keyboard())
        await state.clear()
        return

    if not session_string:
        await _cleanup_temp(phone)
        await message.answer("❌ Сессия пустая — попробуйте добавить аккаунт заново.",
                             reply_markup=get_main_keyboard())
        await state.clear()
        return

    await db.add_account(phone, session_string, api_id, api_hash)
    ub_mgr._clients[phone] = client
    ub_mgr._clients.pop(f"__temp_{phone}", None)

    await message.answer(
        f"✅ Аккаунт <code>{phone}</code> добавлен!\n"
        f"Сессия сохранена в базу данных.",
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
# 3. РАССЫЛКА
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == "🚀 Запустить рассылку")
async def mailing_start(message: Message, state: FSMContext) -> None:
    global _mailing_task
    if _mailing_task and not _mailing_task.done():
        await message.answer(
            "⚠️ Рассылка уже запущена!\n\nНажмите <b>🛑 Остановить рассылку</b> чтобы её остановить.",
            parse_mode="HTML",
            reply_markup=get_stop_keyboard(),
        )
        return

    accounts = await db.get_all_accounts()
    if not accounts:
        await message.answer(
            "⚠️ Нет активных аккаунтов.\nДобавьте аккаунт через <b>📱 Добавить аккаунт</b>.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        return

    await message.answer(
        "📂 <b>Рассылка — Шаг 1/3</b>\n\n"
        "Отправьте <b>.txt файл</b> со списком номеров телефонов\n"
        "(один номер на строку, формат: +79001234567)",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
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
        raw = [line.strip() for line in f if line.strip()]

    numbers = []
    for n in raw:
        clean = n.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if clean.lstrip("+").isdigit() and len(clean) >= 10:
            numbers.append(clean if clean.startswith("+") else f"+{clean}")

    if not numbers:
        await message.answer("❌ Файл не содержит телефонных номеров.",
                             reply_markup=get_main_keyboard())
        await state.clear()
        return

    await state.update_data(numbers=numbers)
    await message.answer(
        f"✅ Загружено <b>{len(numbers)}</b> номеров.\n\n"
        f"📝 <b>Шаг 2/3:</b> Введите текст сообщения для рассылки:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_mailing_text)


@admin_router.message(States.waiting_for_mailing_file)
async def mailing_file_wrong(message: Message) -> None:
    await message.answer("❌ Ожидается <b>.txt файл</b> — нажмите скрепку и выберите файл.",
                         parse_mode="HTML", reply_markup=get_back_keyboard())


@admin_router.message(States.waiting_for_mailing_text)
async def mailing_got_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("❌ Введите текстовое сообщение:", reply_markup=get_back_keyboard())
        return
    await state.update_data(mailing_text=message.text)
    await message.answer(
        f"✅ Текст сохранён.\n\n"
        f"⏱ <b>Шаг 3/3:</b> Введите интервал между сообщениями в <b>секундах</b>\n"
        f"(например: <code>30</code> — одно сообщение каждые 30 сек)",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_mailing_interval)


@admin_router.message(States.waiting_for_mailing_interval)
async def mailing_got_interval(message: Message, state: FSMContext) -> None:
    global _mailing_task

    text = (message.text or "").strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer(
            "❌ Введите целое число секунд (минимум 1):",
            reply_markup=get_back_keyboard(),
        )
        return

    interval = int(text)
    data = await state.get_data()
    numbers: list[str] = data["numbers"]
    mailing_text: str = data["mailing_text"]
    await state.clear()

    accounts = await db.get_all_accounts()

    status_msg = await message.answer(
        f"🚀 <b>Рассылка запущена!</b>\n\n"
        f"📋 Номеров: <b>{len(numbers)}</b>\n"
        f"⏱ Интервал: <b>{interval} сек</b>\n"
        f"👤 Аккаунтов: <b>{len(accounts)}</b>\n\n"
        f"Прогресс: 0/{len(numbers)}",
        parse_mode="HTML",
        reply_markup=get_stop_keyboard(),
    )

    _mailing_task = asyncio.create_task(
        _run_mailing(
            bot=message.bot,
            chat_id=message.chat.id,
            status_msg=status_msg,
            numbers=numbers,
            text=mailing_text,
            interval=interval,
            accounts=accounts,
        )
    )


async def _run_mailing(
    bot, chat_id: int, status_msg, numbers: list[str],
    text: str, interval: int, accounts: list[dict],
) -> None:
    ok = 0
    fail = 0
    stopped = False
    total = len(numbers)

    for i, phone in enumerate(numbers):
        if _mailing_task and _mailing_task.cancelled():
            stopped = True
            break

        account = accounts[i % len(accounts)]
        try:
            client = await ub_mgr.get_client(
                account["phone"], account["api_id"], account["api_hash"]
            )
            status = await ub_mgr.send_to_phone(client, account["phone"], phone, text)
            if status == "ok":
                ok += 1
            else:
                fail += 1
        except Exception as e:
            logger.warning("Ошибка при отправке на %s: %s", phone, e)
            fail += 1

        # Обновляем статус каждые 5 сообщений или в конце
        if (i + 1) % 5 == 0 or (i + 1) == total:
            try:
                await status_msg.edit_text(
                    f"⏳ <b>Рассылка в процессе...</b>\n\n"
                    f"Прогресс: {i + 1}/{total}\n"
                    f"✅ Успешно: {ok} | ❌ Ошибок: {fail}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        if i < total - 1:
            await asyncio.sleep(interval)

    if stopped:
        result_text = (
            f"🛑 <b>Рассылка остановлена</b>\n\n"
            f"Отправлено: {ok + fail}/{total}\n"
            f"✅ Успешно: {ok} | ❌ Ошибок: {fail}"
        )
    else:
        result_text = (
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"📋 Всего номеров: {total}\n"
            f"✅ Успешно: {ok}\n"
            f"❌ Ошибок: {fail}"
        )

    try:
        await status_msg.edit_text(result_text, parse_mode="HTML")
    except Exception:
        pass

    try:
        await bot.send_message(chat_id, result_text, parse_mode="HTML",
                               reply_markup=ReplyKeyboardMarkup(
                                   keyboard=[[KeyboardButton(text="🚀 Запустить рассылку")]],
                                   resize_keyboard=True,
                               ))
        # Восстанавливаем полное меню
        await bot.send_message(chat_id, "🏠 Главное меню", reply_markup=_main_keyboard())
    except Exception:
        pass


def _main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Аккаунты"), KeyboardButton(text="📱 Добавить аккаунт")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Настройка API")],
            [KeyboardButton(text="🚀 Запустить рассылку")],
        ],
        resize_keyboard=True,
    )


# ──────────────────────────────────────────────────────────────
# СТОП
# ──────────────────────────────────────────────────────────────

@admin_router.message(F.text == STOP_BTN)
async def mailing_stop(message: Message) -> None:
    global _mailing_task
    if _mailing_task and not _mailing_task.done():
        _mailing_task.cancel()
        await message.answer(
            "🛑 Рассылка остановлена.\n\nИтоги появятся через секунду.",
            reply_markup=get_main_keyboard(),
        )
    else:
        await message.answer("ℹ️ Рассылка не запущена.", reply_markup=get_main_keyboard())


# ──────────────────────────────────────────────────────────────
# 4. СТАТИСТИКА
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
            status = "🟢" if acc.get("active", 1) else "🔴"
            lines.append(f"  {status} <code>{acc['phone']}</code> — отправлено: {acc['sent_count']}")
    else:
        lines.append("\n<i>Аккаунты не добавлены</i>")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_main_keyboard())


# ──────────────────────────────────────────────────────────────
# 5. НАСТРОЙКА API
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
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(States.waiting_for_api_id)


@admin_router.message(States.waiting_for_api_id)
async def get_api_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("❌ API_ID — это число. Попробуйте ещё раз:",
                             reply_markup=get_back_keyboard())
        return
    await state.update_data(api_id=int(text))
    await message.answer(
        f"✅ API_ID: <code>{text}</code>\n\nШаг 2/2: Введите <b>API_HASH</b>:",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
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
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )
