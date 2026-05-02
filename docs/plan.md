# TUNTUN — Документация

> **Версия документа:** актуальная (после Phase 5 + Model Routing)
> **Стек:** Python 3.10 · aiogram 3 · OpenAI API · aiosqlite · APScheduler · Windows Server

---

## 1. Что умеет TUNTUN

TUNTUN — это персональный AI-ассистент в Telegram.
Ты пишешь обычным языком или голосом — бот сам понимает, что делать.

### ✅ Работает сейчас

#### Задачи
- Создать, завершить, удалить, перенести задачу
- Задать приоритет (low / medium / high) и срок
- «Задачи на сегодня», «покажи всё в работе»
- Кнопки: выполнить, перенести, удалить

#### Напоминания
- Разовые: «напомни завтра в 12:00»
- Повторяющиеся: «каждый день в 10 утра»
- «Повторяй каждые 15 минут, пока не нажму сделано»
- Кнопки: Сделано / Отложить на 10 мин / Отменить

#### Динамические базы данных (Разделы)
- «Создай раздел Реклама: расходы, аккаунты, результат»
- Добавить запись, найти, суммировать, аналитика
- Добавить поле, переименовать раздел, редактировать запись

#### Финансы
- «Потратил 50 долларов на тест» → сохраняет в расходы
- Статистика за день / неделю / месяц
- Экспорт в Excel

#### Учёба
- Записать пропуск, задание, дедлайн
- «Что нужно сделать по математике?»

#### Расписание и режим дня
- «Распредели день» → план с задачами, едой, отдыхом
- Учёт sleep_time / wake_time из настроек
- Показать план таблицей или текстом

#### Память
- «Запомни, что я не люблю помидоры»
- «Запомни: новый сервер на VPS 1.1.1.1»
- «Что ты помнишь о рекламе?»
- Автоматическое обновление при изменении данных в чате

#### Голос
- Отправить voice note → транскрипция через Whisper → обработка как текст

#### Фото и документы
- Фото: анализ изображения, чека, скриншота (если включён Vision)
- PDF / документ: скачать и сохранить

#### Проекты
- Создать проект, добавить цель, статус, дедлайн
- «Покажи проекты»

#### Идеи
- «Идея: сделать систему лояльности» → сохраняет
- «Покажи мои идеи»
- «Конвертируй идею #3 в задачу»

#### Онбординг
- При первом запуске: 6 вопросов для настройки (режим дня, стиль ответа, напоминания)

#### Настройки
- Через диалог: «ставь напоминания жёстче», «отвечай короче»
- Сохраняемые настройки: reply_style, default_view, reminder_style, voice_enabled, vision_enabled, planning_style, morning_plan_time, evening_review_time

#### Экспорт
- Задачи, расходы, разделы → Excel (.xlsx) или TXT
- «Экспортируй расходы за июнь»

#### Backup
- «Сделай бэкап» → отправляет tuntun.db файлом

#### Аналитика
- «Сколько потратил в этом месяце?»
- «Сводка по рекламе за неделю»

#### Клавиатуры
- После каждого действия появляются кнопки: задача ✓ / перенести / удалить / идея ✓ / напоминание отменить и т.д.

---

### 🔄 MVP / Частично реализовано
| Функция | Статус |
|---------|--------|
| Text-to-speech (голосовые ответы) | Зарезервировано, не включено |
| Embeddings / semantic search | Зарезервировано для V2 |
| PostgreSQL | Пока SQLite |
| Docker | Не настроен |
| Автоматический вечерний обзор | Настройка есть, задание не реализовано |

---

## 2. Архитектура

```
Telegram сообщение (текст / голос / фото)
    │
    ▼
bot/handlers/message.py   ← onboarding? FSM? → направить
    │                          │
    │                     bot/modules/onboarding.py
    ▼
bot/ai/intent.py          ← classify(message)
    │  model: MODEL_ROUTER (дешёвая быстрая модель)
    │  → JSON: {actions, chat_response_needed, confidence, safety_level, ...}
    │
    ▼
bot/modules/dispatcher.py ← _HANDLERS[intent] → execute
    │
    ├── tasks.py           задачи
    ├── reminders.py       напоминания
    ├── dynamic.py         разделы
    ├── schedule.py        расписание
    ├── regime.py          план дня
    ├── memory.py          память
    ├── projects.py        проекты
    ├── study.py           учёба
    ├── analytics.py       аналитика
    ├── exports.py         экспорт
    ├── backup.py          бэкап
    ├── ideas.py           идеи
    └── user_settings.py   настройки
    │
    ▼
bot/modules/chat_assistant.py
    │  model: choose_model(confidence, safety_level, intents)
    │  → MODEL_CHAT  (обычный разговор)
    │  → MODEL_REASONING  (план, аналитика, неоднозначное, опасное)
    │
    ▼
bot/modules/settings_manager.py  ← apply_reply_style()
    │
    ▼
bot/modules/keyboards.py         ← контекстные кнопки
    │
    ▼
Telegram ответ
```

### Обработка голоса
```
voice note → bot/handlers/voice.py
    → get_model("transcribe") [Whisper]
    → текст → message.py (как обычное сообщение)
```

### Обработка фото
```
photo → bot/handlers/photo.py
    → bot/modules/vision.py
    → get_model("vision")  [мультимодальная модель]
    → structured JSON (photo_type, text, suggested_actions)
    → dispatcher.py
```

---

## 3. Маршрутизация моделей (Model Router)

Файл: `bot/ai/model_router.py`

| Назначение | Переменная | Fallback |
|-----------|-----------|---------|
| Классификация интентов (каждое сообщение) | `MODEL_ROUTER` | `gpt-4.1-mini` |
| Разговор, советы, вопросы | `MODEL_CHAT` | → ROUTER |
| Планирование, аналитика, сложные/опасные действия | `MODEL_REASONING` | → CHAT → ROUTER |
| Анализ изображений | `MODEL_VISION` | → CHAT → ROUTER |
| Голос → текст | `WHISPER_MODEL` | `whisper-1` |
| Semantic search (V2, пока не используется) | `MODEL_EMBEDDINGS` | `text-embedding-3-small` |

**Когда используется REASONING:**
- `confidence < 0.75` (неоднозначный запрос)
- `safety_level = confirm / dangerous`
- Интент в списке: `regime_day_plan`, `schedule_plan_day`, `analytics_query`, `expense_stats`, `section_add_field`, `section_rename`, `record_edit`, `task_delete`, `idea_convert_to_task`
- `data_query_type` = analytics / schedule

---

## 4. Структура файлов

```
d:\AackREF\TUNTUN\
├── main.py                      ← точка входа
├── config.py                    ← все настройки из .env
├── .env                         ← секреты (не в git)
├── .env.example                 ← шаблон настроек
├── requirements.txt
├── tuntun.db                    ← SQLite база данных
│
├── bot/
│   ├── ai/
│   │   ├── intent.py            ← classify() → JSON интент
│   │   ├── model_router.py      ← get_model() / choose_model()
│   │   ├── prompts.py           ← системный промпт
│   │   └── schemas.py           ← JSON-схема intent
│   │
│   ├── core/
│   │   └── capabilities.py     ← список возможностей + MODEL_INFO
│   │
│   ├── db/
│   │   └── database.py         ← все SQL-запросы (aiosqlite)
│   │
│   ├── handlers/
│   │   ├── message.py          ← главный обработчик текста
│   │   ├── voice.py            ← голос → транскрипция
│   │   ├── photo.py            ← фото → vision
│   │   ├── document.py         ← документы
│   │   └── callbacks.py        ← inline-кнопки
│   │
│   ├── modules/
│   │   ├── chat_assistant.py   ← GPT-ответ (MODEL_CHAT/REASONING)
│   │   ├── dispatcher.py       ← маршрутизация по интентам
│   │   ├── keyboards.py        ← контекстные клавиатуры
│   │   ├── settings_manager.py ← apply_reply_style, настройки
│   │   ├── memory_retriever.py ← semantic/keyword поиск по данным
│   │   ├── section_builder.py  ← создание динамических разделов
│   │   │
│   │   ├── tasks.py            ← CRUD задач
│   │   ├── reminders.py        ← CRUD напоминаний + APScheduler
│   │   ├── dynamic.py          ← записи в разделы
│   │   ├── schedule.py         ← расписание
│   │   ├── regime.py           ← план дня
│   │   ├── memory.py           ← долгосрочная память
│   │   ├── projects.py         ← проекты
│   │   ├── study.py            ← учёба
│   │   ├── analytics.py        ← аналитика разделов
│   │   ├── exports.py          ← Excel / TXT экспорт
│   │   ├── backup.py           ← бэкап БД
│   │   ├── ideas.py            ← идеи
│   │   ├── onboarding.py       ← онбординг (6 вопросов)
│   │   ├── user_settings.py    ← настройки пользователя
│   │   ├── menu.py             ← /start меню
│   │   ├── auto_memory.py      ← авто-обновление памяти
│   │   └── vision.py           ← анализ фото
│   │
│   └── utils/
│       └── formatters.py       ← форматирование ответов
│
├── storage/
│   └── voice/                  ← сохранённые голосовые
│
├── logs/
│
├── run.bat                      ← запуск в консоли
├── start.bat                    ← запуск в фоне
├── stop.bat                     ← остановка
├── restart.bat                  ← перезапуск
├── status.bat                   ← проверка статуса
├── auto_update.bat              ← автообновление из git
├── setup.bat                    ← первоначальная настройка
└── SERVER_INSTALL_AND_RUN.bat   ← установка на сервере (всё в одном)
```

---

## 5. Установка на сервере (Windows Server)

### Вариант 1 — Автоматический (рекомендуется)

```cmd
git clone https://github.com/YOUR_REPO/tuntun.git C:\TG_BOTS\TUNTUN
cd C:\TG_BOTS\TUNTUN
SERVER_INSTALL_AND_RUN.bat
```

Скрипт сам:
1. Проверит Python 3.10+
2. Создаст `.venv`
3. Установит зависимости
4. Создаст `.env` (если нет)
5. Откроет редактор для ввода токенов
6. Запустит бота в фоне
7. Зарегистрирует автообновление (каждые 2 минуты из git)

---

### Вариант 2 — Вручную

**1. Клонировать репозиторий**
```cmd
git clone https://github.com/YOUR_REPO/tuntun.git C:\TG_BOTS\TUNTUN
cd C:\TG_BOTS\TUNTUN
```

**2. Создать виртуальное окружение**
```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**3. Настроить .env**
```cmd
copy .env.example .env
notepad .env
```

Заполнить:
```env
TELEGRAM_BOT_TOKEN=  ← получить у @BotFather в Telegram
OPENAI_API_KEY=      ← https://platform.openai.com/api-keys
ADMIN_TELEGRAM_IDS=  ← твой Telegram ID (узнать у @userinfobot)

# Модели (можно оставить как есть)
OPENAI_MODEL=gpt-4o-mini
OPENAI_MODEL_ROUTER=gpt-4.1-mini
OPENAI_MODEL_CHAT=gpt-4.1
OPENAI_MODEL_REASONING=gpt-4.1
OPENAI_MODEL_VISION=gpt-4.1
OPENAI_TRANSCRIBE_MODEL=whisper-1
OPENAI_MODEL_EMBEDDINGS=text-embedding-3-small

TIMEZONE=Europe/Warsaw
DATABASE_PATH=tuntun.db
```

**4. Запустить бота**
```cmd
# Запуск в консоли (для теста):
run.bat

# Запуск в фоне:
start.bat

# Проверить статус:
status.bat

# Остановить:
stop.bat

# Перезапустить:
restart.bat
```

---

### Вариант 3 — Деплой через ZIP

Если нет git на сервере:

1. На локальной машине: скачать архив репозитория
2. Переместить на сервер любым способом (USB, RDP, SCP)
3. Распаковать в `C:\TG_BOTS\TUNTUN`
4. Запустить `setup.bat`

---

## 6. Автообновление

Файл `auto_update.bat` — каждые N минут:
1. `git pull origin main`
2. `pip install -r requirements.txt` (если изменился)
3. Перезапускает бота при изменениях

Настройка интервала в `.env`:
```env
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_INTERVAL_MINUTES=2
GIT_BRANCH=main
```

Установить как Windows Task Scheduler:
```cmd
install_updater_task.bat
```

---

## 7. Команды бота

| Команда | Действие |
|---------|---------|
| `/start` | Онбординг или главное меню |
| `/today` | Задачи и план на сегодня |
| `/tasks` | Все активные задачи |
| `/reminders` | Все напоминания |
| `/sections` | Список созданных разделов |
| `/settings` | Просмотр настроек |
| `/plan` | Сформировать план дня |
| `/help` | Список команд |

**Главное — всё работает через обычные сообщения, не только команды.**

---

## 8. Примеры живых запросов

### Задачи
```
"запиши на завтра сделать задание по математике"
"добавь задачу: проверить аккаунты — высокий приоритет"
"что у меня сегодня по задачам?"
"выполни задачу 1"
"перенеси задачу 3 на пятницу"
```

### Напоминания
```
"напомни завтра в 12:00 позвонить врачу"
"напоминай каждый день в 9 утра"
"напоминай каждые 15 минут, пока не нажму сделано"
"отмени напоминание про звонок"
```

### Динамические разделы
```
"создай раздел Реклама: расходы, аккаунты, результат, дата"
"в рекламе сегодня потратил 30 долларов, результат плохой"
"что у нас по рекламе за неделю?"
"добавь поле в раздел реклама: платформа"
```

### Финансы
```
"потратил 50 на продукты"
"покажи расходы за месяц"
"экспортируй расходы за июнь в excel"
```

### Память
```
"запомни, что я не люблю утренние встречи"
"запомни: VPS сервер = 185.123.x.x"
"что ты помнишь о рекламе?"
```

### Режим дня
```
"распредели день"
"сделай план дня с учётом задач и еды"
"если лягу в 01:30, когда лучше встать?"
```

### Голос
Просто отправь голосовое сообщение — бот транскрибирует и обработает как текст.

### Идеи
```
"идея: сделать систему лояльности для клиентов"
"покажи мои идеи"
"конвертируй идею 2 в задачу"
```

### Настройки
```
"отвечай короче"
"не используй эмодзи"
"напоминания делай жёстче"
"я встаю в 9, ложусь в 1 ночи"
```

---

## 9. Безопасность

- **Авторизация:** бот отвечает только ADMIN_TELEGRAM_IDS из `.env`
  Посторонние получают "Нет доступа."
- **Опасные действия требуют подтверждения:**
  `task_delete`, `section_delete`, `memory_clear`
- **API-ключи только в `.env`** — файл в `.gitignore`, не попадает в репозиторий
- **SQLite локальный** — база не доступна из сети
- **Логи** — в `/logs/`, без секретных данных

---

## 10. Переменные окружения (`.env`)

```env
# ── Обязательные ──────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=        # Токен бота от @BotFather
OPENAI_API_KEY=            # Ключ OpenAI API

# ── Доступ ────────────────────────────────────────────────────────────────
ADMIN_TELEGRAM_IDS=        # Telegram ID через запятую, кому разрешён доступ

# ── Модели ────────────────────────────────────────────────────────────────
OPENAI_MODEL=gpt-4o-mini              # Fallback модель
OPENAI_MODEL_ROUTER=gpt-4.1-mini      # Классификация интентов (дешёвая)
OPENAI_MODEL_CHAT=gpt-4.1             # Разговор, советы
OPENAI_MODEL_REASONING=gpt-4.1        # Планирование, аналитика, опасные действия
OPENAI_MODEL_VISION=gpt-4.1           # Анализ фото (пусто = Vision отключён)
OPENAI_TRANSCRIBE_MODEL=whisper-1     # Голос → текст
OPENAI_MODEL_EMBEDDINGS=text-embedding-3-small  # V2, пока не используется

# ── Настройки ─────────────────────────────────────────────────────────────
DATABASE_PATH=tuntun.db
TIMEZONE=Europe/Warsaw

# ── Автообновление ────────────────────────────────────────────────────────
GIT_BRANCH=main
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_INTERVAL_MINUTES=2
```

---

## 11. Тесты

| Файл | Покрытие |
|------|---------|
| `test_model_routing.py` | 10 тестов — маршрутизация моделей |
| `test_phase5.py` | 15 тестов — идеи, онбординг, клавиатуры, настройки |
| `test_ux_behavior.py` | 10 тестов — UX-сценарии |
| `test_simulation.py` | 12 тестов — симуляция диалогов |
| `_test_scenarios.py` | 60+ тестов — разные сценарии |
| `test_memory_system.py` | Тесты памяти |
| `test_upgrade.py` | Тесты апгрейда схемы |

Запуск всех тестов (без реального API):
```cmd
cd d:\AackREF\TUNTUN
python test_model_routing.py
python test_phase5.py
python _test_scenarios.py
```

---

## 12. Добавление нового интента (для разработчика)

1. **`bot/ai/prompts.py`** — добавить описание интента в системный промпт
2. **`bot/modules/dispatcher.py`** — добавить в `_HANDLERS` обработчик
3. **Создать / обновить модуль** в `bot/modules/`
4. **Добавить тест** в `test_phase5.py` или отдельный файл
5. Если интент сложный → добавить в `_REASONING_INTENTS` в `model_router.py`

---

*Исходный архитектурный бриф (техническое задание) удалён из этого файла и заменён актуальной документацией.*
Это личный Telegram AI-ассистент с памятью, базами данных, расписанием, напоминаниями, голосовыми сообщениями, планированием дня, учёбой, рекламой, финансами, привычками и аналитикой.

Главная идея:
Я общаюсь с ботом обычным языком в Telegram, текстом или голосом.
Бот должен понимать мои сообщения, сам определять, что я хочу сделать, сохранять нужные данные в базу, ставить напоминания, формировать планы, отвечать на вопросы и доставать сохранённую информацию.

Примеры того, как я буду писать:

1. Задачи:
- “запиши завтра сделать задание по математике”
- “напомни вечером доделать рекламу”
- “добавь задачу: проверить аккаунты”
- “поставь приоритет высокий”
- “перенеси это на завтра”
- “что у меня сегодня по задачам?”

2. Учёба:
- “у меня новый предмет PRI, запоминай туда всё по диаграммам”
- “запиши, что по математике нужно подготовить интегралы”
- “у меня был пропуск по польскому”
- “какие у меня долги по учёбе?”
- “что нужно сделать по PRI на этой неделе?”

3. Расписание:
- “дай мой график на сегодня”
- “распредели день”
- “у меня завтра пары с 10 до 15, после них поставь задачи”
- “сделай план на неделю”
- “покажи расписание на год”
- “когда у меня свободное время?”

4. Еда / сон / режим:
- “распиши день так, чтобы я поел 3 раза”
- “если я лягу в 01:30, когда лучше встать?”
- “напомни поесть через 3 часа”
- “учти, что мне нужно поспать минимум 8 часов”
- “сделай план дня с едой, задачами и отдыхом”

5. Реклама / проекты / финансы:
- “создай раздел Реклама”
- “записывай туда расходы, аккаунты, креативы, результаты”
- “сегодня потратил 20 долларов на тесты”
- “по рекламе план завтра: запустить 10 кабинетов”
- “что у нас по расходам за неделю?”
- “какая статистика по рекламе?”
- “покажи планы по проекту”

6. Память:
- “запомни, что новый гиперраздел называется Реклама”
- “запомни, что я не люблю рагу, помидоры и фасоль”
- “запомни, что по утрам мне лучше не ставить тяжёлые задачи”
- “что ты помнишь по рекламе?”
- “какие данные есть в разделе Учёба?”

7. Напоминания:
- “напомни завтра в 12:00 позвонить”
- “напоминай каждый день в 10 утра”
- “напоминай каждые 15 минут, пока я не нажму сделано”
- “отмени напоминание про еду”
- “покажи мои напоминания”

8. Голос:
- Я могу отправить voice note.
- Бот должен перевести голос в текст.
- Потом обработать как обычное сообщение.
- Бот может отвечать текстом.
- В будущем бот может отвечать voice note через text-to-speech.

Основная цель:
Сделать систему, которая помогает мне не забывать задачи, держать порядок в голове, видеть расписание, помнить проекты, записывать расходы/статистику/учёбу/идеи и управлять всем через Telegram.

ВАЖНО:
Бот НЕ должен бесконтрольно переписывать свой код.
Если я пишу “добавь новую функцию” или “создай новую базу”, он не должен менять Python-файлы сам.
Он должен создавать новые сущности, разделы, поля, автоматизации и настройки в базе данных.

То есть правильная логика:
Я пишу:
“создай раздел Реклама: расходы, аккаунты, креативы, результаты, планы”

Бот должен создать в базе данных dynamic entity:
- section: ads
- title: Реклама
- fields:
  - expense
  - account
  - creative
  - result
  - plan
  - date
  - notes

Потом я пишу:
“сегодня потратил 20 долларов на тест 5 аккаунтов”

Бот должен понять, что это относится к разделу Реклама, и сохранить запись туда.

Архитектура должна быть расширяемой.

Стек:
- Python 3.11+
- aiogram 3.x
- SQLite для MVP
- PostgreSQL для production
- SQLAlchemy
- Alembic
- APScheduler для напоминаний
- OpenAI API для AI-логики
- Speech-to-text для голосовых сообщений
- Text-to-speech для будущих голосовых ответов
- Pydantic для схем
- Docker optional
- python-dotenv

Основные модули:

1. Telegram interface
Бот принимает:
- текстовые сообщения
- команды
- voice notes
- inline-кнопки

Команды:
- /start
- /help
- /today
- /tasks
- /reminders
- /sections
- /settings
- /plan
- /done
- /cancel

Но главное управление должно быть через обычные сообщения, а не только команды.

2. AI Router
Каждое сообщение пользователя должно проходить через AI-router.
AI-router определяет intent.

Возможные intents:
- add_task
- update_task
- complete_task
- delete_task
- list_tasks
- create_reminder
- update_reminder
- delete_reminder
- list_reminders
- create_section
- update_section
- delete_section
- add_section_record
- query_section_data
- create_day_plan
- create_week_plan
- ask_question
- update_user_memory
- update_user_settings
- create_automation
- cancel_action
- unknown

AI должен возвращать structured JSON, например:

{
  "intent": "add_task",
  "confidence": 0.92,
  "data": {
    "title": "Сделать задание по математике",
    "date": "2026-04-27",
    "time": "18:00",
    "priority": "high",
    "section": "study"
  },
  "needs_confirmation": false
}

3. Tool / Skill system
Нужен registry функций.

Каждая функция должна иметь:
- name
- description
- input_schema
- handler

Примеры skills:
- add_task
- create_reminder
- create_section
- add_record_to_section
- query_section
- generate_day_plan
- update_settings
- save_memory
- transcribe_voice
- send_voice_response

AI выбирает нужный skill, backend выполняет действие.

4. Database models

Нужны минимум такие таблицы:

User:
- id
- telegram_id
- username
- timezone
- wake_time
- sleep_time
- preferred_response_mode: text / voice / both
- created_at

Task:
- id
- user_id
- title
- description
- section
- priority: low / medium / high
- status: active / done / cancelled / postponed
- due_date
- due_time
- estimated_minutes
- created_at
- updated_at

Reminder:
- id
- user_id
- title
- text
- remind_at
- repeat_rule
- repeat_until_done
- status
- related_task_id
- created_at

Section / EntityDefinition:
- id
- user_id
- name
- title
- description
- created_at

EntityField:
- id
- entity_id
- field_name
- field_type: text / number / date / datetime / boolean / enum / json
- required
- created_at

EntityRecord:
- id
- entity_id
- user_id
- data_json
- created_at
- updated_at

Memory:
- id
- user_id
- key
- value
- category
- importance
- created_at
- updated_at

Automation:
- id
- user_id
- name
- trigger_type: daily / weekly / interval / one_time
- trigger_config_json
- action_type
- action_config_json
- enabled
- created_at

DailyPlan:
- id
- user_id
- date
- plan_json
- created_at

MessageLog:
- id
- user_id
- message_text
- parsed_intent
- ai_response
- created_at

5. Dynamic sections / bases
Это очень важная часть.

Я должен иметь возможность через Telegram создать любой новый раздел.

Примеры:
“создай базу Финансы: сумма, категория, дата, комментарий”
“создай базу Реклама: расход, аккаунт, креатив, результат”
“создай базу Учёба: предмет, задание, дедлайн, статус”
“создай базу Здоровье: сон, еда, тренировка, самочувствие”

Бот должен создать entity definition и fields.

Потом бот должен уметь:
- добавлять записи
- искать записи
- суммировать числа
- делать простую аналитику
- показывать записи за день/неделю/месяц
- отвечать на вопросы по разделу

Пример:
Я пишу:
“по рекламе сегодня расход 30 долларов, результат плохой, завтра тестить новые крео”

Бот сохраняет:
section = ads
data = {
  "expense": 30,
  "currency": "USD",
  "result": "плохой",
  "plan": "завтра тестить новые крео",
  "date": current_date
}

Потом я спрашиваю:
“что у нас по рекламе за неделю?”

Бот должен достать записи из секции ads и выдать нормальную сводку.

6. Planner
Бот должен уметь формировать план дня.

Он учитывает:
- задачи
- напоминания
- дедлайны
- сон
- еду
- свободные окна
- примерную длительность задач
- приоритеты
- учёбу
- проекты

Пример ответа:
“Сегодня план:
09:30 — подъём
10:00 — завтрак
10:30 — PRI: повторить диаграммы
12:00 — проверить рекламу
13:30 — еда
14:00 — математика
16:00 — свободное окно
18:00 — доделать задание
23:30 — подготовка ко сну”

План должен быть не просто текстом, а сохраняться в DailyPlan.

7. Reminder system
Напоминания должны работать через APScheduler.

Типы:
- one_time
- daily
- weekly
- interval
- repeat_until_done

Пример:
“напоминай каждые 10 минут, пока не нажму сделано”

Бот должен отправлять сообщение с кнопками:
- Сделано
- Отложить на 10 мин
- Перенести
- Отменить

8. Voice notes
Логика:
- Пользователь отправляет voice note в Telegram
- Бот скачивает файл
- Передаёт в speech-to-text
- Получает текст
- Отправляет текст в AI-router
- Выполняет действие
- Отвечает пользователю

Нужно сделать отдельный модуль:
ai/speech_to_text.py

В будущем добавить:
ai/text_to_speech.py

9. Safety layer
Опасные действия требуют подтверждения.

Опасные действия:
- удалить раздел
- удалить много записей
- изменить структуру раздела
- отключить все напоминания
- удалить все задачи
- очистить память

Пример:
Пользователь: “удали раздел реклама”
Бот: “Это удалит раздел Реклама и 128 записей. Для подтверждения напиши: подтверждаю удалить раздел Реклама.”

10. Settings
Пользователь может писать:
- “я обычно встаю в 9”
- “ложусь около 1 ночи”
- “мне нужно есть 3 раза в день”
- “ответы лучше коротко”
- “голосовые ответы выключи”
- “напоминания делай жёстче”

Бот должен сохранять эти настройки.

11. Memory
Бот должен различать:
- краткосрочные задачи
- постоянную память
- проектные данные
- настройки

Пример:
“запомни, что я не люблю помидоры”
Это Memory.

“завтра купить курицу”
Это Task.

“по рекламе расход 20 долларов”
Это EntityRecord в section ads.

12. Project structure

Сделай такую структуру проекта:

app/
  main.py
  config.py

  bot/
    __init__.py
    handlers_text.py
    handlers_voice.py
    handlers_commands.py
    keyboards.py

  ai/
    __init__.py
    openai_client.py
    intent_router.py
    tool_schemas.py
    speech_to_text.py
    text_to_speech.py
    prompts.py

  db/
    __init__.py
    session.py
    models.py
    repositories/
      users.py
      tasks.py
      reminders.py
      entities.py
      memory.py
      automations.py
      daily_plans.py

  core/
    __init__.py
    scheduler.py
    safety.py
    planner.py
    memory.py
    skills/
      __init__.py
      registry.py
      tasks.py
      reminders.py
      entities.py
      sections.py
      automations.py
      settings.py
      analytics.py

  migrations/
  tests/
  .env.example
  requirements.txt
  README.md

13. MVP version
Сначала нужно сделать MVP, не пытаться сразу сделать всё идеально.

MVP должен включать:

- Telegram bot
- /start
- обработку обычного текста
- обработку voice note
- speech-to-text
- AI intent router
- задачи
- напоминания
- dynamic sections
- запись данных в разные разделы
- запрос данных из раздела
- план на сегодня
- настройки пользователя
- базовую память

MVP не должен быть одним огромным файлом.
Код должен быть разделён на модули.

14. Development stages

Разбей разработку на этапы:

Stage 1:
- Telegram bot
- SQLite
- SQLAlchemy models
- /start
- text handler

Stage 2:
- AI-router
- intents
- add_task
- list_tasks
- complete_task

Stage 3:
- reminders
- scheduler
- inline buttons

Stage 4:
- dynamic sections
- create_section
- add_section_record
- query_section_data

Stage 5:
- voice notes
- speech-to-text

Stage 6:
- planner
- today plan
- daily automatic morning plan

Stage 7:
- memory and settings

Stage 8:
- analytics by sections
- finance/ads/study summaries

15. Что я хочу получить от тебя

Сначала НЕ пиши весь код сразу.
Сначала выдай:

1. Архитектуру проекта
2. Схему работы бота
3. Список модулей
4. Модели базы данных
5. Intent schema
6. Tool/skill registry design
7. План MVP
8. Потом начни писать код по этапам

Важно:
Когда будешь писать код, делай его production-like:
- модульно
- понятно
- с типизацией
- с Pydantic-схемами
- с нормальной обработкой ошибок
- с логированием
- без каши в одном файле

16. Поведение бота

Бот должен отвечать простым человеческим языком.

Например:
Пользователь:
“завтра в 15 напомни оплатить подписку”

Бот:
“Окей, поставил напоминание на завтра в 15:00: оплатить подписку.”

Пользователь:
“создай раздел реклама”

Бот:
“Создал раздел Реклама. Можешь теперь писать туда расходы, планы, креативы и результаты.”

Пользователь:
“что по рекламе за неделю?”

Бот:
“За эту неделю по рекламе записано 5 событий. Расход: 120 USD. Основные планы: протестировать новые креативы, проверить аккаунты, сравнить результаты.”

17. Важное ограничение

Бот должен быть безопасным:
- не выполнять опасные действия без подтверждения
- не удалять данные случайно
- не менять структуру базы без подтверждения
- не переписывать свой код автоматически

Новые возможности должны добавляться через:
- dynamic sections
- automation system
- settings
- skill registry
- entity records

Финальная цель:
Получить личного Telegram AI-ассистента, который работает как память, планировщик, напоминалка, база знаний, аналитика и помощник по жизни/учёбе/проектам.