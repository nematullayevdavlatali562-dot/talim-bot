import asyncio
import io
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from keep_alive import keep_alive

keep_alive()

# === SOZLAMALAR ===
BOT_TOKEN = "8786713515:AAEMyr37l9j2BGQE_WBGweHogtzS-fEx9uU"
GEMINI_API_KEY = "AQ.Ab8RN6IRs76D4q74Fkce8r_ezqT0UDB-xZIhIKiGi36Mwmjb_A"

genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel("gemini-1.5-flash")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def init_db():
  conn = sqlite3.connect("education.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            phone_number TEXT,
            role TEXT,
            grade_or_course TEXT
        )
    """)
  conn.commit()
  conn.close()


init_db()


def save_user_data(user_id, phone, role, grade_or_course):
  conn = sqlite3.connect("education.db")
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT OR REPLACE INTO users (user_id, phone_number, role, grade_or_course)
        VALUES (?, ?, ?, ?)
    """,
      (user_id, phone, role, grade_or_course),
  )
  conn.commit()
  conn.close()


def get_user_info(user_id):
  conn = sqlite3.connect("education.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT role, grade_or_course FROM users WHERE user_id = ?", (user_id,)
  )
  row = cursor.fetchone()
  conn.close()
  return row if row else ("Mavjud emas", "Mavjud emas")


class Registration(StatesGroup):
  waiting_for_phone = State()
  waiting_for_role = State()
  waiting_for_grade_or_course = State()


class TaskGenerator(StatesGroup):
  waiting_for_task_type = State()
  waiting_for_topic = State()
  waiting_for_format = State()


class MathSolver(StatesGroup):
  waiting_for_input = State()
  waiting_for_format = State()


class QuizState(StatesGroup):
  waiting_for_subject = State()


def create_pdf(text: str) -> bytes:
  buffer = io.BytesIO()
  p = canvas.Canvas(buffer, pagesize=letter)
  width, height = letter
  y = height - 50

  lines = text.split("\n")
  for line in lines:
    while len(line) > 80:
      p.drawString(50, y, line[:80])
      line = line[80:]
      y -= 15
      if y < 50:
        p.showPage()
        y = height - 50
    p.drawString(50, y, line)
    y -= 15
    if y < 50:
      p.showPage()
      y = height - 50

  p.save()
  buffer.seek(0)
  return buffer.getvalue()


def create_image(text: str) -> bytes:
  lines = text.split("\n")
  img_height = max(400, len(lines) * 20 + 60)
  img = Image.new("RGB", (800, img_height), color=(255, 255, 255))
  draw = ImageDraw.Draw(img)
  font = ImageFont.load_default()

  y = 30
  for line in lines:
    draw.text((30, y), line, fill=(0, 0, 0), font=font)
    y += 20

  buffer = io.BytesIO()
  img.save(buffer, format="PNG")
  buffer.seek(0)
  return buffer.getvalue()


def get_phone_keyboard():
  button = KeyboardButton(
      text="📱 Telefon raqamni yuborish", request_contact=True
  )
  return ReplyKeyboardMarkup(
      keyboard=[[button]], resize_keyboard=True, one_time_keyboard=True
  )


def get_role_keyboard():
  buttons = [
      [KeyboardButton(text="👨‍🎓 Maktab o'quvchisi")],
      [KeyboardButton(text="🏛 Institut talabasi")],
  ]
  return ReplyKeyboardMarkup(
      keyboard=buttons, resize_keyboard=True, one_time_keyboard=True
  )


def get_grade_keyboard():
  buttons = [
      [KeyboardButton(text="5-sinf"), KeyboardButton(text="6-sinf")],
      [KeyboardButton(text="7-sinf"), KeyboardButton(text="8-sinf")],
      [KeyboardButton(text="9-sinf"), KeyboardButton(text="10-sinf")],
      [KeyboardButton(text="11-sinf")],
  ]
  return ReplyKeyboardMarkup(
      keyboard=buttons, resize_keyboard=True, one_time_keyboard=True
  )


def get_course_keyboard():
  buttons = [
      [KeyboardButton(text="1-kurs"), KeyboardButton(text="2-kurs")],
      [KeyboardButton(text="3-kurs"), KeyboardButton(text="4-kurs")],
  ]
  return ReplyKeyboardMarkup(
      keyboard=buttons, resize_keyboard=True, one_time_keyboard=True
  )


def get_main_keyboard():
  buttons = [
      [KeyboardButton(text="📸 Misolni yechish (Rasm/Matn)")],
      [
          KeyboardButton(text="📝 Nazorat ishi"),
          KeyboardButton(text="📖 Mustaqil ish"),
      ],
      [
          KeyboardButton(text="🎓 Kurs ishi"),
          KeyboardButton(text="📄 Referat / Slayd"),
      ],
      [
          KeyboardButton(text="🧠 Test yechish / Viktorina"),
          KeyboardButton(text="💡 Imtihon maslahatlari"),
      ],
  ]
  return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_format_keyboard():
  buttons = [
      [KeyboardButton(text="📄 PDF Fayl"), KeyboardButton(text="🖼 Rasm")]
  ]
  return ReplyKeyboardMarkup(
      keyboard=buttons, resize_keyboard=True, one_time_keyboard=True
  )


@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
  await state.clear()
  await message.answer(
      f"Assalomu alaykum, **{message.from_user.full_name}**!\n\n"
      "Botimizga xush kelibsiz. Foydalanish uchun ro'yxatdan o'ting.\n"
      "Iltimos, **'📱 Telefon raqamni yuborish'** tugmasini bosing:",
      parse_mode=ParseMode.MARKDOWN,
      reply_markup=get_phone_keyboard(),
  )
  await state.set_state(Registration.waiting_for_phone)


@dp.message(Registration.waiting_for_phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext):
  await state.update_data(phone=message.contact.phone_number)
  await message.answer(
      "✅ Raqam saqlandi!\n\nSiz **Maktab o'quvchisi**misiz yoki **Institut"
      " talabasi**?",
      reply_markup=get_role_keyboard(),
  )
  await state.set_state(Registration.waiting_for_role)


@dp.message(
    Registration.waiting_for_role,
    F.text.in_(["👨‍🎓 Maktab o'quvchisi", "🏛 Institut talabasi"]),
)
async def process_role(message: types.Message, state: FSMContext):
  role_text = message.text
  await state.update_data(role=role_text)

  if role_text == "👨‍🎓 Maktab o'quvchisi":
    await message.answer(
        "📚 Nechinchi sinfda o'qiysiz?", reply_markup=get_grade_keyboard()
    )
  else:
    await message.answer(
        "🎓 Nechinchi kursda o'qiysiz?", reply_markup=get_course_keyboard()
    )

  await state.set_state(Registration.waiting_for_grade_or_course)


@dp.message(Registration.waiting_for_grade_or_course)
async def process_grade_or_course(
    message: types.Message, state: FSMContext
):
  data = await state.get_data()
  save_user_data(
      message.from_user.id, data["phone"], data["role"], message.text.strip()
  )

  await message.answer(
      "✅ **Ro'yxatdan o'tdingiz!**\n\nKerakli bo'limni tanlang:",
      parse_mode=ParseMode.MARKDOWN,
      reply_markup=get_main_keyboard(),
  )
  await state.clear()


@dp.message(F.text == "💡 Imtihon maslahatlari")
async def exam_tips(message: types.Message):
  role, grade_or_course = get_user_info(message.from_user.id)
  wait_msg = await message.answer(
      "⏳ *Sun'iy intellekt siz uchun foydali maslahatlar tayyorlamoqda...*",
      parse_mode=ParseMode.MARKDOWN,
  )
  try:
    prompt = (
        f"Foydalanuvchi darajasi: {role}, {grade_or_course}.\n"
        "Ushbu darajadagi o'quvchi/talaba uchun imtihonlarga tayyorgarlik ko'rish"
        " bo'yicha 5 ta eng foydali maslahat yozib ber. O'zbek tilida bo'lsin."
    )
    response = ai_model.generate_content(prompt)
    await wait_msg.delete()
    await message.answer(
        f"💡 **Siz uchun imtihon maslahatlari:**\n\n{response.text}",
        reply_markup=get_main_keyboard(),
    )
  except Exception:
    await wait_msg.delete()
    await message.answer(
        "⚠️ Xatolik yuz berdi.", reply_markup=get_main_keyboard()
    )


@dp.message(F.text == "🧠 Test yechish / Viktorina")
async def start_quiz(message: types.Message, state: FSMContext):
  await state.clear()
  await message.answer(
      "🎯 Qaysi **fan** bo'yicha test topshirishni xohlaysiz?\n"
      "*(Masalan: Matematika, Tarix, Fizika)*",
      reply_markup=ReplyKeyboardRemove(),
  )
  await state.set_state(QuizState.waiting_for_subject)


@dp.message(QuizState.waiting_for_subject)
async def process_quiz_subject(message: types.Message, state: FSMContext):
  subject = message.text.strip()
  role, grade_or_course = get_user_info(message.from_user.id)
  wait_msg = await message.answer(
      f"⏳ *{subject} fani bo'yicha testlar tayyorlanmoqda...*",
      parse_mode=ParseMode.MARKDOWN,
  )
  try:
    prompt = (
        f"Foydalanuvchi darajasi: {role}, {grade_or_course}.\n"
        f"Fan: {subject}.\n"
        "Ushbu darajaga mos ravishda 5 ta test savolini 4 ta variant (A, B, C,"
        " D) bilan tuz. Oxirida javoblar kalitini ham yoz."
    )
    response = ai_model.generate_content(prompt)
    await wait_msg.delete()
    await message.answer(
        f"🧠 **{subject} bo'yicha testlar:**\n\n{response.text}",
        reply_markup=get_main_keyboard(),
    )
  except Exception:
    await wait_msg.delete()
    await message.answer(
        "⚠️ Xatolik yuz berdi.", reply_markup=get_main_keyboard()
    )
  await state.clear()


@dp.message(F.text == "📸 Misolni yechish (Rasm/Matn)")
async def start_math_solver(message: types.Message, state: FSMContext):
  await state.clear()
  await message.answer(
      "📐 **Misol yoki masalangizni yuboring!**\n\n"
      "• Darslikdagi misol **rasmini** tashlashingiz mumkin 📸\n"
      "• Yoki misol matnini **yozib yuborishingiz** mumkin ✍️",
      reply_markup=ReplyKeyboardRemove(),
  )
  await state.set_state(MathSolver.waiting_for_input)


@dp.message(MathSolver.waiting_for_input, F.photo | F.text)
async def process_math_input(message: types.Message, state: FSMContext):
  if message.photo:
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    photo_bytes = await bot.download_file(file.file_path)
    await state.update_data(
        photo_bytes=photo_bytes.getvalue(), is_photo=True, text=None
    )
  else:
    await state.update_data(
        text=message.text.strip(), is_photo=False, photo_bytes=None
    )
  await message.answer(
      "📥 Yechim va tushuntirishni qaysi formatda olmoqchisiz?",
      reply_markup=get_format_keyboard(),
  )
  await state.set_state(MathSolver.waiting_for_format)


@dp.message(
    MathSolver.waiting_for_format, F.text.in_(["📄 PDF Fayl", "🖼 Rasm"])
)
async def process_solver_format(message: types.Message, state: FSMContext):
  selected_format = message.text
  user_data = await state.get_data()
  role, grade_or_course = get_user_info(message.from_user.id)
  wait_msg = await message.answer(
      "⏳ *Sun'iy intellekt misolni tahlil qilib, yechmoqda...*",
      parse_mode=ParseMode.MARKDOWN,
      reply_markup=ReplyKeyboardRemove(),
  )
  try:
    prompt = (
        f"Foydalanuvchi darajasi: {role}, {grade_or_course}.\n"
        "Ushbu misol/masalani qadamma-qadam, tushunarli va batafsil yechib"
        " ber. O'zbek tilida bo'lsin."
    )
    if user_data["is_photo"]:
      img = Image.open(io.BytesIO(user_data["photo_bytes"]))
      response = ai_model.generate_content([prompt, img])
    else:
      full_prompt = f"{prompt}\n\nMisol matni: {user_data['text']}"
      response = ai_model.generate_content(full_prompt)

    generated_text = response.text
    if selected_format == "📄 PDF Fayl":
      pdf_bytes = create_pdf(generated_text)
      doc_file = BufferedInputFile(pdf_bytes, filename="Misol_Yechimi.pdf")
      await wait_msg.delete()
      await message.answer_document(
          document=doc_file,
          caption=f"✅ **Yechim tayyor!**\n🎓 {grade_or_course}",
          reply_markup=get_main_keyboard(),
      )
    else:
      img_bytes = create_image(generated_text)
      img_file = BufferedInputFile(img_bytes, filename="Misol_Yechimi.png")
      await wait_msg.delete()
      await message.answer_photo(
          photo=img_file,
          caption=f"✅ **Yechim tayyor!**\n🎓 {grade_or_course}",
          reply_markup=get_main_keyboard(),
      )
  except Exception:
    await wait_msg.delete()
    await message.answer(
        "⚠️ Xatolik yuz berdi. Qayta urinib ko'ring.",
        reply_markup=get_main_keyboard(),
    )
  await state.clear()


@dp.message(
    F.text.in_([
        "📝 Nazorat ishi",
        "📖 Mustaqil ish",
        "🎓 Kurs ishi",
        "📄 Referat / Slayd",
    ])
)
async def select_task_type(message: types.Message, state: FSMContext):
  await state.clear()
  task_type = message.text
  await state.update_data(task_type=task_type)
  await message.answer(
      f"✍️ **{task_type}** uchun **fan va mavzuni** kiriting:",
      parse_mode=ParseMode.MARKDOWN,
      reply_markup=ReplyKeyboardRemove(),
  )
  await state.set_state(TaskGenerator.waiting_for_topic)


@dp.message(TaskGenerator.waiting_for_topic)
async def process_task_topic(message: types.Message, state: FSMContext):
  await state.update_data(topic=message.text.strip())
  await message.answer(
      "📥 Tayyorlangan materialni qaysi formatda olmoqchisiz?",
      reply_markup=get_format_keyboard(),
  )
  await state.set_state(TaskGenerator.waiting_for_format)


@dp.message(
    TaskGenerator.waiting_for_format, F.text.in_(["📄 PDF Fayl", "🖼 Rasm"])
)
async def process_task_format(message: types.Message, state: FSMContext):
  selected_format = message.text
  user_data = await state.get_data()
  task_type = user_data["task_type"]
  topic = user_data["topic"]
  role, grade_or_course = get_user_info(message.from_user.id)
  wait_msg = await message.answer(
      f"⏳ *Sun'iy intellekt {task_type}ni tayyorlamoqda...*",
      parse_mode=ParseMode.MARKDOWN,
      reply_markup=ReplyKeyboardRemove(),
  )
  try:
    prompt = (
        f"Foydalanuvchi: {role}, {grade_or_course}.\nTopshiriq: {task_type}.\n"
        f"Mavzu: {topic}.\nDarajaga mos ravishda rejali, tushunarli va"
        " batafsil yozib ber."
    )
    response = ai_model.generate_content(prompt)
    generated_text = response.text
    filename_safe = topic.replace(" ", "_")[:20]
    if selected_format == "📄 PDF Fayl":
      pdf_bytes = create_pdf(generated_text)
      doc_file = BufferedInputFile(
          pdf_bytes, filename=f"{task_type}_{filename_safe}.pdf"
      )
      await wait_msg.delete()
      await message.answer_document(
          document=doc_file,
          caption=f"📌 **{task_type}**\n📝 Mavzu: {topic}",
          reply_markup=get_main_keyboard(),
      )
    else:
      img_bytes = create_image(generated_text)
      img_file = BufferedInputFile(
          img_bytes, filename=f"{task_type}_{filename_safe}.png"
      )
      await wait_msg.delete()
      await message.answer_photo(
          photo=img_file,
          caption=f"📌 **{task_type}**\n📝 Mavzu: {topic}",
          reply_markup=get_main_keyboard(),
      )
  except Exception:
    await wait_msg.delete()
    await message.answer(
        "⚠️ Xatolik yuz berdi.", reply_markup=get_main_keyboard()
    )
  await state.clear()


async def main():
  print("Ta'lim boti ishga tushdi...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
