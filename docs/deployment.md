# Развёртывание и конфигурация

## Запуск через Docker Compose

### 1. Клонирование

```bash
git clone <repo-url> aisoc
cd aisoc
```

### 2. Настройка

```bash
cp .env.example .env
# отредактировать под своё окружение
```

Если `.env.example` отсутствует — создать `.env` на основе таблицы конфигурации ниже.

### 3. Запуск

```bash
docker compose up --build
```

Будут запущены 4 контейнера:

| Сервис | Порт (внешний) | Зависимости |
|--------|---------------|-------------|
| RabbitMQ | 5672, 15672 | — |
| Ollama | 11434 | — |
| Connector | 8000 | RabbitMQ |
| Agent | 8001 | RabbitMQ, Ollama |

### 4. Инициализация моделей Ollama

При первом запуске Ollama автоматически скачает модели, указанные в `SMALL_LLM_MODEL`, `LARGE_LLM_MODEL` и модель эмбеддингов `nomic-embed-text`. Это может занять несколько минут.

Если нужно скачать модели вручную:

```bash
# Установить модели внутри контейнера
docker exec -it aisoc-ollama-1 ollama pull gemma2:2b
docker exec -it aisoc-ollama-1 ollama pull nomic-embed-text

# Или через API
curl http://localhost:11434/api/pull -d '{"name": "gemma2:2b"}'
curl http://localhost:11434/api/pull -d '{"name": "nomic-embed-text"}'
```

### 5. Проверка работоспособности

```bash
# Connector
curl http://localhost:8000/health
# → {"status":"ok","module":"connector"}

# Agent
curl http://localhost:8001/health
# → {"status":"ok","module":"agent","playbooks_count":6,...}

# RabbitMQ Management UI
# http://localhost:15672 (guest/guest)

# Плейбуки (проверка индексации)
curl http://localhost:8001/api/v1/playbooks
# → {"playbooks": [...]}
```

---

## Локальный запуск (без Docker)

### 1. Зависимости

```bash
pip install -r requirements.txt

# или через uv:
uv pip install -r requirements.txt
```

### 2. Внешние сервисы

Перед запуском нужно поднять зависимые сервисы.

**Вариант A — через Docker (отдельные контейнеры):**

```bash
# RabbitMQ
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 \
  rabbitmq:3-management

# Ollama (если используется локально)
docker run -d --name ollama \
  -p 11434:11434 \
  ollama/ollama:latest
```

**Вариант B — всё через Docker Compose:**

```bash
# Поднять только инфраструктуру (без connector/agent)
docker compose up rabbitmq ollama
```

**Вариант C — облачная LLM (без Ollama):**

Установите в `.env`:
```env
LLM_BASE_URL=
LLM_API_KEY=
```

В этом случае Ollama не требуется.

### 3. Запуск микросервисов

```bash
# Коннектор (терминал 1)
AISOC_MODE=connector python main.py

# Агент (терминал 2)
AISOC_MODE=agent python main.py
```

или через uvicorn напрямую:

```bash
uvicorn connector.main:app --host 0.0.0.0 --port 8000 --reload
uvicorn agent.main:app --host 0.0.0.0 --port 8001 --reload
```

---

## Конфигурация

### Переменные окружения

Все настройки задаются через `.env` файл или переменные окружения.

#### RabbitMQ

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `RABBITMQ_HOST` | localhost | Хост RabbitMQ |
| `RABBITMQ_PORT` | 5672 | Порт AMQP |
| `RABBITMQ_USER` | guest | Пользователь |
| `RABBITMQ_PASS` | guest | Пароль |
| `RABBITMQ_QUEUE` | aisoc_alerts | Имя очереди для алертов |

#### LLM (Ollama / облачный провайдер)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `LLM_BASE_URL` | http://localhost:11434/v1 | URL OpenAI-совместимого API |
| `LLM_API_KEY` | *(пусто)* | API-ключ (для Ollama оставить пустым) |
| `SMALL_LLM_MODEL` | gemma2:2b | Модель для категоризации |
| `LARGE_LLM_MODEL` | gemma2:2b | Модель для формирования планов |

**Использование облачных провайдеров:**

Для OpenAI:
```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
SMALL_LLM_MODEL=gpt-4o-mini
LARGE_LLM_MODEL=gpt-4o
```

Для OpenRouter:
```env
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-...
SMALL_LLM_MODEL=openai/gpt-4o-mini
LARGE_LLM_MODEL=anthropic/claude-3.5-sonnet
```

Никаких изменений кода не требуется — всё настраивается через `.env`.

#### Chroma (Vector DB, локальное хранилище)

Chroma работает **внутри процесса агента** с локальным SQLite-хранилищем — отдельный Docker-контейнер не требуется.

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `CHROMA_PERSIST_DIR` | ./chroma_data | Директория для локального Chroma |
| `CHROMA_COLLECTION` | aisoc_playbooks | Имя коллекции |
| `EMBEDDING_MODEL` | nomic-embed-text | Модель эмбеддингов (через Ollama) |

**Примечание:** Для эмбеддингов используется `OllamaEmbeddings` — модель `nomic-embed-text` должна быть скачана в Ollama. При Docker Compose она скачивается автоматически через `ollama-init.sh`.

#### Wazuh (SIEM)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `WAZUH_API_URL` | https://localhost:55000 | URL Wazuh API |
| `WAZUH_API_USER` | wazuh-wui | Пользователь |
| `WAZUH_API_PASS` | wazuh-wui | Пароль |
| `USE_RABBITMQ` | false | Включить RabbitMQ (ставьте `true` для полного пайплайна) |

**Внимание:** Для работы без реального Wazuh просто оставьте переменные Wazuh пустыми — `IndexerClient` будет работать в режиме заглушки.

Инструкцию по развертыванию смотри в документации: https://documentation.wazuh.com/current/deployment-options/docker/wazuh-container.html

#### Сервисы

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `CONNECTOR_HOST` | localhost | Хост Connector |
| `CONNECTOR_PORT` | 8000 | Порт Connector |
| `AGENT_HOST` | localhost | Хост Agent |
| `AGENT_PORT` | 8001 | Порт Agent |

### Пример `.env`

```env
# LLM
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=
SMALL_LLM_MODEL=gemma2:2b
LARGE_LLM_MODEL=gemma2:2b

# RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_QUEUE=aisoc_alerts

# Chroma (локальное хранилище)
CHROMA_PERSIST_DIR=./chroma_data
CHROMA_COLLECTION=aisoc_playbooks

# Эмбеддинги
EMBEDDING_MODEL=nomic-embed-text

# Connector
CONNECTOR_HOST=localhost
CONNECTOR_PORT=8000
USE_RABBITMQ=true

# Agent
AGENT_HOST=localhost
AGENT_PORT=8001
VERBOSE=true

# Wazuh (опционально)
WAZUH_API_URL=https://localhost:55000
WAZUH_API_USER=wazuh-wui
WAZUH_API_PASS=changeme
```

---

## Docker-образы

### Dockerfile.connector

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements-base.txt .
RUN pip install --no-cache-dir --default-timeout=300 --retries=10 -r requirements-base.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "connector.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Dockerfile.agent

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements-base.txt requirements-agent.txt ./
RUN pip install --no-cache-dir --default-timeout=300 --retries=10 -r requirements-agent.txt
COPY . .
EXPOSE 8001
CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

---

## Тестирование

### Прямая отправка в агент (без RabbitMQ)

```bash
curl -X POST "http://localhost:8001/api/v1/process" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-05-14T12:00:00Z",
    "event_id": "test-001",
    "rule_name": "SQL Injection Attempt",
    "rule_level": 10,
    "source_ip": "10.0.0.5",
    "destination_ip": "192.168.1.1",
    "destination_port": 80,
    "message": "Possible SQL injection in /api/users?id=1 OR 1=1"
  }'
```

### Через коннектор (полный пайплайн с RabbitMQ)

```bash
# Убедитесь, что USE_RABBITMQ=true и RabbitMQ запущен

# Опубликовать mock-алерт в очередь (алерт из SIEM)
curl -X POST "http://localhost:8000/api/v1/publish" \
  -H "Content-Type: application/json" \
  -d '{"alert_id": "test-001"}' 

# Получить список алертов
curl "http://localhost:8000/api/v1/alerts"
```

### Через webhook

```bash
curl -X POST "http://localhost:8000/webhook/generic" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-05-14T12:00:00Z",
    "event_id": "wh-001",
    "rule_name": "SQL Injection",
    "rule_level": 10,
    "source_ip": "10.0.0.5",
    "destination_ip": "192.168.1.1",
    "message": "Possible SQL injection"
  }'
```

### Плейбуки

```bash
# Список загруженных плейбуков
curl http://localhost:8001/api/v1/playbooks

# Перезагрузить плейбуки (после редактирования knowledge/*.md)
curl -X POST http://localhost:8001/api/v1/playbooks/reload
```

### Скрипты для работы с Wazuh Indexer

```bash
# Проверить соединение с индексером
python scripts/check_indexer.py

# Добавить тестовые алерты в индексер
python scripts/add_alert.py --count 5 --level 7

# Добавить алерт с указанием правила
python scripts/add_alert.py --rule-name "SSH Brute Force" --level 10
```

### С реальным Wazuh

1. Установите `USE_RABBITMQ=true` в `.env`
2. Укажите корректный `WAZUH_API_URL`, `WAZUH_API_USER`, `WAZUH_API_PASS`
3. Настройте вебхук в Wazuh Dashboard:
   - Configuration → Integration → Webhook
   - URL: `http://<connector-host>:8000/webhook/wazuh`
4. Планы анализа будут отправляться через `POST /security/alerts/context` (пока не реализовано)

---

## Порты

| Порт | Сервис | Назначение |
|------|--------|-----------|
| 5672 | RabbitMQ | AMQP (основной протокол) |
| 15672 | RabbitMQ | Management UI |
| 11434 | Ollama | LLM API (OpenAI-совместимый) |
| 8000 | Connector | FastAPI |
| 8001 | Agent | FastAPI |
| 55000 | Wazuh | Wazuh API (внешний) |

---

## Тома (volumes)

| Volume | Сервис | Путь в контейнере |
|--------|--------|-------------------|
| `rabbitmq_data` | RabbitMQ | `/var/lib/rabbitmq` |
| `ollama_data` | Ollama | `/root/.ollama` |

---

## Обновление и перезапуск

```bash
# Пересобрать и перезапустить
docker compose up --build -d

# Перезагрузить плейбуки через API
curl -X POST "http://localhost:8001/api/v1/playbooks/reload"

# Остановить все
docker compose down

# Остановить и удалить тома (сброс данных)
docker compose down -v
```
