admin_router = Router()
BACK = "🔙 Назад"
class IsAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
-8
+54
    waiting_for_check_file = State()
# ──────────────────────────────────────────────────────────────
# КЛАВИАТУРЫ
# ──────────────────────────────────────────────────────────────
def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📱 Добавить аккаунт (UserBot)")],
        [KeyboardButton(text="🚀 Запустить рекламу"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="⚙️ Настройка API"), KeyboardButton(text="🔍 Проверить базу")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
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
        "👋 Добро пожаловать в панель управления UserBot-рассылкой!",
        "👋 Добро пожаловать в панель управления UserBot-рассылкой!\n\n"
        "Выберите действие из меню ниже:",
        reply_markup=get_main_keyboard(),
    )
-7
+18
    settings = await db.get_api_settings()
    if not settings:
        await message.answer(
            "⚠️ Сначала настройте API через кнопку ⚙️ Настройка API"
        )
        return
    await message.answer("Введите номер телефона аккаунта (формат: +79001234567):")
            "⚠️ Сначала настройте API через кнопку <b>⚙️ Настройка API</b>\n"
            "Вам нужны API_ID и API_HASH с сайта my.telegram.org",
            parse_mode="HTML",
        )
        return
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
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("❌ Некорректный номер. Введите в формате +79001234567:")
    if not phone.startswith("+") or not phone[1:].isdigit() or len(phone) < 10:
        await message.answer(
            "❌ Некорректный номер.\nВведите в формате <code>+79001234567</code>:",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        return
    settings = await db.get_api_settings()
    if not settings:
        await message.answer("⚠️ API не настроен. Воспользуйтесь ⚙️ Настройка API")
        await message.answer("⚠️ API не настроен.", reply_markup=get_main_keyboard())
        await state.clear()
        return
-1
+3
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
-5
+11
            api_hash=api_hash,
            phone_code_hash=sent.phone_code_hash,
        )
        await message.answer("📨 Код отправлен. Введите код из Telegram (без пробелов):")
        await state.update_data(_client_ref=id(client))
        client._phone_temp = phone
        ub_mgr._clients[f"__temp_{phone}"] = client
        await message.answer(
            "📨 Код отправлен в Telegram.\n\n"
            "Введите код <b>без пробелов</b> (например: <code>12345</code>):",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(MainStates.waiting_for_code)
    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка при отправке кода: {e}")
        await message.answer(
            f"❌ Ошибка при отправке кода: <code>{e}</code>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
-2
+2
    api_hash: str = data["api_hash"]
    session_name: str = data["session_name"]
    client: Client = ub_mgr._clients.get(f"__temp_{phone}")
    client: Client | None = ub_mgr._clients.get(f"__temp_{phone}")
    if not client:
        await message.answer("❌ Сессия истекла. Начните заново.")
        await message.answer("❌ Сессия истекла. Начните заново.", reply_markup=get_main_keyboard())
        await state.clear()
        return
-9
+27
        await client.sign_in(phone, phone_code_hash, code)
        await db.add_account(phone, session_name, api_id, api_hash)
        ub_mgr._clients[phone] = client
        del ub_mgr._clients[f"__temp_{phone}"]
        await message.answer(
            f"✅ Аккаунт {phone} успешно добавлен!",
        ub_mgr._clients.pop(f"__temp_{phone}", None)
        await message.answer(
            f"✅ Аккаунт <code>{phone}</code> успешно добавлен!",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
    except SessionPasswordNeeded:
        await message.answer("🔐 Требуется пароль двухфакторной аутентификации. Введите пароль:")
        await message.answer(
            "🔐 На аккаунте включена двухфакторная аутентификация.\n\nВведите пароль 2FA:",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(MainStates.waiting_for_2fa)
    except PhoneCodeExpired:
        await client.disconnect()
        del ub_mgr._clients[f"__temp_{phone}"]
        await message.answer("❌ Код истёк. Попробуйте снова.")
        ub_mgr._clients.pop(f"__temp_{phone}", None)
        try:
            await client.disconnect()
        except Exception:
            pass
        await message.answer(
            "❌ Код истёк. Нажмите <b>📱 Добавить аккаунт</b> и попробуйте снова.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
    except PhoneCodeInvalid:
        await message.answer("❌ Неверный код. Введите ещё раз:")
        await message.answer(
            "❌ Неверный код. Проверьте и введите ещё раз:",
            reply_markup=get_back_keyboard(),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка входа: {e}")
        await message.answer(
            f"❌ Ошибка: <code>{e}</code>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
-2
+2
    api_hash: str = data["api_hash"]
    session_name: str = data["session_name"]
    client: Client = ub_mgr._clients.get(f"__temp_{phone}")
    client: Client | None = ub_mgr._clients.get(f"__temp_{phone}")
    if not client:
        await message.answer("❌ Сессия истекла. Начните заново.")
        await message.answer("❌ Сессия истекла. Начните заново.", reply_markup=get_main_keyboard())
        await state.clear()
        return
-4
+9
        await client.check_password(password)
        await db.add_account(phone, session_name, api_id, api_hash)
        ub_mgr._clients[phone] = client
        del ub_mgr._clients[f"__temp_{phone}"]
        await message.answer(
            f"✅ Аккаунт {phone} добавлен (2FA прошёл успешно)!",
        ub_mgr._clients.pop(f"__temp_{phone}", None)
        await message.answer(
            f"✅ Аккаунт <code>{phone}</code> добавлен (2FA прошёл успешно)!",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Неверный пароль 2FA: {e}")
        await message.answer(
            f"❌ Неверный пароль 2FA: <code>{e}</code>\n\nПопробуйте ещё раз:",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
# ──────────────────────────────────────────────────────────────
-5
+21
async def mailing_start(message: Message, state: FSMContext) -> None:
    accounts = await db.get_all_accounts()
    if not accounts:
        await message.answer("⚠️ Нет активных аккаунтов. Добавьте хотя бы один через 📱 Добавить аккаунт.")
        return
    await message.answer("✏️ Введите текст сообщения для рассылки:")
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
        await message.answer("❌ Пожалуйста, введите текстовое сообщение.")
        await message.answer(
            "❌ Пожалуйста, введите текстовое сообщение:",
            reply_markup=get_back_keyboard(),
        )
        return
    await state.update_data(mailing_text=message.text)
    await message.answer(
        "📁 Отправьте .txt файл со списком контактов (один номер/username на строку):"
        f"✅ Текст сохранён.\n\n"
        f"Шаг 2/2: Отправьте <b>.txt файл</b> со списком контактов\n"
        f"(один номер или @username на строку):",
        parse_mode="HTML",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(MainStates.waiting_for_mailing_file)
-1
+5
async def mailing_file(message: Message, state: FSMContext) -> None:
    doc: Document = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Пожалуйста, отправьте файл в формате .txt")
        await message.answer(
            "❌ Нужен файл в формате <b>.txt</b>. Попробуйте ещё раз:",
            parse_mode="HTML",
            reply_markup=get_back_keyboard(),
        )
        return
    os.makedirs(UPLOADS_DIR, exist_ok=True)
-1
+5
        contacts = [line.strip() for line in f if line.strip()]
    if not contacts:
        await message.answer("❌ Файл пустой или не содержит контактов.")
        await message.answer(
            "❌ Файл пустой или не содержит контактов.",
            reply_markup=get_main_keyboard(),
    ...
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
-1
+1
[truncated]
[truncated]
