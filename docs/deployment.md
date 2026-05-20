# Развёртывание и конфигурация AISOC

## Требования

### Минимальные
- **CPU**: 4+ ядра (рекомендуется 8)
- **RAM**: 8+ ГБ (из них ~4 ГБ для Ollama с llama3.1:8b)
- **Диск**: 10+ ГБ свободного места
- **Docker** и **Docker Compose** (рекомендуется)
- **Python 3.12+** (для локального запуска)

### Опционально
- **GPU** (NVIDIA) — для ускорения инференса LLM через Ollama
- **NVIDIA Container Toolkit** — для проброса GPU в Docker

---

## Запуск через Docker Compose

### 1. Клонирование

```bash
git clone <repo-url> aisoc
cd aisoc
```

### 2. Настройка

Скопировать `.env.example` в `.env` и отредактировать при необходимости:

```bash
cp .env.example .env
```

### 3. Запуск

```bash
docker compose up --build
```

Будут запущены 5 контейнеров:

| Сервис | Порт (внешний) | Зависимости |
|--------|---------------|-------------|
| RabbitMQ | 5672, 15672 | — |
| Ollama | 11434 | — |
| Chroma | 8002 | — |
| Connector | 8000 | RabbitMQ |
| Agent | 8001 | RabbitMQ, Ollama, Chroma |

### 4. Инициализация моделей Ollama

После запуска Ollama нужно скачать модели:

```bash
# Установить модели внутри контейнера
docker exec -it aisoc-ollama-1 ollama pull phi3:mini
docker exec -it aisoc-ollama-1 ollama pull llama3.1:8b
```

Или через порт 11434:

```bash
curl http://localhost:11434/api/pull -d '{"name": "phi3:mini"}'
curl http://localhost:11434/api/pull -d '{"name": "llama3.1:8b"}'
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

# Chroma (REST API)
curl http://localhost:8002/api/v1/heartbeat
# → {"nanosecond heartbeat": ...}
```

---

## Локальный запуск (без Docker)

### 1. Зависимости

```bash
pip install -r requirements.txt

# Или через poetry/uv:
uv pip install -r requirements.txt
```

### 2. Внешние сервисы

Перед запуском нужно поднять зависимые сервисы:

```bash
# RabbitMQ
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 \
  rabbitmq:3-management

# Ollama
docker run -d --name ollama \
  -p 11434:11434 \
  ollama/ollama:latest

# Chroma
docker run -d --name chroma \
  -p 8002:8000 \
  chromadb/chroma:latest
```

### 3. Запуск микросервисов

```bash
# Коннектор (в терминале 1)
AISOC_MODE=connector python main.py

# Агент (в терминале 2)
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

#### LLM (Ollama)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `OLLAMA_BASE_URL` | http://localhost:11434/v1 | URL OpenAI-совместимого API |
| `SMALL_LLM_MODEL` | phi3:mini | Модель для категоризации |
| `LARGE_LLM_MODEL` | llama3.1:8b | Модель для формирования планов |

**OpenRouter (опционально):**

В `.env.example` также закомментированы настройки для OpenRouter:
```bash
# LLM_PROVIDER=openrouter
# OPENROUTER_API_KEY=sk-or-v1-...
# OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

Для использования OpenRouter вместо Ollama нужно:
1. Раскомментировать эти переменные в `.env`
2. Модифицировать `AsyncOpenAI(base_url=..., api_key=...)` в `categorizer.py` и `planner.py` (сейчас всегда использует `api_key="ollama"`)

#### Chroma (Vector DB)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `CHROMA_HOST` | localhost | Хост Chroma |
| `CHROMA_PORT` | 8000 | Порт Chroma API |
| `CHROMA_COLLECTION` | aisoc_playbooks | Имя коллекции |

#### Wazuh (SIEM)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `WAZUH_API_URL` | http://localhost:55000 | URL Wazuh API |
| `WAZUH_API_USER` | wazuh-wui | Пользователь |
| `WAZUH_API_PASS` | wazuh-wui | Пароль |
| `WAZUH_MOCK` | true | Использовать Mock-клиент вместо реального Wazuh |

#### Сервисы

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `CONNECTOR_HOST` | 0.0.0.0 | Хост Connector |
| `CONNECTOR_PORT` | 8000 | Порт Connector |
| `AGENT_HOST` | 0.0.0.0 | Хост Agent |
| `AGENT_PORT` | 8001 | Порт Agent |

### Пример `.env`

```bash
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_QUEUE=aisoc_alerts

OLLAMA_BASE_URL=http://localhost:11434/v1
SMALL_LLM_MODEL=phi3:mini
LARGE_LLM_MODEL=llama3.1:8b

WAZUH_API_URL=http://localhost:55000
WAZUH_API_USER=wazuh-wui
WAZUH_API_PASS=wazuh-wui
WAZUH_MOCK=true

CONNECTOR_HOST=0.0.0.0
CONNECTOR_PORT=8000
AGENT_HOST=0.0.0.0
AGENT_PORT=8001

CHROMA_HOST=localhost
CHROMA_PORT=8000
CHROMA_COLLECTION=aisoc_playbooks
```

---

## Docker-образы

### Dockerfile.connector

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "connector.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Dockerfile.agent

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8001
CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

---

## Тестирование

### С Mock Wazuh (по умолчанию)

```bash
# Опубликовать mock-алерт в очередь
curl -X POST "http://localhost:8000/api/v1/publish?alert_id=alert-001"

# Получить список алертов
curl "http://localhost:8000/api/v1/alerts"

# Напрямую передать алерт в агент
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

### С реальным Wazuh

1. Установите `WAZUH_MOCK=false` в `.env`
2. Укажите корректный `WAZUH_API_URL`, `WAZUH_API_USER`, `WAZUH_API_PASS`
3. Настройте вебхук в Wazuh Dashboard:
   - Configuration → Integration → Webhook
   - URL: `http://<connector-host>:8000/webhook/wazuh`
   - Правила: выберите уровни (например ≥ 7)
4. Планы анализа будут отправляться через `POST /security/alerts/context`

---

## Порты

| Порт | Сервис | Назначение |
|------|--------|-----------|
| 5672 | RabbitMQ | AMQP (основной протокол) |
| 15672 | RabbitMQ | Management UI |
| 11434 | Ollama | LLM API (OpenAI-совместимый) |
| 8000 | Connector | FastAPI |
| 8001 | Agent | FastAPI |
| 8002 | Chroma | Vector DB API |
| 55000 | Wazuh | Wazuh API (внешний) |

---

## Тома (volumes)

| Volume | Сервис | Путь в контейнере |
|--------|--------|-------------------|
| `rabbitmq_data` | RabbitMQ | `/var/lib/rabbitmq` |
| `ollama_data` | Ollama | `/root/.ollama` |
| `chroma_data` | Chroma | `/chroma/chroma` |

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
