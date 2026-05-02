# TUNTUN — Server Deployment Guide

> Полное руководство по установке, запуску и обслуживанию TUNTUN на Windows-сервере.

---

## Содержание

1. [Требования](#1-требования)
2. [Структура файлов](#2-структура-файлов)
3. [Быстрый старт](#3-быстрый-старт)
4. [Управление ботом](#4-управление-ботом)
5. [Настройка .env](#5-настройка-env)
6. [Автозапуск и автообновление](#6-автозапуск-и-автообновление)
7. [Структура логов](#7-структура-логов)
8. [Безопасность](#8-безопасность)
9. [Диагностика и устранение проблем](#9-диагностика-и-устранение-проблем)
10. [Структура проекта](#10-структура-проекта)

---

## 1. Требования

| Компонент | Версия | Обязательно |
|-----------|--------|-------------|
| Windows | 10 / Server 2016+ | ✅ |
| Python | 3.10+ | ✅ |
| Git | любая | для автообновления |
| Интернет | — | ✅ |
| Telegram Bot Token | от @BotFather | ✅ |
| OpenAI API Key | от platform.openai.com | ✅ |

**Установить Python:** https://python.org/downloads  
При установке — обязательно отметить **"Add Python to PATH"**.

**Установить Git:** https://git-scm.com/download/win

---

## 2. Структура файлов

```
TUNTUN/
├── DEPLOY_CONFIGURED.bat         ← Главный установщик с ключами (запускать первым)
├── SETUP.bat                      ← Установщик без ключей (запрашивает интерактивно)
├── start.bat                    ← Запустить бота
├── stop.bat                     ← Остановить бота
├── restart.bat                  ← Перезапустить бота
├── status.bat                   ← Статус бота + последние логи
├── check.bat                    ← Проверка установки
├── auto_update.bat              ← Автообновление из git
├── install_bot_task.bat         ← Задача автозапуска (нужны права Admin)
├── install_updater_task.bat     ← Задача автообновления (нужны права Admin)
├── uninstall_tasks.bat          ← Удалить обе задачи планировщика
├── run_background.py            ← PID-менеджер (используется bat-файлами)
├── main.py                      ← Точка входа бота
├── config.py                    ← Конфигурация
├── requirements.txt             ← Python-зависимости
├── .env                         ← Секреты (НЕ в git!) 
├── .env.example                 ← Шаблон .env
├── bot/                         ← Код бота
├── logs/                        ← Логи (НЕ в git)
│   ├── runtime.log              ← Вывод бота
│   ├── deploy.log               ← История деплоев
│   └── last_good_commit.txt     ← Последний успешный коммит
├── storage/                     ← Данные пользователей (НЕ в git)
│   ├── backups/                 ← Автобэкапы БД перед деплоем
│   └── ...
├── tuntun.db                    ← База данных SQLite (НЕ в git)
└── bot.pid                      ← PID запущенного процесса (runtime)
```

---

## 3. Быстрый старт

### Шаг 1 — Скопируй папку на сервер

Распакуй проект в любую папку, например `C:\bots\TUNTUN\`.

### Шаг 2 — Запусти установщик

Дважды кликни на `DEPLOY_CONFIGURED.bat` (если ключи уже вписаны).
Или запусти `SETUP.bat` — он попросит ввести токены интерактивно.

Установщик автоматически:
- Найдёт Python и создаст виртуальное окружение `.venv`
- Установит все зависимости из `requirements.txt`
- Создаст нужные папки (`logs/`, `storage/`, `storage/backups/`)
- Создаст `.env` из `.env.example` и откроет его в Notepad
- Инициализирует базу данных
- Проверит все настройки
- Установит задачи в Планировщик Windows (если запущен от Admin)
- Запустит бота в фоне

### Шаг 3 — Заполни .env

При первом запуске установщик откроет `.env` в Notepad. Заполни:

```ini
TELEGRAM_BOT_TOKEN=  ← токен от @BotFather
OPENAI_API_KEY=      ← ключ с platform.openai.com
ADMIN_TELEGRAM_IDS=  ← твой Telegram user ID (число)
```

Сохрани файл и **повторно запусти** `SETUP.bat`.

---

## 4. Управление ботом

| Команда | Описание |
|---------|----------|
| `start.bat` | Запустить бота в фоне |
| `stop.bat` | Остановить бота (по PID) |
| `restart.bat` | Перезапустить бота |
| `status.bat` | Показать статус, PID, git-коммит и последние 30 строк лога |
| `check.bat` | Проверить все зависимости и настройки |

Все команды безопасны: `start.bat` не запустит второй экземпляр, `stop.bat` остановит только процесс бота (не всё Python-окружение).

---

## 5. Настройка .env

Файл `.env` содержит все настройки бота. **Никогда не добавляй его в git.**

```ini
# === Обязательные ===
TELEGRAM_BOT_TOKEN=   # Токен от @BotFather
OPENAI_API_KEY=       # Ключ с platform.openai.com

# === Модели ===
OPENAI_MODEL=gpt-4o                   # Основная умная модель
OPENAI_MODEL_ROUTER=gpt-4o-mini       # Для классификации интентов (быстрая)
OPENAI_MODEL_CHAT=                    # Для чата (пусто = OPENAI_MODEL)
OPENAI_MODEL_REASONING=               # Для сложных задач
OPENAI_MODEL_VISION=                  # Для анализа фото (пусто = отключено)

# === Голос ===
OPENAI_TRANSCRIBE_MODEL=whisper-1

# === База данных ===
DATABASE_PATH=storage/tuntun.db

# === Временная зона ===
TIMEZONE=Europe/Warsaw

# === Доступ ===
ADMIN_TELEGRAM_IDS=123456789,987654321   # Telegram ID через запятую

# === Автообновление ===
GIT_BRANCH=main
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_INTERVAL_MINUTES=2
```

> Узнать свой Telegram ID: напиши боту @userinfobot

---

## 6. Автозапуск и автообновление

### Автозапуск при старте Windows

Запусти **от имени администратора**:
```
install_bot_task.bat
```

Создаёт задачу `TUNTUN_BOT` в Планировщике задач Windows.  
Бот автоматически запустится при перезагрузке сервера с задержкой 30 секунд.

### Автообновление из git

Запусти **от имени администратора**:
```
install_updater_task.bat
```

Создаёт задачу `TUNTUN_AUTO_UPDATE`, которая каждые N минут:
1. Делает `git fetch origin`
2. Сравнивает локальный и удалённый HEAD
3. Если есть изменения — делает резервную копию БД, останавливает бота, `git pull`, `pip install`, `--init-db`, запускает снова
4. При неудаче — откатывает git и БД к последней рабочей версии

Интервал задаётся в `.env`: `AUTO_UPDATE_INTERVAL_MINUTES=2`

### Отключить автообновление

В `.env` установи: `AUTO_UPDATE_ENABLED=false`

### Удалить задачи планировщика

```
uninstall_tasks.bat
```

---

## 7. Структура логов

| Файл | Содержимое |
|------|-----------|
| `logs/runtime.log` | Stdout/stderr бота (5 MB × 3 ротации) |
| `logs/app.log` | Логи самого приложения (aiogram, db) |
| `logs/deploy.log` | История каждого auto_update прогона |
| `logs/last_good_commit.txt` | SHA последнего успешного деплоя |

Просмотр последних 30 строк: `status.bat`

Просмотр полного лога:
```
powershell Get-Content logs\runtime.log -Tail 100
```

---

## 8. Безопасность

- **Ключи никогда не выводятся** в консоль — только `present` / `not set`
- **`.env` в `.gitignore`** — не попадёт в репозиторий
- **`bot.pid`** — предотвращает запуск двух экземпляров бота
- **`update.lock`** — предотвращает одновременный запуск двух автообновлений
- **`stop.bat`** убивает только конкретный PID, не все python.exe процессы
- **Резервная копия БД** создаётся перед каждым деплоем в `storage/backups/`
- **Откат** — при неудачном деплое git и БД откатываются автоматически
- `.gitignore` исключает все данные пользователей: `storage/`, `logs/`, `*.db`

---

## 9. Диагностика и устранение проблем

### Бот не запускается

```
check.bat
```
Показывает, что именно не так: Python, .env, ключи, импорты.

### Бот завис / не отвечает

```
restart.bat
```

### Посмотреть ошибки

```
status.bat
```
или
```
powershell Get-Content logs\runtime.log -Tail 50
```

### Ошибка "Bot is already running"

```
stop.bat
start.bat
```

Или вручную: удали файл `bot.pid` и запусти `start.bat`.

### Автообновление не работает

1. Проверь `logs/deploy.log`
2. Убедись, что `GIT_BRANCH` в `.env` совпадает с веткой репозитория
3. Убедись, что git настроен (`git remote -v`)
4. Задача должна быть создана от имени Admin: `schtasks /query /tn TUNTUN_AUTO_UPDATE`

### После обновления бот не стартует

Проверь `logs/deploy.log` — в конце должна быть строка `[ROLLBACK]`.  
Бот должен был откатиться автоматически. Если нет — запусти вручную:
```
git log --oneline -5
git reset --hard <последний-рабочий-коммит>
start.bat
```

### Сброс и переустановка

```
stop.bat
del tuntun.db
SETUP.bat
```
> ⚠️ Удаление `tuntun.db` сотрёт все данные пользователей. Предварительно сделай копию.

---

## 10. Структура проекта

```
bot/
├── core/
│   └── capabilities.py      # Список возможностей бота
├── db/
│   └── database.py          # SQLite: tasks, memory, vision, state
├── handlers/
│   ├── message.py           # Входящие текстовые сообщения
│   ├── callbacks.py         # Inline-кнопки
│   ├── photo.py             # Обработка фото (Vision)
│   └── document.py          # Обработка документов
├── ai/
│   ├── intent.py            # Классификация намерений (MODEL_ROUTER)
│   ├── prompts.py           # Системные промпты
│   └── openai_client.py     # Клиент OpenAI
├── modules/
│   ├── chat_assistant.py    # Чат-ответы (MODEL_CHAT)
│   ├── dispatcher.py        # Диспетчер действий (Safe Actions Layer)
│   ├── memory_retriever.py  # Поиск контекста в памяти
│   └── vision.py            # Анализ изображений (MODEL_VISION)
└── utils/
    └── scheduler.py         # APScheduler — напоминания
```

---

*TUNTUN — персональный AI-ассистент в Telegram*
