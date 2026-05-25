import asyncio
from pyrogram import Client, raw
from pyrogram.errors import (
    FloodWait,
    UserDeactivated,
    AuthKeyUnregistered,
    PhoneNumberBanned,
    PeerIdInvalid,
)
import database as db


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
        raise ValueError(f"Нет сохранённой сессии для аккаунта {phone}. Добавьте аккаунт заново.")

    client = Client(
        name=phone,
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_string,
        in_memory=True,
        no_updates=True,
    )
    await client.start()
    _clients[phone] = client
    return client


async def load_all_accounts() -> None:
    """Загружает все активные аккаунты из БД при старте бота."""
    accounts = await db.get_all_accounts()
    for account in accounts:
        phone = account["phone"]
        session_string = account.get("session_string", "")
        if not session_string:
            continue
        if phone in _clients and _clients[phone].is_connected:
            continue
        try:
            client = Client(
                name=phone,
                api_id=account["api_id"],
                api_hash=account["api_hash"],
                session_string=session_string,
                in_memory=True,
                no_updates=True,
            )
            await client.start()
            _clients[phone] = client
        except Exception:
            pass


async def check_contacts(
    phones: list[str],
    progress_callback=None,
) -> dict:
    """
    Проверяет список номеров телефонов — есть ли у них Telegram.
    Использует import_contacts через один из активных аккаунтов.
    """
    accounts = await db.get_all_accounts()
    if not accounts:
        return {"found": [], "not_found": len(phones), "errors": 0,
                "error": "Нет активных аккаунтов для проверки"}

    account = accounts[0]
    client = await get_client(account["phone"], account["api_id"], account["api_hash"])

    found = []
    not_found = 0
    errors = 0
    batch_size = 100

    for i in range(0, len(phones), batch_size):
        batch = phones[i:i + batch_size]

        try:
            result = await client.invoke(
                raw.functions.contacts.ImportContacts(
                    contacts=[
                        raw.types.InputPhoneContact(
                            client_id=j,
                            phone=phone.strip(),
                            first_name="x",
                            last_name=""
                        )
                        for j, phone in enumerate(batch)
                    ]
                )
            )

            batch_found = []
            for user in result.users:
                phone_num = getattr(user, "phone", None)
                if not phone_num:
                    for imp in result.imported:
                        if imp.user_id == user.id:
                            phone_num = batch[imp.client_id]
                            break
                batch_found.append({
                    "phone": f"+{phone_num}" if phone_num and not str(phone_num).startswith("+") else phone_num or "",
                    "username": getattr(user, "username", None),
                    "first_name": getattr(user, "first_name", "") or "",
                })

            found.extend(batch_found)
            not_found += len(batch) - len(result.users)

            if result.users:
                try:
                    await client.invoke(
                        raw.functions.contacts.DeleteContacts(
                            id=[raw.types.InputUser(user_id=u.id, access_hash=u.access_hash)
                                for u in result.users]
                        )
                    )
                except Exception:
                    pass

        except FloodWait as e:
            await asyncio.sleep(e.value + 5)
            errors += len(batch)
        except Exception:
            errors += len(batch)

        if progress_callback:
            done = min(i + batch_size, len(phones))
            await progress_callback(done, len(phones), len(found))

        await asyncio.sleep(2)

    return {"found": found, "not_found": not_found, "errors": errors}


async def send_message_to_contact(
    client: Client,
    phone: str,
    contact: str,
    text: str,
) -> str:
    try:
        await client.send_message(contact, text)
        await db.log_mailing(phone, contact, "ok")
        await db.increment_sent(phone)
        return "ok"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await send_message_to_contact(client, phone, contact, text)
    except (PeerIdInvalid, ValueError):
        await db.log_mailing(phone, contact, "invalid")
        return "invalid"
    except (UserDeactivated, AuthKeyUnregistered, PhoneNumberBanned):
        await db.deactivate_account(phone)
        await db.log_mailing(phone, contact, "account_banned")
        return "account_banned"
    except Exception as e:
        await db.log_mailing(phone, contact, f"error: {e}")
        return f"error: {e}"


async def run_mailing(
    text: str,
    contacts: list[str],
    progress_callback=None,
) -> dict:
    accounts = await db.get_all_accounts()
    if not accounts:
        return {"ok": 0, "fail": 0, "error": "Нет активных аккаунтов"}

    results = {"ok": 0, "fail": 0}
    acc_index = 0

    for i, contact in enumerate(contacts):
        contact = contact.strip()
        if not contact:
            continue

        account = accounts[acc_index % len(accounts)]
        acc_index += 1

        try:
            client = await get_client(
                account["phone"], account["api_id"], account["api_hash"]
            )
            status = await send_message_to_contact(
                client, account["phone"], contact, text
            )
            if status == "ok":
                results["ok"] += 1
            else:
                results["fail"] += 1
        except Exception:
            results["fail"] += 1

        if progress_callback and (i + 1) % 10 == 0:
            await progress_callback(i + 1, len(contacts), results)

        await asyncio.sleep(0.5)

    return results


async def disconnect_all() -> None:
    for phone, client in list(_clients.items()):
        try:
            if client.is_connected:
                await client.stop()
        except Exception:
            pass
    _clients.clear()
