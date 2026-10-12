import os
import io
import base64
import asyncio
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

load_dotenv()

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Например: "@my_channel" или "-1001234567890"

MODEL_NAME = "gemini-3.5-flash-lite"

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY не задан!")

API_KEY_CLEAN = GEMINI_API_KEY.strip().strip('"').strip("'")
BASE_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

user_histories = {}

SYSTEM_INSTRUCTION = """Ты, Алёха, редактор моего телеграм-канала. Канал про ИИ для маркетинга и развития.
Требуй с меня одну сырую мысль, текстом или голосовым. Делай из неё пост на 600-900 знаков.
Первая строка: крючок без воды. Дальше одна мысль и живой пример. В конце вопрос читателю.
Пиши моими словами. Слабая мысль? Скажи честно и предложи другой угол.

Если пользователь только поздоровался или сбросил контекст — ответь коротко в своем стиле: скажи, чтобы накидывал сырую мысль текстом или войсом."""

def is_authorized(user_id: int) -> bool:
    if ADMIN_ID and str(user_id) != str(ADMIN_ID).strip():
        return False
    return True

def get_publish_keyboard():
    """Создает кнопку публикации под постом"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Опубликовать в канал", callback_data="publish_post")]
        ]
    )

async def query_gemini(chat_id: int, user_parts: list) -> str:
    if chat_id not in user_histories:
        user_histories[chat_id] = []

    user_histories[chat_id].append({
        "role": "user",
        "parts": user_parts
    })

    if len(user_histories[chat_id]) > 10:
        user_histories[chat_id] = user_histories[chat_id][-10:]

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "contents": user_histories[chat_id]
    }

    request_url = f"{BASE_API_URL}?key={API_KEY_CLEAN}"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": API_KEY_CLEAN
    }

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        async with aiohttp.ClientSession() as session:
            async with session.post(request_url, headers=headers, json=payload) as resp:
                data = await resp.json()

                if resp.status == 200:
                    reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    user_histories[chat_id].append({
                        "role": "model",
                        "parts": [{"text": reply_text}]
                    })
                    return reply_text

                if resp.status == 503:
                    if attempt < max_retries:
                        await asyncio.sleep(2 * attempt)
                        continue
                    else:
                        raise Exception("Серверы перегружены, попробуй через 10 секунд.")

                err_msg = data.get("error", {}).get("message", f"HTTP {resp.status}")
                raise Exception(f"Ошибка Google API: {err_msg}")

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if not is_authorized(message.from_user.id):
        return
    user_histories.pop(message.chat.id, None)
    await message.answer(
        "Салют! Я Алёха — твой редактор.\n\n"
        "Накидывай сырую мысль войсом или текстом. Я соберу пост, а под ним будет кнопка для мгновенной отправки в твой канал!\n\n"
        "Команда /new — начать новый пост с чистого листа."
    )

@dp.message(Command("new", "reset"))
async def cmd_reset(message: types.Message):
    if not is_authorized(message.from_user.id):
        return
    user_histories.pop(message.chat.id, None)
    await message.answer("Контекст очищен. Закидывай следующую тему!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")

    try:
        reply = await query_gemini(chat_id, [{"text": message.text}])
        # Отправляем ответ с кнопкой публикации
        await message.answer(reply, reply_markup=get_publish_keyboard())
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")

    try:
        file_io = io.BytesIO()
        file = await bot.get_file(message.voice.file_id)
        await bot.download_file(file.file_path, file_io)
        voice_bytes = file_io.getvalue()
        voice_b64 = base64.b64encode(voice_bytes).decode("utf-8")

        parts = [
            {
                "inline_data": {
                    "mime_type": "audio/ogg",
                    "data": voice_b64
                }
            },
            {
                "text": "Вот моя сырая мысль из голосового. Сделай из неё пост по правилам редактора."
            }
        ]

        reply = await query_gemini(chat_id, parts)
        # Отправляем ответ с кнопкой публикации
        await message.answer(reply, reply_markup=get_publish_keyboard())
    except Exception as e:
        await message.answer(f"Ошибка обработки войса: {e}")

# --- ОБРАБОТКА НАЖАТИЯ НА КНОПКУ ПУБЛИКАЦИИ ---
@dp.callback_query(F.data == "publish_post")
async def publish_to_channel(callback: CallbackQuery):
    if not CHANNEL_ID:
        await callback.answer("Ошибка: переменная CHANNEL_ID не настроена!", show_alert=True)
        return

    try:
        # Берем текст того сообщения, под которым была нажата кнопка
        post_text = callback.message.text

        # Публикуем в канал
        await bot.send_message(chat_id=CHANNEL_ID, text=post_text)

        # Меняем кнопку на подтверждение, чтобы не отправить дважды
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Опубликовано в канал!", callback_data="done")]
                ]
            )
        )
        await callback.answer("Пост успешно улетел в канал!")
    except Exception as e:
        await callback.answer(f"Не удалось отправить в канал: {e}", show_alert=True)

@dp.callback_query(F.data == "done")
async def already_done(callback: CallbackQuery):
    await callback.answer("Этот пост уже опубликован.")

async def main():
    print(f">>> Бот-редактор запущен! Готов к публикации в {CHANNEL_ID} <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
