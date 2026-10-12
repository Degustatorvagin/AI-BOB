import os
import io
import base64
import asyncio
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY не задан!")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# URL эндпоинта из твоего cURL
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"

# История диалогов пользователей для сохранения контекста доработок
user_histories = {}

SYSTEM_INSTRUCTION = """Ты, Алёха, редактор моего телеграм-канала. Канал про ИИ для маркетинга и развития.
Требуй с меня одну сырую мысль, текстом или голосовым. Делай из неё пост на 600-900 знаков.
Первая строка: крючок без воды. Дальше одна мысль и живой пример. В конце вопрос читателю.
Пиши моими словами. Слабая мысль? Скажи честно и предложи другой угол.

Если пользователь только поздоровался или сбросил контекст — ответь коротко в своем стиле: скажи, чтобы накидывал сырую мысль текстом или войсом."""

def is_authorized(user_id: int) -> bool:
    if ADMIN_ID and str(user_id) != str(ADMIN_ID):
        return False
    return True

async def query_gemini(chat_id: int, user_parts: list) -> str:
    """Отправляет запрос напрямую в Google API с нужным заголовком X-goog-api-key"""
    if chat_id not in user_histories:
        user_histories[chat_id] = []

    # Добавляем сообщение пользователя в историю
    user_histories[chat_id].append({
        "role": "user",
        "parts": user_parts
    })

    # Ограничиваем историю последними 10 сообщениями, чтобы не раздувать контекст
    if len(user_histories[chat_id]) > 10:
        user_histories[chat_id] = user_histories[chat_id][-10:]

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "contents": user_histories[chat_id]
    }

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY.strip()
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL, headers=headers, json=payload) as resp:
            data = await resp.json()
            
            if resp.status != 200:
                err_msg = data.get("error", {}).get("message", "Неизвестная ошибка")
                raise Exception(f"HTTP {resp.status}: {err_msg}")

            reply_text = data["candidates"][0]["content"]["parts"][0]["text"]

            # Сохраняем ответ модели в историю диалога
            user_histories[chat_id].append({
                "role": "model",
                "parts": [{"text": reply_text}]
            })

            return reply_text

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if not is_authorized(message.from_user.id):
        return
    user_histories.pop(message.chat.id, None)
    await message.answer(
        "Салют! Я Алёха — твой редактор по ИИ и маркетингу.\n\n"
        "Накидывай сырую мысль текстом или прямо войсом — соберу пост на 600–900 знаков. "
        "Если идея слабая — скажу прямо и предложу нормальный угол.\n\n"
        "Команда /new — сбросить контекст для нового поста."
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
        await message.answer(reply)
    except Exception as e:
        await message.answer(f"Ошибка при генерации: {e}")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")

    try:
        # Скачиваем голосовое сообщение в буфер оперативной памяти
        file_io = io.BytesIO()
        file = await bot.get_file(message.voice.file_id)
        await bot.download_file(file.file_path, file_io)
        voice_bytes = file_io.getvalue()

        # Кодируем аудио в Base64 для передачи напрямую в Gemini
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
        await message.answer(reply)
    except Exception as e:
        await message.answer(f"Ошибка при обработке войса: {e}")

async def main():
    print(">>> Бот-редактор Алёха запущен через прямой REST API! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
