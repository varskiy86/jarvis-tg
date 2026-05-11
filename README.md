# J.A.R.V.I.S. Telegram Bot 🤖

**Just A Rather Very Intelligent System** — умный ИИ-ассистент в стиле Железного Человека.

� **Подробное описание функций** — см. [`FEATURES.md`](FEATURES.md)

---

## ⚡ Быстрый старт

### 1. Получи API ключи

**Telegram Bot Token:**
1. Напиши [@BotFather](https://t.me/botfather)
2. Создай бота: `/newbot`
3. Скопируй токен

**Google Gemini API Key:**
1. Зайди на [ai.google.dev](https://ai.google.dev/)
2. Получи API ключ (бесплатно)

### 2. Установка

```bash
# Клонируй или скачай файлы бота
# cd J.A.R.V.I.S in TG

# Установи зависимости
pip install -r requirements.txt

# Настройка — отредактируй config.json, добавь свои ключи
# TELEGRAM_BOT_TOKEN — получи у @BotFather
# GEMINI_API_KEY — получи на ai.google.dev
# ADMIN_ID — твой Telegram ID (узнай у @userinfobot)
```

### 3. Запуск

```bash
python main.py
```

---

## 🌐 Деплой (24/7, когда ПК выключен)

### PythonAnywhere (простой)
**Сайт:** [pythonanywhere.com](https://www.pythonanywhere.com)

1. Зарегистрируйся, загрузи файлы в раздел **Files**
2. Открой **Console** → Bash
3. `pip install --user -r requirements.txt`
4. `python main.py`

**Лимит:** ~12 часов в сутки

### Railway (надёжный)
**Сайт:** [railway.app](https://railway.app)

1. Подключи GitHub репозиторий
2. Добавь переменные окружения из `.env`
3. Deploy

**Лимит:** $5/мес кредитов (хватает на месяц 24/7)

### Render (хороший вариант)
**Сайт:** [render.com](https://render.com)

1. New → Web Service
2. Build: `pip install -r requirements.txt`
3. Start: `python main.py`
4. Добавь Environment Variables

**Лимит:** Спит после 15 мин без активности (Telegram webhook будит)

---

## 📋 Структура проекта

```
J.A.R.V.I.S in TG/
├── main.py              # Основной файл бота
├── config.py            # Конфигурация (читает из config.json)
├── config.json          # ⚠️ ТВОИ КЛЮЧИ (редактируй этот файл!)
├── database.py          # База данных (SQLite + JSON)
├── image_handler.py     # Обработка изображений
├── requirements.txt     # Зависимости
├── jarvis.db            # SQLite база (автосоздание)
├── admins.json          # Список админов (автосоздание)
├── FEATURES.md          # Подробное описание функций
└── README.md            # Этот файл
```

---

## � Поддержка

Если что-то не работает:
1. Проверь `.env` — все ли токены заполнены?
2. Проверь логи в консоли
3. Перезапусти бота
4. Попробуй другой хостинг

---

**Готов к работе, сэр!** 🤖
