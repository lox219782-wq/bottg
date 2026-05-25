import asyncio
import logging
from pyrogram import Client, raw
from pyrogram.errors import (
    FloodWait,
    UserDeactivated,
    AuthKeyUnregistered,
    PhoneNumberBanned,
    PeerIdInvalid,
    UserPrivacyRestricted,
)
import database as db

logger = logging.getLogger(__name__)
_clients: dict[str, Client] = {}


async def get_client(phone: str, api_id: int, api_hash: str) -> Client:
    """Возвращает активный клиент. Если нет — создаёт из session_string в БД."""
    if phone in _clients and _clients[phone].is_connected:
        return _clients[phone]

    accounts = await db.get_all_accounts()
    account = next((a for a in accounts if a["phone"] == phone), None)
    if not account:
        raise ValueError(f"Аккаунт {phone} не найден в БД")

    session_string = account.get("session_string", "")
    if not session_string:
        raise ValueError(f"Нет сохранённой сессии для {phone}. Добавьте аккаунт заново.")

    client = Client(
        name=phone,
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_string,
        no_updates=True,
    )
    await client.start()
    _clients[phone] = client
    return client


async def load_all_accounts() -> None:
    """Загружает все активные аккаунты из БД при старте бота."""
    accounts = await db.get_all_accounts()
    loaded = 0
    for account in accounts:
        phone = account["phone"]
        session_string = account.get("session_string", "")
        if not session_string:
            logger.warning("Аккаунт %s без session_string — пропускаем", phone)
            continue
        if phone in _clients and _clients[phone].is_connected:
            continue
        try:
            client = Client(
                name=phone,
                api_id=account["api_id"],
                api_hash=account["api_hash"],
                session_string=session_string,
                no_updates=True,
            )
            await client.start()
            _clients[phone] = client
            loaded += 1
            logger.info("Аккаунт %s загружен", phone)
        except Exception as e:
            logger.warning("Не удалось загрузить аккаунт %s: %s", phone, e)
    logger.info("Загружено аккаунтов: %d / %d", loaded, len(accounts))


async def send_to_phone(
    client: Client,
    sender_phone: str,
    recipient_phone: str,
    text: str,
) -> str:
    """
    Добавляет номер как контакт → отправляет сообщение → удаляет из контактов.
    Возвращает: 'ok', 'no_telegram', 'privacy', 'banned', 'error: ...'
    """
    user_id = None
    try:
        # Шаг 1: добавляем номер в контакты
        result = await client.invoke(
            raw.functions.contacts.ImportContacts(
                contacts=[
                    raw.types.InputPhoneContact(
                        client_id=0,
                        phone=recipient_phone,
                        first_name="Contact",
                        last_name="",
                    )
                ]
            )
        )

        if not result.users:
            # Номер не в Telegram
            return "no_telegram"

        user = result.users[0]
        user_id = user.id

        # Шаг 2: отправляем сообщение
        await client.send_message(user_id, text)
        await db.log_mailing(sender_phone, recipient_phone, "ok")
        await db.increment_sent(sender_phone)
        return "ok"

    except FloodWait as e:
        wait = e.value + 3
        logger.warning("FloodWait %d сек для %s", wait, sender_phone)
        await asyncio.sleep(wait)
        # Повторная попытка после ожидания
        return await send_to_phone(client, sender_phone, recipient_phone, text)

    except UserPrivacyRestricted:
        await db.log_mailing(sender_phone, recipient_phone, "privacy")
        return "privacy"

    except (PeerIdInvalid, ValueError):
        await db.log_mailing(sender_phone, recipient_phone, "invalid")
        return "invalid"

    except (UserDeactivated, AuthKeyUnregistered, PhoneNumberBanned):
        await db.deactivate_account(sender_phone)
        await db.log_mailing(sender_phone, recipient_phone, "account_banned")
        return "banned"

    except Exception as e:
        err = str(e)
        await db.log_mailing(sender_phone, recipient_phone, f"error: {err}")
        return f"error: {err}"

    finally:
        # Шаг 3: удаляем из контактов в любом случае
        if user_id:
            try:
                await client.invoke(
                    raw.functions.contacts.DeleteContacts(
                        id=[raw.types.InputUser(
                            user_id=user_id,
                            access_hash=user.access_hash,
                        )]
                    )
                )
            except Exception:
                pass


async def disconnect_all() -> None:
    for phone, client in list(_clients.items()):
        try:
            if client.is_connected:
                await client.stop()
        except Exception:
            pass
    _clients.clear()
