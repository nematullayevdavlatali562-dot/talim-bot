import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# AI Kutubxonalari
import google.generativeai as genai
from openai import OpenAI

# Token va API kalitlar
BOT_TOKEN = "8786713515:AAGnN4qNudzmaEv5EGkd2SBsmf9OhPBO7u4
GEMINI_API_KEY = "AQ.Ab8RN6IKtpvUlEoFSaYyf0K9v6KGOjKrcT38geDNewND1DIMlA"
OPENAI_API_KEY = "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"

# Gemini sozlamasi (Nazorat ishi va Slayd uchun)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# OpenAI (ChatGPT) sozlamasi (Referat / Mustaqil ish uchun)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

dp = Dispatcher()

# Bot holatlari (FSM - State Management)
class BotStates(StatesGroup):
    nazorat = State()
    slayd = State()
    referat = State()

# Doimiy pastdagi menyu tugmalari
main_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 Nazorat ishi"), KeyboardButton(text="📊 Slayd (Gamma)")],
        [KeyboardButton(text="📚 Referat / Mustaqil ish"), KeyboardButton(text="🛑 To'xtatish")]
    ],
    resize_keyboard=True
)

# /start buyrug'i
@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"Assalom alaykum, {html.bold(message.from_user.full_name)}!\n"
        "Kerakli bo'limni pastdagi tugmalardan tanlang:",
        reply_markup=main_menu_keyboard
    )

# 🛑 To'xtatish / Stop buyrug'i
@dp.message(F.text == "🛑 To'xtatish")
@dp.message(Command("stop"))
async def stop_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Jarayon to'xtatildi. Asosiy menyudasiz.", reply_markup=main_menu_keyboard)

# 1. Nazorat ishi bo'limi (Gemini)
@dp.message(F.text == "📝 Nazorat ishi")
async def nazorat_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.nazorat)
    await message.answer("📝 Nazorat ishi savolini yoki shartini yuboring. Gemini yordamida qadam-baqadam yechib beraman.")

# 2. Slayd bo'limi (Gamma uslubida tuzilma)
@dp.message(F.text == "📊 Slayd (Gamma)")
async def slayd_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.slayd)
    await message.answer("📊 Slayd uchun mavzu yuboring. Gamma.app orqali taqdimot qilish uchun har bir slaydning sarlavhasi va asosiy matni tuzib beraman.")

# 3. Referat / Mustaqil ish bo'limi (ChatGPT)
@dp.message(F.text == "📚 Referat / Mustaqil ish")
async def referat_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.referat)
    await message.answer("📚 Referat yoki mustaqil ish mavzusini yuboring. ChatGPT yordamida keng qamrovli matn tayyorlab beraman.")

# --- AI BILAN ISHLASH JARAYoni ---

@dp.message(BotStates.nazorat, F.text)
async def process_nazorat(message: Message) -> None:
    try:
        prompt = f"Sen kuchli o'qituvchisan. Ushbu nazorat ishi savoliga mukammal va tushunarli javob yozib ber: {message.text}"
        response = gemini_model.generate_content(prompt)
        await message.answer(response.text)
    except Exception as e:
        await message.answer(f"Xatolik yuz berdi: {e}")

@dp.message(BotStates.slayd, F.text)
async def process_slayd(message: Message) -> None:
    try:
        prompt = f"Gamma.app orqali slayd qilish uchun quyidagi mavzu bo'yicha 7-10 ta slayddan iborat tuzilma (har bir slaydning sarlavhasi va asosiy matni) tuzib ber: {message.text}"
        response = gemini_model.generate_content(prompt)
        await message.answer(response.text)
    except Exception as e:
        await message.answer(f"Xatolik yuz berdi: {e}")

@dp.message(BotStates.referat, F.text)
async def process_referat(message: Message) -> None:
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen akademik referat va mustaqil ishlar yozuvchi professional yordamchisan."},
                {"role": "user", "content": f"Quyidagi mavzu bo'yicha kirish, asosiy qism, reja va xulosa qilib mustaqil ish yozib ber: {message.text}"}
            ]
        )
        answer = completion.choices[0].message.content
        await message.answer(answer)
    except Exception as e:
        await message.answer(f"ChatGPT'da xatolik yuz berdi: {e}")

# Agar menyudan tashqari matn yozilsa
@dp.message()
async def default_handler(message: Message) -> None:
    await message.answer("Iltimos, pastdagi tugmalardan birini tanlang.", reply_markup=main_menu_keyboard)

async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
