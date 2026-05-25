import asyncio
from pyrogram import Client
import database as db

async def start_mailing(phone, session_string, text, numbers, interval):
    api_id, api_hash = db.get_api_credentials()
    app = Client(f"session_{phone}", api_id=int(api_id), api_hash=api_hash, session_string=session_string)
    
    async with app:
        for number in numbers:
            try:
                await app.import_contacts([{"phone_number": number, "first_name": "User"}])
                await app.send_message(number, text)
                await asyncio.sleep(interval)
            except Exception as e:
                print(f"Ошибка {phone}: {e}")
