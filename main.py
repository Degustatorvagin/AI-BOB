import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from google import genai
from google.genai import types as genai_types

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = "AQ.Ab8RN6LgP1CXO1d_QLcbXQbAUkNOchegbXrz8iT357tgAeGpjw"
ADMIN_ID = os.getenv("ADMIN_ID")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не найден в .env или переменных окружения!")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY не найден в .env или переменных окружения!")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Инициализируем клиент с обычным API-ключом
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Хранилище сессий чата
user_chats = {}

SYSTEM_INSTRUCTION = """Ты, Алёха, редактор моего телеграм-канала. Канал про ИИ для маркетинга и развития.
Требуй с меня одну сырую мысль, текстом или голосовым. Делай из неё пост на 600-900 знаков.
Первая строка: крючок без воды. Дальше одна мысль и живой пример. В конце вопрос читателю.
Пиши моими словами. Слабая мысль? Скажи честно и предложи другой угол.

Если пользователь только поздоровался или сбросил диалог — ответь коротко в своем деловом стиле: скажи, чтобы накидывал сырую мысль текстом или войсом."""

def get_or_create_chat(chat_id: int):
    if chat_id not in user_chats:
        user_chats[chat_id] = ai_client.chats.create(
            model="gemini-3.8-flash",
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION
            )
        )
    return user_chats[chat_id]

def is_authorized(user_id: int) -> bool:
    if ADMIN_ID and str(user_id) != str(ADMIN_ID):
        return False
    return True

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if not is_authorized(message.from_user.id):
        return
    user_chats.pop(message.chat.id, None)
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
        # Отправляем сообщение через стандартный генеративный чат
        response = await asyncio.to_thread(chat_session.send_message, message.text)
        await message.answer(response.text or "Пустой ответ.")
    except Exception as e:
        await message.answer(f"Ошибка при генерации: {e}")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    await bot.send_chat_action(chat_id, "typing")
    file_name = f"voice_{chat_id}_{message.message_id}.ogg"

    try:
        voice_file = await bot.get_file(message.voice.file_id)
        await bot.download_file(voice_file.file_path, file_name)

        def process_voice():
            uploaded_audio = ai_client.files.upload(
                file=file_name,
                config=genai_types.UploadFileConfig(mime_type="audio/ogg")
            )
            chat_session = get_or_create_chat(chat_id)
            return chat_session.send_message([
                uploaded_audio,
                "Вот моя сырая мысль из голосового. Сделай из неё пост по правилам редактора."
            ])

        response = await asyncio.to_thread(process_voice)
        await message.answer(response.text or "Не удалось разобрать войс.")

    except Exception as e:
        await message.answer(f"Ошибка при обработке войса: {e}")
    finally:
        if os.path.exists(file_name):
            os.remove(file_name)

async def main():
    print(">>> ВЕРСИЯ 2.0 БЕЗ INTERACTIONS ЗАПУЩЕНА! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
