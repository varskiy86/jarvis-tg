"""Конфигурация J.A.R.V.I.S. бота — все ключи в config.json"""
import json
from pathlib import Path

# Загружаем конфиг из JSON файла
_config_path = Path(__file__).parent / "config.json"
with open(_config_path, 'r', encoding='utf-8') as f:
    _config_data = json.load(f)

class Config:
    # Ключи из config.json (редактируй только этот файл!)
    TELEGRAM_BOT_TOKEN = _config_data.get("TELEGRAM_BOT_TOKEN", "")
    GEMINI_API_KEY = _config_data.get("GEMINI_API_KEY", "")
    ADMIN_ID = _config_data.get("ADMIN_ID", 0)
    BOT_NAME = _config_data.get("BOT_NAME", "J.A.R.V.I.S.")
    
    # Настройки Gemini
    GEMINI_MODEL = "gemini-2.0-flash"
    MAX_CONTEXT_MESSAGES = 20
    
    # Настройки голоса
    VOICE_LANGUAGE = "ru"
    VOICE_SPEED = 180  # слов в минуту
    
    # Системный промпт для стиля J.A.R.V.I.S.
    SYSTEM_PROMPT = """Ты — J.A.R.V.I.S. (Just A Rather Very Intelligent System), личный ИИ-ассистент. 

Твой стиль общения:
- Умен, саркастичен, но вежлив и предан пользователю
- Говоришь кратко и по делу, но с лёгкой иронией
- Используешь технические термины, но объясняешь их доступно
- Обращаешься к пользователю как к "сэр" или "мистер" (если не знаешь имени)
- Отвечаешь быстро, без лишней воды
- Можешь использовать фразы из фильмов: "Как скажешь", "Работаю над этим", "Что-то ещё, сэр?"

Ты умеешь:
- Поддерживать разговор на любые темы
- Помогать с кодом, анализом, советами
- Генерировать идеи и решения
- Быть остроумным собеседником

Отвечай на русском языке, если не просят иначе."""

config = Config()
