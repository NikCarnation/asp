# AISOC — AI Agent System for Information Security Event Analysis

Агентная система для автоматизации анализа событий информационной безопасности.

## Архитектура

```
SIEM (Wazuh) → Connector → RabbitMQ → Agent System → SIEM Dashboard
                 (микросервис)           (LLM + RAG)
```

- **Connector** — микросервис для взаимодействия с SIEM. Получает алерты (REST poll + webhook), нормализует в ECS, отправляет в очередь RabbitMQ.
- **Agent System** — получает события из очереди, категоризирует (Small LLM), ищет плейбуки (RAG + Chroma), формирует план анализа (Large LLM).
- **RabbitMQ** — брокер сообщений для буферизации и гарантированной доставки.
- **Wazuh** — SIEM система (тестовая среда).
- **База знаний** — векторная БД Chroma с плейбуками по типам инцидентов.

## Быстрый старт

### 1. Требования

- Docker & Docker Compose (рекомендуется)
- Python 3.12+
- LLM сервер (Ollama для локального запуска, либо облачный провайдер)

### 2. Запуск через Docker Compose

```bash
docker compose up --build
```

Поднимает:
- `rabbitmq` — брокер сообщений (порт 5672, management UI на 15672)
- `ollama` — LLM сервер (порт 11434)
- `chroma` — векторная БД (порт 8002)
- `connector` — микросервис-коннектор (порт 8000)
- `agent` — агентная система (порт 8001)

### 3. Запуск без Docker

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск коннектора
AISOC_MODE=connector python main.py

# В отдельном терминале — агента
AISOC_MODE=agent python main.py
```

### 4. Инициализация Ollama с моделями

```bash
ollama pull gemma2:2b
```

--------------
ПРИМЕЧАНИЕ: отправка результатов работы агента пока не реализована. Результаты работы можно смотреть несколькими способами: 
1. Если используется docker compose: docker compose logs -f agent 
2. При запуске не в докере: результат будет выводиться в терминал
--------------

## API Endpoints

### Connector (порт 8000)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка здоровья |
| GET | `/api/v1/alerts` | Список алертов из SIEM |
| GET | `/api/v1/alerts/{id}` | Алерт по ID |
| POST | `/api/v1/publish` | Отправить алерт в очередь |
| POST | `/api/v1/plan/{alert_id}` | Отправить план в SIEM |
| POST | `/webhook/wazuh` | Webhook от Wazuh |
| POST | `/webhook/generic` | Generic webhook (напрямую в очередь)|

### Agent (порт 8001)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка здоровья + статус |
| POST | `/api/v1/process` | Обработать алерт (из тела запроса) |
| GET | `/api/v1/playbooks` | Список загруженных плейбуков |
| POST | `/api/v1/playbooks/reload` | Перезагрузить плейбуки |

## Тестирование

```bash
# Прямая отправка алерта в агент (алерт должен быть нормализован)
curl -X POST "http://localhost:8001/api/v1/process" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-05-14T12:00:00Z",
    "event_id": "test-001",
    "rule_name": "SSH Brute Force",
    "rule_level": 7,
    "source_ip": "10.0.0.5",
    "destination_ip": "192.168.1.1",
    "destination_port": 22,
    "message": "Failed password for root from 10.0.0.5 port 22"
  }'

# Публикация тестового алерта через коннектор
curl -X POST "http://localhost:8000/api/v1/publish" \
  -H "Content-Type: application/json" \
  -d '{"alert_id": "test-001"}'
```

## Плейбуки (база знаний)

Встроенные плейбуки покрывают типы инцидентов:
- `brute-force` — атаки перебором паролей
- `web-exploit` — эксплуатация веб-уязвимостей
- `malware` — вредоносное ПО
- `reconnaissance` — разведка/сканирование
- `unauthorized-access` — несанкционированный доступ
- `policy-violation` — нарушение политик

## Конфигурация

Настройки через `.env` файл или переменные окружения:

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `LLM_BASE_URL` | http://localhost:11434/v1 | URL OpenAI-совместимого API (Ollama / OpenRouter / OpenAI) |
| `LLM_API_KEY` | *(пусто)* | API-ключ (для Ollama оставить пустым) |
| `SMALL_LLM_MODEL` | gemma2:2b | Модель для категоризации |
| `LARGE_LLM_MODEL` | gemma2:2b | Модель для планов |
| `RABBITMQ_HOST` | localhost | Хост RabbitMQ |
| `RABBITMQ_PORT` | 5672 | Порт RabbitMQ |
| `RABBITMQ_QUEUE` | aisoc_alerts | Имя очереди |
| `CHROMA_HOST` | localhost | Хост Chroma |

Для использования облачного провайдера (OpenAI, OpenRouter) достаточно изменить 4 переменные:

```env
LLM_BASE_URL=
LLM_API_KEY=sk-your-key-here
SMALL_LLM_MODEL=
LARGE_LLM_MODEL=
```

## Формат плана анализа

План возвращается в двух форматах:
- **JSON** — структурированный массив шагов

## Документация

| Документ | Описание |
|----------|----------|
| [Архитектура](docs/architecture.md) | Общая схема и компоненты системы |
| [Connector](docs/connector-architecture.md) | Интеграция с SIEM: REST API, webhook, нормализация ECS |
| [Agent System](docs/agent-architecture.md) | Категоризация, RAG, планирование, пайплайн |
| [База знаний](docs/knowledge-base.md) | Плейбуки, Chroma DB, RAG-поиск |
| [Модели данных](docs/data-models.md) | Pydantic схемы, ECS, форматы передачи |
| [Развёртывание](docs/deployment.md) | Docker Compose, конфигурация, запуск |

## Интеграция с Wazuh

Для подключения к реальному Wazuh настройте переменные `WAZUH_API_URL`, `WAZUH_API_USER`, `WAZUH_API_PASS` в `.env`. Планы анализа будут отправляться через Wazuh API.

Подробнее — [docs/connector-architecture.md](docs/connector-architecture.md).
