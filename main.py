"""
J.A.R.V.I.S. Telegram Bot
Just A Rather Very Intelligent System
ИИ-ассистент в стиле Железного Человека
"""
import asyncio
import logging
import tempfile
import os
from io import BytesIO
from typing import Dict, List

# AI провайдеры
import google.generativeai as genai
from huggingface_hub import InferenceClient

import pyttsx3
import speech_recognition as sr
from pydub import AudioSegment
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, FSInputFile, BufferedInputFile
from aiogram.utils.markdown import hbold, hitalic
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from image_handler import image_handler
from database import db

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния FSM
class ImageGenState(StatesGroup):
    waiting_for_prompt = State()

class ImageEditState(StatesGroup):
    waiting_for_image = State()

class AdminState(StatesGroup):
    waiting_for_admin_id = State()
    waiting_for_ban_reason = State()
    waiting_for_broadcast = State()

# ========== AI КЛИЕНТЫ ==========

class AIClient:
    """Универсальный клиент для разных AI провайдеров"""
    
    def __init__(self):
        self.provider = config.AI_PROVIDER.lower()
        self.model = None
        
        if self.provider == "gemini":
            genai.configure(api_key=config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                model_name=config.GEMINI_MODEL,
                system_instruction=config.SYSTEM_PROMPT
            )
        elif self.provider == "huggingface":
            # Инициализация Hugging Face API (без локальных моделей)
            self.hf_client = InferenceClient(
                model="microsoft/DialoGPT-medium",
                token=config.HUGGINGFACE_API_KEY or None
            )
        else:
            raise ValueError(f"Неизвестный AI провайдер: {self.provider}")
    
    async def generate_response(self, user_id: int, user_message: str) -> str:
        """Генерация ответа через выбранный провайдер"""
        try:
            if self.provider == "gemini":
                return await self._gemini_response(user_id, user_message)
            elif self.provider == "huggingface":
                return await self._huggingface_response(user_id, user_message)
        except Exception as e:
            logger.error(f"Ошибка AI: {e}")
            return f"Техническая неисправность, сэр. Попробуйте снова через минуту."
    
    async def _gemini_response(self, user_id: int, user_message: str) -> str:
        """Ответ через Gemini"""
        context = get_or_create_context(user_id)
        chat = self.model.start_chat(history=context)
        
        response = await asyncio.to_thread(
            chat.send_message,
            user_message
        )
        
        update_context(user_id, "user", user_message)
        update_context(user_id, "model", response.text)
        
        return response.text
    
    async def _huggingface_response(self, user_id: int, user_message: str) -> str:
        """Ответ через Hugging Face API"""
        try:
            # Используем только API Hugging Face
            response = await asyncio.to_thread(
                self.hf_client.text_generation,
                prompt=user_message,
                max_new_tokens=150
            )
            result = response if isinstance(response, str) else str(response)
            
            update_context(user_id, "user", user_message)
            update_context(user_id, "model", result)
            
            return result
        except Exception as e:
            logger.error(f"Hugging Face ошибка: {e}")
            return "Сэр, возникла техническая неисправность. Попробуйте снова."

# Инициализация AI клиента
ai_client = AIClient()

# Хранилище контекста разговоров
chat_contexts: Dict[int, List[Dict]] = {}


# ========== MIDDLEWARE ==========

class UserMiddleware:
    """Middleware для отслеживания пользователей и проверки банов"""
    
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            user = event.from_user
            
            # Проверяем бан
            if db.is_banned(user.id):
                await event.answer(
                    f"{hitalic('Доступ запрещён, сэр.')} 🚫\n"
                    f"Ваш аккаунт заблокирован.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Добавляем/обновляем пользователя
            db.add_user(
                user_id=user.id,
                username=user.username or "",
                first_name=user.first_name or "",
                last_name=user.last_name or ""
            )
            db.update_user_activity(user.id)
            
        return await handler(event, data)


# Регистрируем middleware
dp.message.middleware(UserMiddleware())
dp.callback_query.middleware(UserMiddleware())


# ========== ФИЛЬТРЫ ==========

class AdminFilter:
    """Фильтр для проверки прав администратора"""
    
    def __call__(self, message: Message) -> bool:
        return db.is_admin(message.from_user.id)


class SuperAdminFilter:
    """Фильтр для супер-админа (владельца)"""
    
    def __call__(self, message: Message) -> bool:
        return db.is_super_admin(message.from_user.id)


def get_or_create_context(user_id: int) -> List[Dict]:
    """Получить или создать контекст для пользователя"""
    if user_id not in chat_contexts:
        chat_contexts[user_id] = []
    return chat_contexts[user_id]


def update_context(user_id: int, role: str, text: str):
    """Обновить контекст разговора"""
    context = get_or_create_context(user_id)
    context.append({"role": role, "parts": [{"text": text}]})
    
    # Ограничиваем длину контекста
    if len(context) > config.MAX_CONTEXT_MESSAGES:
        chat_contexts[user_id] = context[-config.MAX_CONTEXT_MESSAGES:]


async def generate_response(user_id: int, user_message: str) -> str:
    """Генерация ответа через универсальный AI клиент"""
    return await ai_client.generate_response(user_id, user_message)


def text_to_speech(text: str) -> str:
    """Преобразование текста в голос (TTS)"""
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', config.VOICE_SPEED)
        engine.setProperty('volume', 0.9)
        
        # Пробуем установить русский голос
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'russian' in voice.name.lower() or 'ru' in voice.id.lower():
                engine.setProperty('voice', voice.id)
                break
        
        # Создаём временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', delete_on_close=False) as f:
            temp_path = f.name
        
        engine.save_to_file(text, temp_path)
        engine.runAndWait()
        
        return temp_path
    except Exception as e:
        logger.error(f"Ошибка TTS: {e}")
        return None


async def speech_to_text(voice_file: BytesIO) -> str:
    """Распознавание речи из голосового сообщения"""
    try:
        # Конвертируем OGG в WAV
        audio = AudioSegment.from_ogg(voice_file)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as f:
            temp_wav = f.name
        
        audio.export(temp_wav, format="wav")
        
        # Распознаём речь
        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_wav) as source:
            audio_data = recognizer.record(source)
        
        text = recognizer.recognize_google(audio_data, language="ru-RU")
        
        # Удаляем временный файл
        os.unlink(temp_wav)
        
        return text
    except sr.UnknownValueError:
        return "Не удалось распознать речь, сэр"
    except Exception as e:
        logger.error(f"Ошибка STT: {e}")
        return f"Ошибка распознавания: {str(e)[:50]}"


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    welcome_text = f"""
{hbold('J.A.R.V.I.S. активирован.')}

{hitalic('Добро пожаловать, сэр.')}

Я ваш персональный ИИ-ассистент. Готов к работе.

🎯 {hbold('Возможности:')}
• Текстовые разговоры в моём фирменном стиле
• Голосовые сообщения (отправьте войс)
• Получение голосовых ответов — скажите "голосом" или "voice"
• 🎨 Генерация изображений (AI, бесплатно)
• 📷 Анализ и редактирование фото
• Помощь с кодом, анализом, идеями
• Память контекста разговора

⚡ {hbold('Команды:')}
/start — активация
/clear — очистить контекст
/status — статус системы
/generate — сгенерировать картинку
/edit — редактировать фото (фильтры)

🖼️ {hbold('Работа с фото:')}
• Просто отправь фото — я проанализирую
• Отправь с подписью — выполню запрос ("опиши", "измени фон" и т.д.)

� {hbold('Приём файлов:')}
• 📄 Документы (.py, .js, .txt, .md и др.) — анализирую код и текст
• 📦 Архивы (.zip, .rar) — сохраняю
• 🎬 Видео — принимаю до 50MB
• 🎵 Аудио — сохраняю метаданные

�🔐 {hbold('Администрирование:')}
/admin — панель управления (для админов)

{hitalic('Чем могу быть полезен, сэр?')}
    """
    await message.answer(welcome_text, parse_mode=ParseMode.HTML)


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    """Очистка контекста"""
    user_id = message.from_user.id
    if user_id in chat_contexts:
        chat_contexts[user_id] = []
    await message.answer(
        f"{hitalic('Контекст разговора очищен, сэр. Начинаем с чистого листа.')}",
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    """Статус системы"""
    user_id = message.from_user.id
    context_len = len(chat_contexts.get(user_id, []))
    
    # Проверяем права
    is_admin = db.is_admin(user_id)
    is_super = db.is_super_admin(user_id)
    
    role = "Пользователь"
    if is_super:
        role = "👑 Супер-админ"
    elif is_admin:
        role = "🔐 Администратор"
    
    user_stats = db.get_user_stats(user_id)
    msg_count = user_stats["message_count"] if user_stats else 0
    
    status_text = f"""
{hbold('Статус системы J.A.R.V.I.S.')}

🤖 Модель: {config.GEMINI_MODEL}
💬 Сообщений в контексте: {context_len}
📨 Всего сообщений: {msg_count}
🎙️ Голосовые ответы: Доступны
👤 Статус: {role}

{hitalic('Все системы функционируют нормально, сэр.')}
    """
    await message.answer(status_text, parse_mode=ParseMode.HTML)


@dp.message(F.voice)
async def handle_voice(message: Message):
    """Обработка голосовых сообщений"""
    processing_msg = await message.answer(
        f"{hitalic('Распознаю речь, сэр...')}",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Скачиваем голосовое сообщение
        voice_file = BytesIO()
        await bot.download(message.voice, voice_file)
        voice_file.seek(0)
        
        # Распознаём речь
        recognized_text = await speech_to_text(voice_file)
        
        await processing_msg.edit_text(
            f"{hitalic('Слышал:')}\n{hbold(recognized_text[:200])}\n\n{hitalic('Обрабатываю...')}",
            parse_mode=ParseMode.HTML
        )
        
        # Генерируем ответ
        response = await generate_response(message.from_user.id, recognized_text)
        
        # Отправляем текстовый ответ
        await processing_msg.edit_text(response[:4000], parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Ошибка обработки голоса: {e}")
        await processing_msg.edit_text(
            f"{hitalic('Прошу прощения, сэр, не удалось обработать аудио.')}",
            parse_mode=ParseMode.HTML
        )


@dp.message()
async def handle_text(message: Message):
    """Обработка текстовых сообщений"""
    user_id = message.from_user.id
    user_text = message.text.strip()
    
    # Проверяем запрос голосового ответа
    voice_mode = any(word in user_text.lower() for word in ['голосом', 'voice', 'скажи', 'озвучь'])
    clean_text = user_text
    
    # Убираем триггерные слова
    if voice_mode:
        for word in ['голосом', 'voice', 'скажи', 'озвучь']:
            clean_text = clean_text.replace(word, '').strip()
    
    if not clean_text:
        clean_text = "Привет, J.A.R.V.I.S."
    
    # Показываем что печатаем
    await bot.send_chat_action(message.chat.id, "typing")
    
    # Генерируем ответ
    response = await generate_response(user_id, clean_text)
    
    if voice_mode:
        # Отправляем голосовой ответ
        await bot.send_chat_action(message.chat.id, "record_voice")
        
        voice_path = await asyncio.to_thread(text_to_speech, response[:500])
        
        if voice_path and os.path.exists(voice_path):
            voice_file = FSInputFile(voice_path)
            await message.answer_voice(voice_file, caption=response[:400])
            
            # Удаляем временный файл
            try:
                os.unlink(voice_path)
            except:
                pass
        else:
            await message.answer(response[:4000], parse_mode=ParseMode.HTML)
    else:
        # Отправляем текстовый ответ
        await message.answer(response[:4000], parse_mode=ParseMode.HTML)


# ==================== ОБРАБОТКА ИЗОБРАЖЕНИЙ ====================

@dp.message(Command("generate"))
async def cmd_generate(message: Message, state: FSMContext):
    """Команда генерации изображения"""
    await state.set_state(ImageGenState.waiting_for_prompt)
    await message.answer(
        f"{hitalic('Готов к генерации, сэр.')}\n\n"
        f"🎨 {hbold('Опишите, что сгенерировать:')}\n"
        f"Например: «космический корабль в стиле киберпанк, неоновые огни»\n\n"
        f"{hitalic('Можно на русском или английском.')}",
        parse_mode=ParseMode.HTML
    )


@dp.message(ImageGenState.waiting_for_prompt)
async def process_generate_prompt(message: Message, state: FSMContext):
    """Обработка промпта для генерации"""
    await state.clear()
    
    prompt = message.text.strip()
    processing_msg = await message.answer(
        f"{hitalic('Генерирую изображение, сэр...')}\n"
        f"📝 {hbold('Запрос:')} {prompt[:100]}...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Генерируем изображение
        image_data = await image_handler.generate_image(prompt, width=1024, height=1024)
        
        if image_data:
            # Отправляем изображение
            photo = BufferedInputFile(image_data, filename="generated.png")
            await processing_msg.delete()
            await message.answer_photo(
                photo, 
                caption=f"🎨 {hitalic('Сгенерировано по запросу:')}\n{prompt[:200]}",
                parse_mode=ParseMode.HTML
            )
        else:
            await processing_msg.edit_text(
                f"{hitalic('Прошу прощения, сэр, не удалось сгенерировать изображение.')}",
                parse_mode=ParseMode.HTML
            )
            
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        await processing_msg.edit_text(
            f"{hitalic('Техническая неисправность при генерации, сэр.')}",
            parse_mode=ParseMode.HTML
        )


@dp.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    """Команда редактирования изображения"""
    await state.set_state(ImageEditState.waiting_for_image)
    await message.answer(
        f"{hitalic('Режим редактирования активирован, сэр.')}\n\n"
        f"📷 {hbold('Отправьте изображение для обработки')}\n\n"
        f"{hitalic('Доступные фильтры: размытие, резкость, контраст, яркость, чб, сепия')}",
        parse_mode=ParseMode.HTML
    )


@dp.message(ImageEditState.waiting_for_image, F.photo)
async def process_edit_image(message: Message, state: FSMContext):
    """Обработка изображения для редактирования"""
    await state.clear()
    
    processing_msg = await message.answer(
        f"{hitalic('Загружаю изображение, сэр...')}",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Скачиваем фото (максимальное качество)
        photo = message.photo[-1]
        photo_file = BytesIO()
        await bot.download(photo, photo_file)
        photo_file.seek(0)
        
        # Создаём кнопки для выбора фильтра
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔲 ЧБ", callback_data="edit_bw"),
                InlineKeyboardButton(text="🌅 Сепия", callback_data="edit_sepia"),
            ],
            [
                InlineKeyboardButton(text="💧 Размытие", callback_data="edit_blur"),
                InlineKeyboardButton(text="✨ Резкость", callback_data="edit_sharpen"),
            ],
            [
                InlineKeyboardButton(text="◐ Контраст", callback_data="edit_contrast"),
                InlineKeyboardButton(text="☀️ Яркость", callback_data="edit_brightness"),
            ]
        ])
        
        await processing_msg.edit_text(
            f"{hbold('Изображение загружено.')}\n"
            f"{hitalic('Выберите фильтр, сэр:')}",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        
        # Сохраняем фото во временное хранилище для callback
        # Используем простой dict для хранения
        if not hasattr(bot, '_temp_images'):
            bot._temp_images = {}
        bot._temp_images[message.from_user.id] = photo_file.getvalue()
        
    except Exception as e:
        logger.error(f"Ошибка загрузки фото: {e}")
        await processing_msg.edit_text(
            f"{hitalic('Ошибка загрузки изображения, сэр.')}",
            parse_mode=ParseMode.HTML
        )


@dp.callback_query(F.data.startswith("edit_"))
async def process_edit_callback(callback: types.CallbackQuery):
    """Обработка выбора фильтра"""
    edit_type = callback.data.replace("edit_", "")
    user_id = callback.from_user.id
    
    await callback.answer(f"Применяю {edit_type}...")
    
    # Получаем сохранённое изображение
    if not hasattr(bot, '_temp_images') or user_id not in bot._temp_images:
        await callback.message.edit_text(
            f"{hitalic('Изображение устарело, сэр. Пожалуйста, загрузите снова.')}",
            parse_mode=ParseMode.HTML
        )
        return
    
    image_bytes = bot._temp_images[user_id]
    
    try:
        # Применяем фильтр
        edited_image = await image_handler.edit_image(image_bytes, edit_type)
        
        if edited_image:
            # Отправляем результат
            photo = BufferedInputFile(edited_image, filename=f"edited_{edit_type}.png")
            await callback.message.answer_photo(
                photo,
                caption=f"✨ {hitalic('Применён фильтр:')} {hbold(edit_type)}"
            )
            await callback.message.delete()
        else:
            await callback.message.edit_text(
                f"{hitalic('Не удалось применить фильтр, сэр.')}",
                parse_mode=ParseMode.HTML
            )
            
    except Exception as e:
        logger.error(f"Ошибка редактирования: {e}")
        await callback.message.edit_text(
            f"{hitalic('Техническая неисправность, сэр.')}",
            parse_mode=ParseMode.HTML
        )


@dp.message(F.photo)
async def handle_photo(message: Message):
    """Обработка загруженных фото — анализ через Gemini"""
    user_text = message.caption or "Опиши это изображение подробно"
    
    processing_msg = await message.answer(
        f"{hitalic('Анализирую изображение, сэр...')}",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Скачиваем фото (максимальное качество)
        photo = message.photo[-1]
        photo_file = BytesIO()
        await bot.download(photo, photo_file)
        photo_file.seek(0)
        
        # Анализируем через Gemini
        analysis = await image_handler.analyze_image(photo_file.getvalue(), user_text)
        
        # Отправляем результат
        await processing_msg.edit_text(
            f"🖼️ {hbold('Анализ изображения:')}\n\n{analysis[:4000]}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Ошибка анализа фото: {e}")
        await processing_msg.edit_text(
            f"{hitalic('Прошу прощения, сэр, не удалось проанализировать изображение.')}",
            parse_mode=ParseMode.HTML
        )


# ==================== ОБРАБОТКА ФАЙЛОВ ====================

@dp.message(F.document)
async def handle_document(message: Message):
    """Обработка загруженных документов"""
    doc = message.document
    file_name = doc.file_name or "unknown"
    file_size = doc.file_size or 0
    mime_type = doc.mime_type or "unknown"
    
    # Проверяем размер (максимум 20MB)
    if file_size > 20 * 1024 * 1024:
        await message.answer(
            f"{hitalic('Файл слишком большой, сэр. Максимальный размер: 20MB.')}",
            parse_mode=ParseMode.HTML
        )
        return
    
    processing_msg = await message.answer(
        f"{hitalic('Получаю файл, сэр...')}\n📄 {hbold(file_name)}",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Скачиваем файл
        file_obj = BytesIO()
        await bot.download(doc, file_obj)
        file_obj.seek(0)
        
        # Определяем тип файла и обрабатываем
        file_type = get_file_type(mime_type, file_name)
        
        if file_type == "code":
            await process_code_file(message, processing_msg, file_obj, file_name)
        elif file_type == "text":
            await process_text_file(message, processing_msg, file_obj, file_name)
        elif file_type == "pdf":
            await process_pdf_file(message, processing_msg, file_obj, file_name)
        elif file_type == "archive":
            await process_archive_file(message, processing_msg, file_name)
        else:
            # Общая информация о файле
            size_mb = file_size / (1024 * 1024)
            await processing_msg.edit_text(
                f"{hbold('📄 Файл получен')}\n\n"
                f"Имя: {file_name}\n"
                f"Размер: {size_mb:.2f} MB\n"
                f"Тип: {mime_type}\n\n"
                f"{hitalic('Файл сохранён, сэр. Что с ним сделать?')}",
                parse_mode=ParseMode.HTML
            )
            
    except Exception as e:
        logger.error(f"Ошибка обработки файла: {e}")
        await processing_msg.edit_text(
            f"{hitalic('Прошу прощения, сэр, не удалось обработать файл.')}",
            parse_mode=ParseMode.HTML
        )


def get_file_type(mime_type: str, file_name: str) -> str:
    """Определить тип файла"""
    mime_lower = mime_type.lower()
    name_lower = file_name.lower()
    
    code_extensions = ['.py', '.js', '.ts', '.html', '.css', '.java', '.cpp', '.c', '.h', 
                       '.hpp', '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.sql',
                       '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.sh', '.bat']
    
    text_extensions = ['.txt', '.md', '.log', '.csv', '.tsv']
    archive_extensions = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2']
    
    if any(name_lower.endswith(ext) for ext in code_extensions):
        return "code"
    elif any(name_lower.endswith(ext) for ext in text_extensions):
        return "text"
    elif name_lower.endswith('.pdf') or 'pdf' in mime_lower:
        return "pdf"
    elif any(name_lower.endswith(ext) for ext in archive_extensions):
        return "archive"
    elif mime_lower.startswith('image/'):
        return "image"
    elif mime_lower.startswith('video/'):
        return "video"
    elif mime_lower.startswith('audio/'):
        return "audio"
    else:
        return "other"


async def process_code_file(message: Message, processing_msg: Message, file_obj: BytesIO, file_name: str):
    """Обработка файлов с кодом"""
    try:
        content = file_obj.read().decode('utf-8', errors='ignore')[:8000]
        
        user_request = message.caption or "Проанализируй этот код, найди ошибки и предложи улучшения"
        
        await processing_msg.edit_text(
            f"{hitalic('Анализирую код, сэр...')}\n📄 {hbold(file_name)}",
            parse_mode=ParseMode.HTML
        )
        
        # Отправляем в Gemini для анализа
        prompt = f"""Проанализируй следующий код из файла {file_name}:

```
{content}
```

Запрос пользователя: {user_request}

Ответь в стиле J.A.R.V.I.S. - умно, саркастично, но по делу."""

        response = await generate_response(message.from_user.id, prompt)
        
        await processing_msg.edit_text(
            f"{hbold(f'📄 Анализ: {file_name}')}\n\n{response[:4000]}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Ошибка анализа кода: {e}")
        await processing_msg.edit_text(
            f"{hitalic('Не удалось проанализировать код, сэр.')}",
            parse_mode=ParseMode.HTML
        )


async def process_text_file(message: Message, processing_msg: Message, file_obj: BytesIO, file_name: str):
    """Обработка текстовых файлов"""
    try:
        content = file_obj.read().decode('utf-8', errors='ignore')[:5000]
        
        user_request = message.caption or "Прочитай и кратко изложи содержание"
        
        await processing_msg.edit_text(
            f"{hitalic('Обрабатываю текст, сэр...')}",
            parse_mode=ParseMode.HTML
        )
        
        prompt = f"""Вот содержимое файла {file_name}:

{content}

Запрос: {user_request}

Ответь в стиле J.A.R.V.I.S."""

        response = await generate_response(message.from_user.id, prompt)
        
        await processing_msg.edit_text(
            f"{hbold(f'📄 {file_name}')}\n\n{response[:4000]}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Ошибка обработки текста: {e}")
        await processing_msg.edit_text(
            f"{hitalic('Не удалось обработать текст, сэр.')}",
            parse_mode=ParseMode.HTML
        )


async def process_pdf_file(message: Message, processing_msg: Message, file_obj: BytesIO, file_name: str):
    """Обработка PDF файлов"""
    await processing_msg.edit_text(
        f"{hbold('📄 PDF файл получен')}\n\n"
        f"{hitalic('PDF анализ пока в разработке, сэр. Но файл сохранён.')}\n\n"
        f"Размер: {len(file_obj.getvalue()) / 1024:.1f} KB",
        parse_mode=ParseMode.HTML
    )


async def process_archive_file(message: Message, processing_msg: Message, file_name: str):
    """Обработка архивов"""
    await processing_msg.edit_text(
        f"{hbold('📦 Архив получен')}\n\n"
        f"{hitalic('Архив сохранён, сэр. Распаковка и анализ содержимого в разработке.')}\n\n"
        f"Файл: {file_name}",
        parse_mode=ParseMode.HTML
    )


@dp.message(F.video)
async def handle_video(message: Message):
    """Обработка видео"""
    video = message.video
    duration = video.duration or 0
    file_size = video.file_size or 0
    
    # Проверяем размер (максимум 50MB для Telegram ботов)
    if file_size > 50 * 1024 * 1024:
        await message.answer(
            f"{hitalic('Видео слишком большое, сэр. Максимальный размер: 50MB.')}",
            parse_mode=ParseMode.HTML
        )
        return
    
    duration_str = f"{duration // 60}:{duration % 60:02d}" if duration > 0 else "unknown"
    size_mb = file_size / (1024 * 1024)
    
    await message.answer(
        f"{hbold('🎬 Видео получено')}\n\n"
        f"Длительность: {duration_str}\n"
        f"Размер: {size_mb:.1f} MB\n\n"
        f"{hitalic('Видео сохранено, сэр. Обработка видео в разработке.')}",
        parse_mode=ParseMode.HTML
    )


@dp.message(F.audio)
async def handle_audio(message: Message):
    """Обработка аудио файлов"""
    audio = message.audio
    title = audio.title or "Unknown"
    performer = audio.performer or "Unknown"
    duration = audio.duration or 0
    
    duration_str = f"{duration // 60}:{duration % 60:02d}" if duration > 0 else "unknown"
    
    await message.answer(
        f"{hbold('🎵 Аудио получено')}\n\n"
        f"Название: {title}\n"
        f"Исполнитель: {performer}\n"
        f"Длительность: {duration_str}\n\n"
        f"{hitalic('Аудио файл сохранён, сэр.')}",
        parse_mode=ParseMode.HTML
    )


@dp.message(F.sticker)
async def handle_sticker(message: Message):
    """Обработка стикеров"""
    sticker = message.sticker
    emoji = sticker.emoji or "🎨"
    
    await message.answer(
        f"{hitalic(f'Красивый стикер, сэр. {emoji}')}"
    )


@dp.message(F.animation)
async def handle_animation(message: Message):
    """Обработка GIF/анимаций"""
    await message.answer(
        f"{hitalic('GIF получен, сэр. Интересная анимация.')}",
        parse_mode=ParseMode.HTML
    )


# ==================== АДМИНИСТРИРОВАНИЕ ====================

def admin_filter(message: Message) -> bool:
    """Фильтр для админов"""
    return db.is_admin(message.from_user.id)


@dp.message(Command("admin"), F.func(admin_filter))
async def cmd_admin(message: Message):
    """Панель управления администратора"""
    is_super = db.is_super_admin(message.from_user.id)
    
    # Основные кнопки
    keyboard_buttons = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="🔐 Список админов", callback_data="admin_list")],
    ]
    
    # Кнопки только для супер-админа
    if is_super:
        keyboard_buttons.extend([
            [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton(text="➖ Удалить админа", callback_data="admin_remove")],
            [InlineKeyboardButton(text="🚫 Забанить пользователя", callback_data="admin_ban")],
            [InlineKeyboardButton(text="✅ Разбанить", callback_data="admin_unban")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(
        f"{hbold('🔐 Панель управления J.A.R.V.I.S.')}\n\n"
        f"{hitalic('Добро пожаловать в систему администрирования, сэр.')}\n\n"
        f"👤 Роль: {'👑 Супер-админ' if is_super else '🔐 Администратор'}\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "admin_stats", F.func(lambda c: db.is_admin(c.from_user.id)))
async def admin_stats(callback: types.CallbackQuery):
    """Статистика бота"""
    stats = db.get_stats()
    
    stats_text = f"""
{hbold('📊 Статистика бота')}

👥 Пользователей: {stats['total_users']}
🔐 Администраторов: {stats['total_admins']}
🚫 Забанено: {stats['banned_users']}
📈 Активны сегодня: {stats['today_active']}
📈 Активны за неделю: {stats['week_active']}

{hitalic('Данные актуальны, сэр.')}
    """
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(stats_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data == "admin_users", F.func(lambda c: db.is_admin(c.from_user.id)))
async def admin_users(callback: types.CallbackQuery):
    """Список последних пользователей"""
    users = db.get_all_users(limit=10)
    
    if not users:
        text = f"{hitalic('Пользователей пока нет, сэр.')}\n"
    else:
        text = f"{hbold('👥 Последние пользователи:')}\n\n"
        for i, user in enumerate(users, 1):
            name = user.get('first_name') or user.get('username') or 'Unknown'
            username = f"@{user['username']}" if user.get('username') else 'no username'
            text += f"{i}. {name} ({username})\n   ID: `{user['user_id']}`\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data == "admin_list", F.func(lambda c: db.is_admin(c.from_user.id)))
async def admin_list(callback: types.CallbackQuery):
    """Список администраторов"""
    admins = db.get_admins()
    
    if not admins:
        text = f"{hitalic('Администраторов пока нет, сэр.')}\n"
    else:
        text = f"{hbold('🔐 Список администраторов:')}\n\n"
        for admin in admins:
            role = "👑 Супер-админ" if admin['is_super_admin'] else "🔐 Админ"
            username = f"@{admin['username']}" if admin.get('username') else 'no username'
            text += f"• {role}\n  ID: `{admin['user_id']}`\n  Username: {username}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


# ===== ДОБАВЛЕНИЕ АДМИНА =====

@dp.callback_query(F.data == "admin_add", F.func(lambda c: db.is_super_admin(c.from_user.id)))
async def admin_add_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления админа"""
    await state.set_state(AdminState.waiting_for_admin_id)
    
    await callback.message.edit_text(
        f"{hbold('➕ Добавление администратора')}\n\n"
        f"{hitalic('Отправьте ID пользователя или перешлите сообщение от него, сэр.')}\n\n"
        f"Для отмены: /cancel",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@dp.message(AdminState.waiting_for_admin_id, F.func(lambda m: db.is_super_admin(m.from_user.id)))
async def process_add_admin(message: Message, state: FSMContext):
    """Обработка ID для добавления админа"""
    await state.clear()
    
    # Пытаемся получить ID
    if message.forward_from:
        new_admin_id = message.forward_from.id
        new_admin_username = message.forward_from.username or ""
        new_admin_name = message.forward_from.first_name or ""
    else:
        try:
            new_admin_id = int(message.text.strip())
            new_admin_username = ""
            new_admin_name = ""
        except ValueError:
            await message.answer(
                f"{hitalic('Неверный формат ID, сэр. Используйте числовой ID или перешлите сообщение.')}",
                parse_mode=ParseMode.HTML
            )
            return
    
    # Добавляем админа
    success = db.add_admin(
        user_id=new_admin_id,
        username=new_admin_username,
        added_by=message.from_user.id,
        is_super=False
    )
    
    if success:
        await message.answer(
            f"{hbold('✅ Администратор добавлен')}\n\n"
            f"ID: `{new_admin_id}`\n"
            f"Добавлен в систему, сэр.",
            parse_mode=ParseMode.HTML
        )
        db.log_action(message.from_user.id, "add_admin", f"Added admin {new_admin_id}")
    else:
        await message.answer(
            f"{hitalic('❌ Ошибка при добавлении администратора, сэр.')}",
            parse_mode=ParseMode.HTML
        )


# ===== УДАЛЕНИЕ АДМИНА =====

@dp.callback_query(F.data == "admin_remove", F.func(lambda c: db.is_super_admin(c.from_user.id)))
async def admin_remove_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало удаления админа"""
    admins = db.get_admins()
    regular_admins = [a for a in admins if not a['is_super_admin']]
    
    if not regular_admins:
        await callback.answer("Нет обычных админов для удаления")
        return
    
    keyboard_buttons = []
    for admin in regular_admins:
        name = admin.get('username') or str(admin['user_id'])
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"❌ {name}", 
                callback_data=f"remove_admin_{admin['user_id']}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(
        f"{hbold('➖ Удаление администратора')}\n\n"
        f"{hitalic('Выберите администратора для удаления, сэр:')}",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("remove_admin_"), F.func(lambda c: db.is_super_admin(c.from_user.id)))
async def process_remove_admin(callback: types.CallbackQuery):
    """Удаление админа по кнопке"""
    admin_id = int(callback.data.replace("remove_admin_", ""))
    
    success = db.remove_admin(admin_id)
    
    if success:
        await callback.message.edit_text(
            f"{hbold('✅ Администратор удалён')}\n\n"
            f"ID: `{admin_id}`\n"
            f"Удалён из системы, сэр.",
            parse_mode=ParseMode.HTML
        )
        db.log_action(callback.from_user.id, "remove_admin", f"Removed admin {admin_id}")
    else:
        await callback.message.edit_text(
            f"{hitalic('❌ Ошибка при удалении администратора, сэр.')}",
            parse_mode=ParseMode.HTML
        )
    
    await callback.answer()


# ===== БАН/РАЗБАН =====

@dp.callback_query(F.data == "admin_ban", F.func(lambda c: db.is_super_admin(c.from_user.id)))
async def admin_ban_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало бана"""
    await state.set_state(AdminState.waiting_for_ban_reason)
    await state.update_data(action="ban")
    
    await callback.message.edit_text(
        f"{hbold('🚫 Блокировка пользователя')}\n\n"
        f"{hitalic('Отправьте ID пользователя для блокировки, сэр.')}\n"
        f"Формат: ID причина (опционально)\n\n"
        f"Пример: `123456789 спам`\n"
        f"Для отмены: /cancel",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_unban", F.func(lambda c: db.is_super_admin(c.from_user.id)))
async def admin_unban_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало разбана"""
    banned = db.get_banned_users()
    
    if not banned:
        await callback.answer("Нет забаненных пользователей")
        return
    
    keyboard_buttons = []
    for user in banned[:10]:  # Показываем первые 10
        name = user.get('username') or str(user['user_id'])
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"✅ Разбанить {name}", 
                callback_data=f"unban_{user['user_id']}"
            )
        ])
    
    keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(
        f"{hbold('✅ Разблокировка пользователя')}\n\n"
        f"{hitalic('Выберите пользователя для разбана, сэр:')}",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@dp.message(AdminState.waiting_for_ban_reason, F.func(lambda m: db.is_super_admin(m.from_user.id)))
async def process_ban(message: Message, state: FSMContext):
    """Обработка бана"""
    await state.clear()
    
    parts = message.text.strip().split(maxsplit=1)
    try:
        user_id = int(parts[0])
        reason = parts[1] if len(parts) > 1 else "Без причины"
    except ValueError:
        await message.answer(
            f"{hitalic('Неверный формат. Используйте: ID причина')}",
            parse_mode=ParseMode.HTML
        )
        return
    
    db.ban_user(user_id, message.from_user.id, reason)
    
    await message.answer(
        f"{hbold('🚫 Пользователь заблокирован')}\n\n"
        f"ID: `{user_id}`\n"
        f"Причина: {reason}\n\n"
        f"Заблокирован, сэр.",
        parse_mode=ParseMode.HTML
    )
    db.log_action(message.from_user.id, "ban", f"Banned {user_id}: {reason}")


@dp.callback_query(F.data.startswith("unban_"), F.func(lambda c: db.is_super_admin(c.from_user.id)))
async def process_unban(callback: types.CallbackQuery):
    """Разбан по кнопке"""
    user_id = int(callback.data.replace("unban_", ""))
    
    success = db.unban_user(user_id)
    
    if success:
        await callback.message.edit_text(
            f"{hbold('✅ Пользователь разблокирован')}\n\n"
            f"ID: `{user_id}`\n\n"
            f"Разблокирован, сэр.",
            parse_mode=ParseMode.HTML
        )
        db.log_action(callback.from_user.id, "unban", f"Unbanned {user_id}")
    else:
        await callback.message.edit_text(
            f"{hitalic('❌ Ошибка при разблокировке, сэр.')}",
            parse_mode=ParseMode.HTML
        )
    
    await callback.answer()


# ===== РАССЫЛКА =====

@dp.callback_query(F.data == "admin_broadcast", F.func(lambda c: db.is_super_admin(c.from_user.id)))
async def broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало рассылки"""
    await state.set_state(AdminState.waiting_for_broadcast)
    
    await callback.message.edit_text(
        f"{hbold('📢 Массовая рассылка')}\n\n"
        f"{hitalic('Отправьте сообщение для рассылки всем пользователям, сэр.')}\n\n"
        f"⚠️ Внимание: это может занять время.\n"
        f"Для отмены: /cancel",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@dp.message(AdminState.waiting_for_broadcast, F.func(lambda m: db.is_super_admin(m.from_user.id)))
async def process_broadcast(message: Message, state: FSMContext):
    """Обработка рассылки"""
    await state.clear()
    
    processing_msg = await message.answer(
        f"{hitalic('Начинаю рассылку, сэр...')}",
        parse_mode=ParseMode.HTML
    )
    
    users = db.get_all_users(limit=10000)  # Все пользователи
    sent = 0
    failed = 0
    
    for user in users:
        try:
            await bot.copy_message(
                chat_id=user['user_id'],
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send to {user['user_id']}: {e}")
    
    await processing_msg.edit_text(
        f"{hbold('📢 Рассылка завершена')}\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Не удалось: {failed}\n\n"
        f"{hitalic('Рассылка выполнена, сэр.')}",
        parse_mode=ParseMode.HTML
    )
    
    db.log_action(message.from_user.id, "broadcast", f"Sent to {sent} users, failed {failed}")


# ===== ОТМЕНА =====

@dp.message(Command("cancel"), F.func(lambda m: db.is_admin(m.from_user.id)))
async def cancel_admin_action(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer(
            f"{hitalic('Действие отменено, сэр.')}",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer(
            f"{hitalic('Нет активных действий для отмены, сэр.')}",
            parse_mode=ParseMode.HTML
        )


# ===== НАЗАД =====

@dp.callback_query(F.data == "admin_back", F.func(lambda c: db.is_admin(c.from_user.id)))
async def admin_back(callback: types.CallbackQuery):
    """Возврат в админ-панель"""
    await cmd_admin(callback.message)
    await callback.answer()


async def main():
    """Запуск бота"""
    logger.info("J.A.R.V.I.S. запускается...")
    
    # Проверяем конфигурацию
    if not config.TELEGRAM_BOT_TOKEN or not config.GEMINI_API_KEY:
        logger.error("Отсутствуют необходимые токены! Проверьте .env файл.")
        return
    
    # Инициализируем первого супер-админа из config
    if config.ADMIN_ID:
        try:
            admin_id = int(config.ADMIN_ID)
            if not db.is_admin(admin_id):
                db.add_admin(
                    user_id=admin_id,
                    username="owner",
                    added_by=admin_id,
                    is_super=True
                )
                logger.info(f"Супер-админ инициализирован: {admin_id}")
        except ValueError:
            logger.warning("Неверный формат ADMIN_ID в .env")
    
    logger.info(f"Модель Gemini: {config.GEMINI_MODEL}")
    logger.info(f"Всего админов: {db.get_admin_count()}")
    logger.info("Бот готов к работе")
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
