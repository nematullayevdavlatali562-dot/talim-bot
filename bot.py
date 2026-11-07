import asyncio
import base64
import logging
import sys
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from anthropic import Anthropic

# --- SOZLAMALAR ---
# Tokenlaringizni shu yerga yozing
TELEGRAM_BOT_TOKEN = "8786713515:AAGnN4qNudzmaEv5EGkd2SBsmf9OhPBO7u4"
CLAUDE_API_KEY = "AQ.Ab8RN6JCnhISnIJDz0edZzxhx1jTykP8BHMoMsks4Q--mTAQ2A"

# Bot va Claude mijozini yaratish
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
anthropic_client = Anthropic(api_key=CLAUDE_API_KEY)

# Claude uchun o'quv yordamchisi roli
SYSTEM_PROMPT = (
    "Siz maktab o'quvchilari va talabalarga ta'lim jarayonida, uy vazifalarini bajarishda, "
    "formula va qonuniyatlarni tushuntirishda yordam beruvchi aqlli sun'iy intellekt ustozisiz. "
    "Javoblaringizni doimo tushunarli, bosqichma-bosqich va o'zbek tilida bering."
)

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Bot ishga tushganda yoki /start bosilganda ishlaydi"""
    welcome_text = (
        "Assalomu alaykum! 📚\n\n"
        "Men sizning shaxsiy ta'lim yordamchingizman. Menga quyidagilarni yuborishingiz mumkin:\n"
        "• Matn ko'rinishidagi savollar va masalalar\n"
        "• Uy vazifasi tushirilgan **rasmlar** (kitob yoki daftar fotosi)\n\n"
        "Qani, qanday savolingiz bor?"
    )
    await message.answer(welcome_text)


@dp.message(F.text)
async def handle_text_message(message: types.Message):
    """Foydalanuvchidan matn kelganda ishlaydi"""
    user_text = message.text
    
    # Jarayon haqida xabar berish
    processing_msg = await message.answer("⏳ Savolingiz tahlil qilinmoqda...")

    try:
        # Claude API orqali javob olish
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_text}
            ]
        )
        
        answer_text = response.content[0].text
        
        # Vaqtinchalik xabarni o'chirib, javobni yuborish
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        await message.answer(answer_text)

    except Exception as e:
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        await message.answer(f"❌ Xatolik yuz berdi: {str(e)}")


@dp.message(F.photo)
async def handle_photo_message(message: types.Message):
    """Foydalanuvchidan rasm (uy vazifasi fotosi) kelganda ishlaydi"""
    processing_msg = await message.answer("🖼 Rasm tahlil qilinmoqda, biroz kuting...")

    try:
        # Eng sifatli rasmni olish
        photo = message.photo[-1]
        
        # Telegram serveridan rasmni yuklab olish
        file_info = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(file_info.file_path)
        
        # Rasmni Claude talab qiladigan Base64 formatiga o'tkazish
        base64_image = base64.b64encode(photo_bytes.read()).decode("utf-8")
        
        # Agar foydalanuvchi rasm bilan birga izoh yozgan bo'lsa o'shani olamiz
        caption_text = message.caption if message.caption else "Ushbu rasmdagi masala yoki topshiriqni batafsil yechib tushuntirib bering."

        # Claude APIga multimodal (matn + rasm) so'rov yuborish
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": caption_text
                        }
                    ],
                }
            ],
        )
        
        answer_text = response.content[0].text
        
        # Vaqtinchalik xabarni o'chirib, natijani yuborish
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        await message.answer(answer_text)

    except Exception as e:
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        await message.answer(f"❌ Rasmni o'qishda xatolik yuz berdi: {str(e)}")


async def main():
    """Botni ishga tushiruvchi asosiy funksiya"""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print("🤖 Ta'lim boti muvaffaqiyatli ishga tushdi...")
    
    # Eski xabarlarni tozalab, yangilarini qabul qilishni boshlash
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
