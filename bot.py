import asyncio
import io
import logging
import os
import re
import sys
import time

from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiohttp import web
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI

load_dotenv()

# ---------------------------------------------------------------- Sozlamalar
BOT_TOKEN = os.getenv("8786713515:AAGnN4qNudzmaEv5EGkd2SBsmf9OhPBO7u4", "")
GEMINI_API_KEY = os.getenv("AQ.Ab8RN6IKtpvUlEoFSaYyf0K9v6KGOjKrcT38geDNewND1DIMlA", "")
OPENAI_API_KEY = os.getenv("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", "")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

COOLDOWN_SECONDS = 5          # bir foydalanuvchi uchun so'rovlar orasidagi pauza
MAX_INPUT_LENGTH = 3000       # foydalanuvchi matnining maksimal uzunligi
TELEGRAM_LIMIT = 4000         # Telegram xabar limiti 4096, zaxira bilan

if not BOT_TOKEN:
    sys.exit("BOT_TOKEN topilmadi. .env faylini tekshiring.")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

dp = Dispatcher()
last_request: dict[int, float] = {}


# ------------------------------------------------------------------- Holatlar
class BotStates(StatesGroup):
    nazorat = State()
    slayd = State()
    referat = State()
    maktab = State()


# --------------------------------------------------------------------- Menyu
BTN_NAZORAT = "📝 Nazorat ishi"
BTN_SLAYD = "📊 Slayd (Gamma)"
BTN_REFERAT = "📚 Referat / Mustaqil ish"
BTN_MAKTAB = "🏫 Maktab darsliklari (5-11)"
BTN_STOP = "🛑 To'xtatish"

main_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_NAZORAT), KeyboardButton(text=BTN_SLAYD)],
        [KeyboardButton(text=BTN_REFERAT), KeyboardButton(text=BTN_MAKTAB)],
        [KeyboardButton(text=BTN_STOP)],
    ],
    resize_keyboard=True,
)

# ------------------------------------------------------------------- Promptlar
NAZORAT_SYSTEM = (
    "Sen tajribali o'qituvchisan. Nazorat ishi savollariga qadam-baqadam, "
    "aniq va tushunarli javob ber. Foydalanuvchi qaysi tilda yozsa, shu tilda javob ber."
)
SLAYD_SYSTEM = (
    "Sen taqdimotlar bo'yicha mutaxassissan. Gamma.app uchun tayyor tuzilma yarat: "
    "7-10 ta slayd, har birida 'Slayd N: Sarlavha' va 3-5 ta qisqa tezis. "
    "Foydalanuvchi qaysi tilda yozsa, shu tilda javob ber."
)
REFERAT_SYSTEM = (
    "Sen akademik referat va mustaqil ishlar yozuvchi professional yordamchisan. "
    "Tuzilma: Reja, Kirish, Asosiy qism (bo'limlarga bo'lingan), Xulosa, Foydalanilgan adabiyotlar. "
    "Javobni Markdown formatida yoz: bo'lim sarlavhalari uchun '## ', kichik sarlavhalar uchun '### ', "
    "ro'yxatlar uchun '- ' ishlat. Eng birinchi sarlavha ('# ') ishlatma, u alohida qo'yiladi. "
    "Foydalanuvchi qaysi tilda yozsa, shu tilda yoz."
)


# ------------------------------------------------------- Maktab fanlari (5-11 sinf)
# Fan turlari: aniq, tabiiy, til, ijtimoiy.
# Har bir tur uchun qaysi AI ishlatilishi shu yerda belgilanadi ("gemini" yoki "openai").
# Xohlasangiz, shu lug'atni o'zgartirib, boshqa AI tanlashingiz mumkin.
CATEGORY_PROVIDER = {
    "aniq": "gemini",       # matematika, algebra, geometriya, fizika, kimyo, informatika
    "tabiiy": "gemini",     # tabiiy fan, biologiya, geografiya
    "til": "openai",        # ona tili, ingliz tili, rus tili
    "ijtimoiy": "openai",   # adabiyot, tarix, huquq
}

# kalit: (nom, tur, birinchi sinf, oxirgi sinf). Ro'yxatni dasturingizga qarab tahrirlashingiz mumkin.
SUBJECTS: dict[str, tuple[str, str, int, int]] = {
    "mat": ("Matematika", "aniq", 5, 6),
    "alg": ("Algebra", "aniq", 7, 11),
    "geo": ("Geometriya", "aniq", 7, 11),
    "fiz": ("Fizika", "aniq", 7, 11),
    "kim": ("Kimyo", "aniq", 7, 11),
    "inf": ("Informatika", "aniq", 5, 11),
    "tab": ("Tabiiy fan", "tabiiy", 5, 5),
    "bio": ("Biologiya", "tabiiy", 6, 11),
    "gegr": ("Geografiya", "tabiiy", 6, 11),
    "ona": ("Ona tili", "til", 5, 11),
    "ing": ("Ingliz tili", "til", 5, 11),
    "rus": ("Rus tili", "til", 5, 11),
    "adab": ("Adabiyot", "ijtimoiy", 5, 11),
    "tar": ("Tarix", "ijtimoiy", 5, 11),
    "huq": ("Huquq", "ijtimoiy", 9, 11),
}
GRADES = list(range(5, 12))

SCHOOL_BASE = (
    "Sen O'zbekiston umumiy o'rta ta'lim maktablarining tajribali fan o'qituvchisisan. "
    "O'quvchi {grade}-sinfda o'qiydi, fan: {subject}. "
    "Javobni shu sinf o'quvchisi tushunadigan sodda tilda, maktab dasturi doirasida yoz. "
    "Uy vazifasida faqat javobni berib qo'yma: avval qanday yechilishini tushuntir, oxirida javobni alohida ko'rsat. "
    "Foydalanuvchi qaysi tilda yozsa, shu tilda javob ber (odatda o'zbekcha). "
    "Telegramda Markdown ko'rinmaydi, shuning uchun ** # ` kabi belgilarni ishlatma, oddiy matn yoz; "
    "formulalarni oddiy yozuvda ko'rsat (masalan x^2, a/b, √). "
    "Agar savol tanlangan fanga aloqasi bo'lmasa, buni muloyim ayt. "
    "Agar topshiriq to'liq berilmagan yoki aniq darslik sahifasiga tayansa, topshiriq matnini yuborishni so'ra. "
    "Bilmagan ma'lumotni to'qima."
)

SCHOOL_CATEGORY_RULES = {
    "aniq": (
        " Yechimni quyidagi tartibda yoz: Berilgan, Topish kerak, Yechish (qadamlar, kerakli formula yoki qoida), "
        "Javob. Mumkin bo'lsa, natijani tekshirib ko'rsat va o'lchov birliklarini unutma. "
        "Kimyoda reaksiya tenglamalarini tenglashtir, informatikada kodni qisqa izoh bilan yoz."
    ),
    "tabiiy": (
        " Avval tushunchani sodda ta'riflab ber, keyin hayotiy misol keltir, terminlarni izohla, "
        "oxirida 2-3 gaplik qisqa xulosa yoz. Jarayonlarni bosqichma-bosqich tushuntir."
    ),
    "til": (
        " Avval tegishli qoidani qisqa ayt, keyin misollar bilan ko'rsat. Mashq bo'lsa, har bir javobni "
        "nega shunday ekanini izohlab yoz. Ingliz va rus tillarida misollarni o'sha tilda, izohni o'zbek tilida ber "
        "va kerakli so'zlarning tarjimasini qo'sh."
    ),
    "ijtimoiy": (
        " Muhim sana, shaxs va joylarni aniq ko'rsat; voqeaning sabablari, borishi, natijalari va ahamiyatini ajrat. "
        "Adabiyotda asar muallifi, mavzusi, g'oyasi, qahramonlari va badiiy vositalarini tahlil qil, "
        "asar matnidan uzun parcha ko'chirma. Neytral va xolis bo'l."
    ),
}


def school_subjects_for(grade: int) -> list[tuple[str, str]]:
    return [(key, v[0]) for key, v in SUBJECTS.items() if v[2] <= grade <= v[3]]


def build_school_system(grade: int, subject_key: str) -> str:
    name, category, _, _ = SUBJECTS[subject_key]
    return SCHOOL_BASE.format(grade=grade, subject=name) + SCHOOL_CATEGORY_RULES[category]


def pick_school_ai(category: str):
    """Fan turiga mos AI funksiyasini tanlaydi. Kaliti yo'q bo'lsa, ikkinchisiga o'tadi."""
    preferred = CATEGORY_PROVIDER.get(category, "gemini")
    order = ["gemini", "openai"] if preferred == "gemini" else ["openai", "gemini"]
    for provider in order:
        if provider == "gemini" and gemini_client is not None:
            return ask_gemini
        if provider == "openai" and openai_client is not None:
            return ask_openai
    return None


# ---------------------------------------------------------------- Yordamchilar
def split_text(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Uzun matnni Telegram limitiga mos bo'laklarga ajratadi."""
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


async def send_long(message: Message, text: str, reply_markup=None) -> None:
    """AI javobini bo'laklab, HTML parserisiz yuboradi (AI matnida < > belgilari bo'lishi mumkin)."""
    chunks = split_text(text)
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        await message.answer(chunk, parse_mode=None, reply_markup=reply_markup if is_last else None)


async def safe_edit(msg: Message, text: str, reply_markup=None) -> None:
    """Xabarni tahrirlaydi; imkoni bo'lmasa (masalan, eski xabar) yangisini yuboradi."""
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            await msg.answer(text, reply_markup=reply_markup)


# ------------------------------------------------------------ Word (.docx) yaratish
def _add_inline(paragraph, text: str) -> None:
    """**qalin** va *kursiv* belgilarini Word formatiga o'giradi."""
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            paragraph.add_run(part[1:-1]).italic = True
        else:
            paragraph.add_run(part)


def build_docx(title: str, markdown_text: str) -> bytes:
    """AI matnidan (Markdown) Word hujjat yasaydi va baytlarda qaytaradi."""
    doc = Document()

    # Sahifa: A4, chap 3 sm, qolganlari 2 sm
    for section in doc.sections:
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.left_margin = Cm(3)
        section.right_margin = section.top_margin = section.bottom_margin = Cm(2)

    # Asosiy uslub: Times New Roman 14, qator oralig'i 1.5
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(14)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    normal.paragraph_format.line_spacing = 1.5

    for name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        style = doc.styles[name]
        style.font.name = "Times New Roman"
        style.font.color.rgb = None
        style.font.bold = True
        rfonts = style.element.rPr.rFonts
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            if rfonts.get(qn(attr)) is not None:
                del rfonts.attrib[qn(attr)]
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            rfonts.set(qn(attr), "Times New Roman")
    doc.styles["Title"].font.size = Pt(20)
    doc.styles["Heading 1"].font.size = Pt(16)
    doc.styles["Heading 2"].font.size = Pt(15)
    doc.styles["Heading 3"].font.size = Pt(14)

    title_par = doc.add_paragraph()
    title_par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_par.add_run(title[:200])
    title_run.bold = True
    title_run.font.size = Pt(20)

    for raw in markdown_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")), 3)
            text = line.lstrip("#").strip().strip("*")
            # Matndagi birinchi darajali sarlavhani ikkinchi darajaga tushiramiz
            doc.add_heading(text, level=max(level, 1) if level > 1 else 1)
        elif re.match(r"^[-*•]\s+", line):
            p = doc.add_paragraph(style="List Bullet")
            _add_inline(p, re.sub(r"^[-*•]\s+", "", line))
        elif re.match(r"^\d+[.)]\s+", line):
            p = doc.add_paragraph(style="List Number")
            _add_inline(p, re.sub(r"^\d+[.)]\s+", "", line))
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.first_line_indent = Cm(1.25)
            _add_inline(p, line)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def safe_filename(text: str) -> str:
    name = re.sub(r"[^\w\- ]+", "", text, flags=re.UNICODE).strip().replace(" ", "_")
    return (name[:40] or "referat") + ".docx"


def check_cooldown(user_id: int, seconds: int = COOLDOWN_SECONDS) -> float:
    """Qolgan kutish vaqtini qaytaradi (0 bo'lsa ruxsat)."""
    now = time.monotonic()
    wait = seconds - (now - last_request.get(user_id, 0))
    if wait > 0:
        return wait
    last_request[user_id] = now
    return 0


async def ask_gemini(system: str, user_text: str) -> str:
    if gemini_client is None:
        raise RuntimeError("GEMINI_API_KEY sozlanmagan.")
    response = await gemini_client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_text,
        config=genai_types.GenerateContentConfig(system_instruction=system),
    )
    return response.text or "Javob bo'sh qaytdi, qayta urinib ko'ring."


async def ask_openai(system: str, user_text: str) -> str:
    if openai_client is None:
        raise RuntimeError("OPENAI_API_KEY sozlanmagan.")
    completion = await openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    )
    return completion.choices[0].message.content or "Javob bo'sh qaytdi, qayta urinib ko'ring."


async def handle_ai_request(message: Message, ask_func, system: str, label: str, deliver=None) -> None:
    """Barcha AI so'rovlari uchun umumiy mantiq: tekshiruv, 'yozmoqda...', xatoliklar."""
    text = (message.text or "").strip()
    if not text:
        return

    if len(text) > MAX_INPUT_LENGTH:
        await message.answer(f"Matn juda uzun. Iltimos, {MAX_INPUT_LENGTH} belgidan qisqaroq yuboring.")
        return

    wait = check_cooldown(message.from_user.id)
    if wait:
        await message.answer(f"⏳ Iltimos, {wait:.0f} soniyadan keyin qayta yuboring.")
        return

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    status = await message.answer("⏳ Tayyorlanmoqda, biroz kuting...")

    try:
        answer = await ask_func(system, text)
        if deliver is None:
            await send_long(message, answer)
        else:
            await deliver(message, text, answer)
    except Exception as e:
        logging.exception("%s so'rovida xatolik", label)
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "rate" in err.lower():
            note = "⚠️ So'rovlar hozir juda ko'p. Bir ozdan keyin qayta urinib ko'ring."
        else:
            note = "⚠️ Xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring."
        await message.answer(note)
    finally:
        try:
            await status.delete()
        except Exception:
            pass


# ------------------------------------------------------------------- Buyruqlar
@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"Assalom alaykum, {html.bold(html.quote(message.from_user.full_name))}!\n"
        "Kerakli bo'limni pastdagi tugmalardan tanlang:",
        reply_markup=main_menu_keyboard,
    )


@dp.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Bot imkoniyatlari</b>\n\n"
        f"{BTN_NAZORAT} — savolni qadam-baqadam yechish\n"
        f"{BTN_SLAYD} — taqdimot uchun slaydlar rejasi\n"
        f"{BTN_REFERAT} — referat / mustaqil ish matni\n"
        f"{BTN_MAKTAB} — 5-11 sinf fanlaridan uy vazifasi va tushuntirish\n"
        f"{BTN_STOP} — jarayonni to'xtatish\n\n"
        "Bo'limni tanlang, so'ng mavzu yoki savolni yuboring.",
        reply_markup=main_menu_keyboard,
    )


@dp.message(F.text == BTN_STOP)
@dp.message(Command("stop"))
async def stop_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Jarayon to'xtatildi. Asosiy menyudasiz.", reply_markup=main_menu_keyboard)


# --------------------------------------------------------------- Bo'lim tanlash
@dp.message(F.text == BTN_NAZORAT)
async def nazorat_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.nazorat)
    await message.answer(
        "📝 Nazorat ishi savolini yoki shartini yuboring. Qadam-baqadam yechib beraman.\n"
        "Tugatish uchun «🛑 To'xtatish» tugmasini bosing."
    )


@dp.message(F.text == BTN_SLAYD)
async def slayd_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.slayd)
    await message.answer(
        "📊 Slayd mavzusini yuboring. Gamma.app uchun har bir slaydning sarlavhasi va matnini tuzib beraman.\n"
        "Tugatish uchun «🛑 To'xtatish» tugmasini bosing."
    )


@dp.message(F.text == BTN_REFERAT)
async def referat_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.referat)
    await message.answer(
        "📚 Referat yoki mustaqil ish mavzusini yuboring. Keng qamrovli matn tayyorlab beraman.\n"
        "Tugatish uchun «🛑 To'xtatish» tugmasini bosing."
    )


@dp.message(F.text == BTN_MAKTAB)
async def maktab_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BotStates.maktab)
    await message.answer("🏫 Sinfingizni tanlang:", reply_markup=grade_keyboard())


# ------------------------------------------------------------- AI bilan ishlash
@dp.message(BotStates.nazorat, F.text)
async def process_nazorat(message: Message) -> None:
    await handle_ai_request(message, ask_gemini, NAZORAT_SYSTEM, "Nazorat")


async def deliver_referat_docx(message: Message, topic: str, answer: str) -> None:
    await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
    data = await asyncio.to_thread(build_docx, topic, answer)
    await message.answer_document(
        BufferedInputFile(data, filename=safe_filename(topic)),
        caption="📚 Referat tayyor (Word fayl). Yangi mavzu yuborishingiz mumkin.",
        parse_mode=None,
    )


@dp.message(BotStates.slayd, F.text)
async def process_slayd(message: Message) -> None:
    await handle_ai_request(message, ask_gemini, SLAYD_SYSTEM, "Slayd")


@dp.message(BotStates.referat, F.text)
async def process_referat(message: Message) -> None:
    await handle_ai_request(message, ask_openai, REFERAT_SYSTEM, "Referat", deliver=deliver_referat_docx)


# --------------------------------------------------------------- Maktab darsliklari
def grade_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in GRADES:
        kb.button(text=f"{g}-sinf", callback_data=f"grade:{g}")
    kb.adjust(4, 3)
    return kb.as_markup()


def subject_keyboard(grade: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, name in school_subjects_for(grade):
        kb.button(text=name, callback_data=f"subj:{key}")
    kb.adjust(2)
    kb.row(InlineKeyboardButton(text="⬅️ Sinfni o'zgartirish", callback_data="change_grade"))
    return kb.as_markup()


def change_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Fanni o'zgartirish", callback_data="change_subject")
    kb.button(text="🏫 Sinfni o'zgartirish", callback_data="change_grade")
    kb.adjust(1)
    return kb.as_markup()


@dp.callback_query(F.data == "change_grade")
async def cb_change_grade(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BotStates.maktab)
    await state.update_data(grade=None, subject=None)
    await callback.message.answer("🏫 Sinfingizni tanlang:", reply_markup=grade_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "change_subject")
async def cb_change_subject(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    grade = data.get("grade")
    if not grade:
        await callback.message.answer("🏫 Sinfingizni tanlang:", reply_markup=grade_keyboard())
    else:
        await state.set_state(BotStates.maktab)
        await callback.message.answer(
            f"📘 {grade}-sinf. Fanni tanlang:", reply_markup=subject_keyboard(int(grade))
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("grade:"))
async def cb_grade(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        grade = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer()
        return
    if grade not in GRADES:
        await callback.answer()
        return
    await state.set_state(BotStates.maktab)
    await state.update_data(grade=grade, subject=None)
    await safe_edit(callback.message, f"📘 {grade}-sinf. Fanni tanlang:", reply_markup=subject_keyboard(grade))
    await callback.answer()


@dp.callback_query(F.data.startswith("subj:"))
async def cb_subject(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    grade = data.get("grade")
    key = callback.data.split(":", 1)[1]
    if not grade or key not in SUBJECTS:
        await callback.message.answer("🏫 Avval sinfingizni tanlang:", reply_markup=grade_keyboard())
        await callback.answer()
        return
    await state.set_state(BotStates.maktab)
    await state.update_data(subject=key)
    name = SUBJECTS[key][0]
    await safe_edit(
        callback.message,
        f"✅ {grade}-sinf, {name}.\n\n"
        "Endi savol yoki topshiriq matnini yozib yuboring. Masalan: misol, mashq, mavzu bo'yicha savol.",
        reply_markup=change_keyboard(),
    )
    await callback.answer()


@dp.message(BotStates.maktab, F.text)
async def process_maktab(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    grade, key = data.get("grade"), data.get("subject")
    if not grade:
        await message.answer("🏫 Avval sinfingizni tanlang:", reply_markup=grade_keyboard())
        return
    if key not in SUBJECTS:
        await message.answer(f"📘 {grade}-sinf. Avval fanni tanlang:", reply_markup=subject_keyboard(int(grade)))
        return

    _, category, _, _ = SUBJECTS[key]
    ask_func = pick_school_ai(category)
    if ask_func is None:
        await message.answer("⚠️ AI kalitlari sozlanmagan. .env faylini tekshiring.")
        return

    async def deliver(msg: Message, topic: str, answer: str) -> None:
        await send_long(msg, answer, reply_markup=change_keyboard())

    system = build_school_system(int(grade), key)
    await handle_ai_request(message, ask_func, system, f"Maktab/{key}", deliver=deliver)


@dp.message(~F.text)
async def non_text_handler(message: Message) -> None:
    await message.answer("Hozircha faqat matn qabul qilaman. Savolingizni yozib yuboring.")


@dp.message()
async def default_handler(message: Message) -> None:
    await message.answer("Iltimos, pastdagi tugmalardan birini tanlang.", reply_markup=main_menu_keyboard)


# ------------------------------------------------------------------------ Main
async def health(_request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def start_web_server() -> web.AppRunner:
    """Render'ning bepul Web Service'i port talab qiladi. Bu kichik server ham shu uchun,
    ham UptimeRobot kabi xizmat botni 'uyg'otib' turishi uchun kerak."""
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logging.info("Veb-server %s portda ishga tushdi", port)
    return runner


async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    if gemini_client is None:
        logging.warning("GEMINI_API_KEY topilmadi: Gemini ishlatiladigan bo'limlar ishlamaydi.")
    if openai_client is None:
        logging.warning("OPENAI_API_KEY topilmadi: ChatGPT ishlatiladigan bo'limlar ishlamaydi.")
    # PORT o'zgaruvchisi faqat Render kabi hostinglarda bor; kompyuterda veb-server ishga tushmaydi
    runner = await start_web_server() if os.getenv("PORT") else None
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        if runner is not None:
            await runner.cleanup()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi.")
