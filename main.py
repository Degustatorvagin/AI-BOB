import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from google import genai
from google.genai import types as genai_types

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан в переменных окружения!")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY не задан в переменных окружения!")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Хранилище сессий для сохранения контекста диалога
user_chats = {}

SYSTEM_INSTRUCTION = """Ты, Боб, редактор моего телеграм-канала. Канал про ИИ для маркетинга и развития.
Требуй с меня одну сырую мысль, текстом или голосовым. Делай из неё пост на 600-900 знаков.
Первая строка: крючок без воды. Дальше одна мысль и живой пример. В конце вопрос читателю.
Пиши моими словами. Слабая мысль? Скажи честно и предложи другой угол.

Если пользователь только поздоровался или сбросил контекст — ответь коротко в своем стиле: скажи, чтобы накидывал сырую мысль текстом или войсом."""

def get_or_create_chat(chat_id: int):
    """Возвращает существующий диалог с контекстом или создает новый"""
    if chat_id not in user_chats:
        user_chats[chat_id] = ai_client.chats.create(
            model="gemini-3.8-flash",
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION
            )
        )
    return user_chats[chat_id]

def is_authorized(user_id: int) -> bool:
    """Ограничение доступа только для владельца бота (если ADMIN_ID указан)"""
    if ADMIN_ID and str(user_id) != str(ADMIN_ID):
        return False
    return True

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if not is_authorized(message.from_user.id):
        return
    user_chats.pop(message.chat.id, None)
    await message.answer(
        "Салют! Я Боб — твой редактор по ИИ и маркетингу.\n\n"
        "Накидывай сырую мысль текстом или прямо войсом — сделаю пост на 600–900 знаков. "
        "Если идея слабая — скажу прямо и предложу нормальный заход.\n\n"
        "Команда /new — сбросить контекст для нового поста."
    )

@dp.message(Command("new", "reset"))
async def cmd_reset(message: types.Message):
    if not is_authorized(message.from_user.id):
        return
    user_chats.pop(message.chat.id, None)
    await message.answer("Контекст очищен. Закидывай следующую тему!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")

    try:
        chat_session = get_or_create_chat(chat_id)
        response = await asyncio.to_thread(chat_session.send_message, message.text)
        await message.answer(response.text or "Пустой ответ от модели.")
    except Exception as e:
        await message.answer(f"Ошибка генерации: {e}")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")
    file_name = f"voice_{chat_id}_{message.message_id}.ogg"

    try:
        # Скачиваем войс из Telegram
        voice_file = await bot.get_file(message.voice.file_id)
        await bot.download_file(voice_file.file_path, file_name)

        def process_voice():
            # Загружаем аудиофайл в Gemini с явным MIME-типом
            uploaded_audio = ai_client.files.upload(
                file=file_name,
                config=genai_types.UploadFileConfig(mime_type="audio/ogg")
            )
            chat_session = get_or_create_chat(chat_id)
            return chat_session.send_message([
                uploaded_audio,
                "Вот моя сырая мысль из голосового сообщения. Преврати её в пост по правилам редактора."
            ])

        response = await asyncio.to_thread(process_voice)
        await message.answer(response.text or "Не удалось разобрать голосовое.")

    except Exception as e:
        await message.answer(f"Ошибка при обработке войса: {e}")
    finally:
        # Удаляем локальный временный файл с хостинга
        if os.path.exists(file_name):
            os.remove(file_name)

async def main():
    print(">>> Бот-редактор Алёха успешно запущен! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
