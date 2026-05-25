import asyncio
import os
from pyrogram import Client
from pyrogram.errors import (
    FloodWait,
    UserDeactivated,
    AuthKeyUnregistered,
    PhoneNumberBanned,
    PeerIdInvalid,
)
import database as db
from config import SESSIONS_DIR


_clients: dict[str, Client] = {}


def _session_path(session_name: str) -> str:
    return os.path.join(SESSIONS_DIR, session_name)


async def get_client(phone: str, api_id: int, api_hash: str) -> Client:
    if phone in _clients and _clients[phone].is_connected:
        return _clients[phone]

    accounts = await db.get_all_accounts()
    account = next((a for a in accounts if a["phone"] == phone), None)
    if not account:
        raise ValueError(f"Аккаунт {phone} не найден в БД")

    session_name = account["session_name"]
    client = Client(
        name=_session_path(session_name),
        api_id=api_id,
        api_hash=api_hash,
        no_updates=True,
    )
    await client.start()
    _clients[phone] = client
    return client


async def create_temp_client(api_id: int, api_hash: str, session_name: str) -> Client:
    client = Client(
        name=_session_path(session_name),
        api_id=api_id,
        api_hash=api_hash,
        no_updates=True,
    )
    return client


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
    for phone, client in _clients.items():
        try:
            if client.is_connected:
                await client.stop()
        except Exception:
            pass
    _clients.clear()
