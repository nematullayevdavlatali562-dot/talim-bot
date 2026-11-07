import asyncio
import json
import logging
import os
import sys
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiohttp import web
import aiohttp

# --- TOKEN VA KALITLAR ---
TELEGRAM_BOT_TOKEN = "8786713515:AAGnN4qNudzmaEv5EGkd2SBsmf9OhPBO7u4"
GEMINI_AUTH_TOKEN = "AQ.Ab8RN6JwfmjzvYAQF14cHsTxM9MTGUJhULGdOTOtKN41HfFzpQ"  # O'zingizning AQ. bilan boshlanadigan tokeningiz
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

SYSTEM_INSTRUCTION = (
    "Siz maktab o'quvchilari va talabalarga ta'lim jarayonida, uy vazifalarini bajarishda, "
    "formula va qonuniyatlarni tushuntirishda yordam beruvchi aqlli sun'iy intellekt ustozisiz. "
    "Javoblaringizni doimo tushunarli, bosqichma-bosqich va o'zbek tilida bering."
)

async def call_gemini_api(prompt_text: str, image_bytes: bytes = None):
    """Google Cloud Auth Token (AQ.) yordamida Gemini REST API ga so'rov yuborish"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    
    headers = {
        "Authorization": f"Bearer {GEMINI_AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Qismlarni tayyorlash
    parts = [{"text": prompt_text}]
    
    if image_bytes:
        import base64
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64_image
            }
        })
        
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": parts
            }
        ],
        "systemInstruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "generationConfig": {
            "temperature": 0.7
        }
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            res_json = await response.json()
            if response.status != 200:
                raise Exception(f"API xatosi ({response.status}): {res_json}")
            
            # Javobni ajratib olish
            try:
                return res_json["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return "Kutilmagan formatdagi javob keldi."

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer(
        "Assalomu alaykum! 📚\n\n"
        "Men sizning Gemini AI asosidagi shaxsiy ta'lim yordamchingizman. Menga quyidagilarni yuborishingiz mumkin:\n"
        "• Matn ko'rinishidagi savollar va masalalar\n"
        "• Uy vazifasi tushirilgan **rasmlar** (kitob yoki daftar fotosi)\n\n"
        "Qani, qanday savolingiz bor?"
    )

@dp.message(F.text)
async def handle_text_message(message: types.Message):
    user_text = message.text
    processing_msg = await message.answer("⏳ Savolingiz tahlil qilinmoqda...")

    try:
        answer_text = await call_gemini_api(user_text)
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        await message.answer(answer_text)
    except Exception as e:
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        await message.answer(f"❌ Xatolik yuz berdi: {str(e)}")

@dp.message(F.photo)
async def handle_photo_message(message: types.Message):
    processing_msg = await message.answer("🖼 Rasm tahlil qilinmoqda, biroz kuting...")

    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(file_info.file_path)
        image_bytes = photo_bytes.read()
        
        caption_text = message.caption if message.caption else "Ushbu rasmdagi masala yoki topshiriqni batafsil yechib tushuntirib bering."

        answer_text = await call_gemini_api(caption_text, image_bytes=image_bytes)

        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        await message.answer(answer_text)
    except Exception as e:
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        await message.answer(f"❌ Rasmni o'qishda xatolik yuz berdi: {str(e)}")

async def handle_ping(request):
    return web.Response(text="Bot ishlayapti!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print("🤖 Gemini Ta'lim boti (Auth Token rejimida) ishga tushdi...")
    
    asyncio.create_task(web_server())
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
