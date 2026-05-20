# AISOC — AI Agent System for Information Security Event Analysis

Agentная система для автоматизации анализа событий информационной безопасности.

## Архитектура

```
SIEM (Wazuh) → Connector → RabbitMQ → Agent System → SIEM Dashboard
                 (микросервис)           (LLM + RAG)
```

- **Connector** — микросервис для взаимодействия с SIEM. Получает алерты (REST poll + webhook), нормализует в ECS, отправляет в очередь RabbitMQ.
- **Agent System** — получает события из очереди, категоризирует (small LLM: phi3:mini), ищет плейбуки (RAG + Chroma), формирует план анализа (large LLM: llama3.1:8b).
- **RabbitMQ** — брокер сообщений для буферизации и гарантированной доставки.
- **Wazuh** — SIEM система (тестовая среда).
- **База знаний** — векторная БД Chroma с плейбуками по типам инцидентов.

## Быстрый старт

### 1. Требования

- Docker & Docker Compose (рекомендуется)
- Python 3.12+
- Ollama (для локального запуска LLM)

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

### 3. Локальный запуск (без Docker)

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
ollama pull phi3:mini
ollama pull llama3.1:8b
```

## API Endpoints

### Connector (порт 8000)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка здоровья |
| GET | `/api/v1/alerts` | Список алертов из SIEM |
| GET | `/api/v1/alerts/{id}` | Алерт по ID |
| POST | `/api/v1/publish?alert_id=...` | Отправить алерт в очередь |
| POST | `/api/v1/plan/{alert_id}` | Отправить план в SIEM |
| POST | `/webhook/wazuh` | Webhook от Wazuh |
| POST | `/webhook/generic` | Generic webhook |

### Agent (порт 8001)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Проверка здоровья + статус |
| POST | `/api/v1/process` | Обработать алерт (из тела) |
| GET | `/api/v1/playbooks` | Список загруженных плейбуков |
| POST | `/api/v1/playbooks/reload` | Перезагрузить плейбуки |

## Тестирование с Mock Wazuh

По умолчанию система работает в режиме `wazuh_mock=true` (симулированный Wazuh). Это позволяет тестировать полный пайплайн без реального SIEM.

```bash
# Через коннектор — опубликовать mock-алерт в очередь
curl -X POST "http://localhost:8000/api/v1/publish?alert_id=alert-001"

# Или напрямую в агент
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
```

## Плейбуки (база знаний)

Встроенные плейбуки покрывают типы инцидентов:
- `brute-force` — атаки перебором паролей
- `web-exploit` — эксплуатация веб-уязвимостей
- `malware` — вредоносное ПО
- `reconnaissance` — разведка/сканирование
- `unauthorized-access` — несанкционированный доступ
- `policy-violation` — нарушение политик

## Формат плана анализа

План возвращается в двух форматах:
- **JSON** — структурированный массив шагов для интеграции
- **Markdown** — человекочитаемый формат для отображения в дашборде

Пример JSON плана:
```json
{
  "alert_id": "alert-001",
  "incident_category": "brute-force",
  "summary": "SSH brute force attack detected from 192.168.1.100",
  "steps": [
    {
      "order": 1,
      "action": "Check source IP reputation",
      "commands": ["curl -s https://www.virustotal.com/api/v3/ip_addresses/..."],
      "expected_result": "IP reputation score"
    }
  ],
  "raw_markdown": "# Analysis Plan\n## 1. Check source IP reputation\n..."
}
```

## Документация

| Документ | Описание |
|----------|----------|
| [Архитектура](docs/architecture.md) | Общая схема и компоненты системы |
| [Connector](docs/connector-architecture.md) | Интеграция с SIEM: REST API, webhook, нормализация ECS |
| [Agent System](docs/agent-architecture.md) | Категоризация, RAG, планирование, пайплайн |
| [База знаний](docs/knowledge-base.md) | Плейбуки, Chroma DB, RAG-поиск |
| [Модели данных](docs/data-models.md) | Pydantic схемы, ECS, форматы передачи |
| [Развёртывание](docs/deployment.md) | Docker Compose, конфигурация, запуск |

## Конфигурация

Настройки через `.env` файл или переменные окружения (подробнее — [docs/deployment.md](docs/deployment.md)):

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `RABBITMQ_HOST` | localhost | Хост RabbitMQ |
| `RABBITMQ_PORT` | 5672 | Порт RabbitMQ |
| `RABBITMQ_QUEUE` | aisoc_alerts | Имя очереди |
| `OLLAMA_BASE_URL` | http://localhost:11434/v1 | URL Ollama API |
| `SMALL_LLM_MODEL` | phi3:mini | Модель для категоризации |
| `LARGE_LLM_MODEL` | llama3.1:8b | Модель для планов |
| `CHROMA_HOST` | localhost | Хост Chroma |
| `WAZUH_MOCK` | true | Использовать mock SIEM |

## Интеграция с Wazuh

Для подключения к реальному Wazuh:
1. Установите `WAZUH_MOCK=false` в `.env`
2. Укажите `WAZUH_API_URL`, `WAZUH_API_USER`, `WAZUH_API_PASS`
3. Планы анализа будут отправляться через Wazuh API
4. Для отображения в дашборде Wazuh используйте API эндпоинты:
   - GET `/security/alerts/context` для получения контекста с планами

Подробнее — [docs/connector-architecture.md](docs/connector-architecture.md).
