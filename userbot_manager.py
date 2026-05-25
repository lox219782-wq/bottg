import asyncio
from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError
import database as db

# --- ЛОГИКА ЧЕКЕРА ---
async def check_single_phone(app: Client, phone_to_check: str):
    try:
        contact = await app.import_contacts([{"phone_number": phone_to_check}])
        if contact.users:
            user = contact.users[0]
            db.update_phone_status(phone=phone_to_check, status=1, tg_id=user.id, username=user.username)
            await app.delete_contacts([user.id])
            print(f"[Чекер] Номер {phone_to_check} -> ЕСТЬ в ТГ")
        else:
            db.update_phone_status(phone=phone_to_check, status=2)
            print(f"[Чекер] Номер {phone_to_check} -> НЕТ в ТГ")
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        print(f"Ошибка чекера для {phone_to_check}: {e}")

async def start_mass_checking():
    active_bots = db.get_all_userbots()
    if not active_bots: return False
        
    phones_to_check = db.get_unverified_phones(limit=50)
    if not phones_to_check: return False
        
    phone, session_string = active_bots[0]
    api_id, api_hash = db.get_api_credentials()
    
    app = Client(f"session_{phone}", api_id=int(api_id), api_hash=api_hash, session_string=session_string)
    
    async with app:
        for p in phones_to_check:
            await check_single_phone(app, p)
            await asyncio.sleep(2)
    return True

# --- ЛОГИКА РАССЫЛКИ (НОВАЯ) ---
async def start_mailing(phone, session_string, text, numbers, interval):
    """
    Массовая рассылка от лица конкретного аккаунта
    """
    api_id, api_hash = db.get_api_credentials()
    app = Client(f"session_{phone}", api_id=int(api_id), api_hash=api_hash, session_string=session_string)
    
    async with app:
        for number in numbers:
            number = number.strip()
            if not number: continue
            
            try:
                # 1. Добавляем в контакты (снижает риск бана)
                await app.import_contacts([{"phone_number": number, "first_name": "User"}])
                
                # 2. Отправляем сообщение
                await app.send_message(number, text)
                print(f"[Рассылка] Аккаунт {phone} отправил сообщение на {number}")
                
                # 3. Ждем интервал
                await asyncio.sleep(interval)
                
            except FloodWait as e:
                print(f"[FloodWait] Аккаунт {phone} в блоке на {e.value} секунд")
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"[Ошибка] Аккаунт {phone} не смог написать {number}: {e}")
