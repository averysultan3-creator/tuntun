# TUNTUN — Telegram AI OS

Персональный AI-ассистент в Telegram. Голосовые сообщения, задачи, напоминания, динамические базы данных, экспорт Excel, ZIP-backup.

---

## Быстрый старт (Windows)

### 1. Заполнить .env

Открой файл `.env` (если нет — скопируй из `.env.example`) и вставь ключи:

```env
TELEGRAM_BOT_TOKEN=твой_токен_от_BotFather
OPENAI_API_KEY=твой_openai_ключ
OPENAI_MODEL=gpt-4o
TIMEZONE=Europe/Warsaw
DATABASE_PATH=storage/tuntun.db
```

> **Важно:** Никогда не публикуй `.env`. Он добавлен в `.gitignore`.

### 2. Запустить run.bat

Двойной клик на `run.bat`.

При первом запуске автоматически:
- Проверит Python (нужен 3.10+)
- Создаст virtual environment `.venv`
- Установит все зависимости
- Создаст папки `storage/` и `logs/`
- Инициализирует SQLite базу (17 таблиц)
- Запустит бота

---

## Файлы запуска

| Файл | Назначение |
|------|-----------|
| `run.bat` | **Главный.** Setup при первом запуске → потом бот |
| `setup.bat` | Разовая установка окружения |
| `start.bat` | Только запуск бота (после setup) |
| `check.bat` | Диагностика: Python, зависимости, ключи, DB |

---

## Требования

- **Windows 10/11** или Windows Server 2019+
- **Python 3.10+** → https://www.python.org/downloads/
  > При установке выбери **"Add Python to PATH"**
- Доступ в интернет (Telegram API + OpenAI API)

---

## Структура проекта

```
TUNTUN/
├── main.py                  # Точка входа
├── config.py                # Конфигурация (.env)
├── requirements.txt
├── .env                     # Твои ключи (НЕ публиковать!)
├── .env.example             # Шаблон
├── run.bat / setup.bat / start.bat / check.bat
│
├── bot/
│   ├── ai/
│   │   ├── intent.py        # GPT multi-intent классификация
│   │   ├── prompts.py       # System prompt (30+ интентов)
│   │   └── schemas.py       # Константы
│   ├── db/
│   │   └── database.py      # SQLite (17 таблиц)
│   ├── handlers/
│   │   ├── message.py       # Текст + голос
│   │   ├── callbacks.py     # Inline кнопки
│   │   ├── photo.py         # Фото
│   │   ├── document.py      # Документы
│   │   └── voice.py         # Whisper транскрипция
│   ├── modules/
│   │   ├── dispatcher.py    # Multi-intent роутер
│   │   ├── tasks.py         # Задачи
│   │   ├── reminders.py     # Напоминания + inline кнопки
│   │   ├── dynamic.py       # Динамические разделы
│   │   ├── section_builder.py # FSM-диалог создания разделов
│   │   ├── exports.py       # Excel + TXT экспорт
│   │   ├── backup.py        # ZIP backup
│   │   ├── analytics.py     # Аналитика
│   │   ├── menu.py          # Inline меню
│   │   ├── memory.py        # Долгосрочная память
│   │   ├── projects.py      # Проекты + расходы
│   │   ├── schedule.py      # Расписание
│   │   ├── study.py         # Учёба
│   │   └── regime.py        # Режим дня
│   └── utils/
│       ├── scheduler.py     # APScheduler напоминания
│       ├── formatters.py    # Форматирование
│       └── dates.py         # Утилиты дат
│
├── storage/                 # Файлы пользователей
│   ├── photos/ voice/ documents/ exports/ backups/
└── logs/
    └── app.log              # Ротируемые логи (5MB x 3)
```

---

## Возможности и тестовые команды

| Команда | Что делает |
|---------|-----------|
| `/start` | Главное меню с inline кнопками |
| `создай базу финансов` | Conversational DB builder (FSM-диалог) |
| `сегодня потратил 40 zł на еду и 120 zł бензин` | Два action за одно сообщение |
| `завтра в 12 напомни оплатить подписку` | Напоминание с кнопками ✅⏰❌ |
| `дай план на сегодня` | Планировщик дня |
| `выгрузи финансы в Excel` | Excel файл → Telegram |
| `сделай backup` | ZIP архив → Telegram |
| `запомни что FB лучше работает утром` | Долгосрочная память |

### Multi-intent пример
```
"завтра напомни оплатить подписку, потратил $50 на рекламу, запомни что утром тяжёлые задачи не ставить"
```
→ Бот выполнит 3 действия одновременно.

---

## Переменные .env

| Переменная | Описание |
|-----------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен от @BotFather |
| `OPENAI_API_KEY` | OpenAI API ключ |
| `OPENAI_MODEL` | Основная модель для умного чата (например, gpt-4o) |
| `OPENAI_MODEL_ROUTER` | Быстрая модель для классификации действий (например, gpt-4o-mini) |
| `OPENAI_MODEL_CHAT` | Модель для разговорных ответов, если хочешь переопределить `OPENAI_MODEL` |
| `OPENAI_MODEL_REASONING` | Модель для сложных задач, планов и неоднозначного контекста |
| `OPENAI_TRANSCRIBE_MODEL` | Whisper модель |
| `DATABASE_PATH` | Путь к SQLite файлу |
| `TIMEZONE` | Часовой пояс |
| `ADMIN_TELEGRAM_IDS` | ID пользователей через запятую (пусто = все) |

---

## Диагностика

```
check.bat
```

Показывает: Python версию, зависимости, токены (маскированные), DB и таблицы, папки.

Логи: `logs\app.log`
