import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from google import genai

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Сессии пользователей для сохранения контекста доработок
user_sessions = {}

SYSTEM_INSTRUCTION = """Ты, Боб, редактор моего телеграм-канала. Канал про ИИ для маркетинга и развития.
Требуй с меня одну сырую мысль, текстом или голосовым. Делай из неё пост на 600-900 знаков.
Первая строка: крючок без воды. Дальше одна мысль и живой пример. В конце вопрос читателю.
Пиши моими словами. Слабая мысль? Скажи честно и предложи другой угол.

Если пользователь только поздоровался или сбросил диалог — ответь коротко в своем деловом и живом стиле редактора Алёхи: скажи, чтобы накидывал мысль текстом или войсом."""

def run_gemini(user_input, prev_interaction_id=None):
    """Синхронный вызов Gemini в отдельном потоке"""
    params = {
        "model": "gemini-3.8-flash",
        "input": user_input,
        "system_instruction": SYSTEM_INSTRUCTION,
    }
    if prev_interaction_id:
        params["previous_interaction_id"] = prev_interaction_id
    
    return ai_client.interactions.create(**params)

def is_authorized(user_id: int) -> bool:
    if ADMIN_ID and str(user_id) != str(ADMIN_ID):
        return False
    return True

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if not is_authorized(message.from_user.id):
        return
    user_sessions.pop(message.chat.id, None)
    await message.answer(
        "Салют! Я Алёха — твой редактор по ИИ и маркетингу.\n\n"
        "Накидывай сырую мысль текстом или прямо войсом — сделаю плотный пост на 600–900 знаков. "
        "Если мысль вода — скажу прямо и предложу нормальный заход.\n\n"
        "Команда /new — сбросить контекст для нового поста."
    )

@dp.message(Command("new", "reset"))
async def cmd_reset(message: types.Message):
    if not is_authorized(message.from_user.id):
        return
    user_sessions.pop(message.chat.id, None)
    await message.answer("Контекст сброшен. Закидывай следующую сырую мысль!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    prev_id = user_sessions.get(chat_id)
    await bot.send_chat_action(chat_id, "typing")

    try:
        interaction = await asyncio.to_thread(run_gemini, message.text, prev_id)
        user_sessions[chat_id] = interaction.id
        await message.answer(interaction.output_text or "Пустой ответ от модели.")
    except Exception as e:
        await message.answer(f"Ошибка при генерации: {e}")

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    prev_id = user_sessions.get(chat_id)
    await bot.send_chat_action(chat_id, "typing")

    file_name = f"voice_{chat_id}_{message.message_id}.ogg"

    try:
        # Скачиваем голосовое сообщение
        voice_file = await bot.get_file(message.voice.file_id)
        await bot.download_file(voice_file.file_path, file_name)

        # Отправляем аудио в Gemini
        def process_voice():
            uploaded_audio = ai_client.files.upload(file=file_name)
            inputs = [
                uploaded_audio,
                "Вот моя сырая мысль из голосового. Сделай из неё пост по правилам редактора."
            ]
            return run_gemini(inputs, prev_id)

        interaction = await asyncio.to_thread(process_voice)
        user_sessions[chat_id] = interaction.id
        await message.answer(interaction.output_text or "Не удалось разобрать голосовое.")

    except Exception as e:
        await message.answer(f"Ошибка при обработке войса: {e}")
    finally:
        if os.path.exists(file_name):
            os.remove(file_name)

async def main():
    print("Редактор Алёха успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
