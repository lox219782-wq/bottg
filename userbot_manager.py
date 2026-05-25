import asyncio
from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError
from config import API_ID, API_HASH
import database as db

async def check_single_phone(app: Client, phone_to_check: str):
    """Проверяет один номер через запущенного юзербота"""
    try:
        # Пытаемся импортировать контакт в Telegram для проверки
        contact = await app.import_contacts([{"phone_number": phone_to_check}])
        
        if contact.users:
            user = contact.users[0]
            db.update_phone_status(
                phone=phone_to_check, 
                status=1, 
                tg_id=user.id, 
                username=user.username
            )
            # Сразу удаляем из контактов, чтобы не засорять аккаунт
            await app.delete_contacts([user.id])
            print(f"[Чекер] Номер {phone_to_check} -> ЕСТЬ в ТГ (ID: {user.id})")
        else:
            db.update_phone_status(phone=phone_to_check, status=2)
            print(f"[Чекер] Номер {phone_to_check} -> НЕТ в ТГ")
            
    except FloodWait as e:
        print(f"[Предупреждение] Флуд-контроль! Нужно подождать {e.value} сек.")
        await asyncio.sleep(e.value)
    except RPCError as e:
        print(f"[Ошибка RPC] Не удалось проверить {phone_to_check}: {e}")
    except Exception as e:
        print(f"[Ошибка] Системная ошибка при проверке {phone_to_check}: {e}")

async def start_mass_checking():
    """Запускает проверку базы номеров через первый активный юзербот"""
    active_bots = db.get_all_userbots()
    if not active_bots:
        print("[Чекер] Нет активных юзерботов для проверки.")
        return False
        
    phones_to_check = db.get_unverified_phones(limit=50)
    if not phones_to_check:
        print("[Чекер] Нет неотвеченных номеров в базе данных.")
        return False
        
    # Берем первый доступный аккаунт
    phone, session_string = active_bots[0]
    
    # Создаем клиент Pyrogram из сохраненной строки сессии
    app = Client(f"session_{phone}", api_id=int(API_ID), api_hash=API_HASH, session_string=session_string)
    
    print(f"[Чекер] Запуск проверки через аккаунт {phone}...")
    async with app:
        for p in phones_to_check:
            await check_single_phone(app, p)
            await asyncio.sleep(2) # Пауза между номерами для защиты от бана
            
    return True
