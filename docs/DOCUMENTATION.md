# AISOC — Полная документация

## 1. Общая архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                       AISOC System                                  │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌───────────┐   ┌──────────────┐│
│  │   SIEM   │──▶│  Connector   │──▶│ RabbitMQ  │──▶│    Agent     ││
│  │ (Wazuh)  │◀──│  (FastAPI)   │   │ (Broker)  │   │  (FastAPI)   ││
│  └──────────┘   └──────────────┘   └───────────┘   └──────┬───────┘│
│       ▲                                                    │        │
│       │                         ┌──────────────────────────┘        │
│       │                         │                                    │
│       │                    ┌────▼──────┐  ┌──────────────────┐      │
│       │                    │ Categoriz │  │   RAG + Chroma   │      │
│       │                    │ (Small LLM)│  │   VectorStore    │      │
│       │                    └────┬──────┘  └────────┬─────────┘      │
│       │                         │                  │                │
│       │                    ┌────▼──────┐           │                │
│       └────────────────────┤  Planner  ◄───────────┘                │
│                            │ (Large LLM)│                            │
│                            └────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

### Компоненты

| Компонент | Технология | Порт | Назначение |
|-----------|-----------|------|------------|
| **Connector** | FastAPI + httpx | 8000 | Шлюз к SIEM: получает, нормализует, отправляет в очередь |
| **RabbitMQ** | aio-pika | 5672 | Брокер сообщений для буферизации |
| **Agent** | FastAPI + LangGraph | 8001 | Категоризация → RAG → генерация плана |
| **Chroma** | chromadb | 8002 | Векторная БД для поиска плейбуков |
| **Ollama** | OpenAI API | 11434 | Локальный LLM сервер |

### Поток данных

```
SIEM → Connector → RabbitMQ → Agent → план анализа
                                 │
                  ┌──────────────┼──────────────┐
                  ▼              ▼              ▼
            Categorizer       RAG          Planner
           (ministral-3:8b)  (Chroma)   (qwen3.6:27b)
```

---

## 2. Connector (микросервис) — `/connector/`

### 2.1. Назначение
Отвечает за взаимодействие с SIEM-системой (Wazuh). Получает алерты, нормализует их в ECS-формат и передаёт в RabbitMQ для агента.

### 2.2. Структура модуля

```
connector/
├── main.py                  # FastAPI приложение + lifespan + все эндпоинты
├── config.py                # ConnectorConfig (Pydantic Settings)
├── schemas.py               # Pydantic модели запросов (PublishRequest и др.)
├── broker/
│   └── rabbit.py            # RabbitPublisher + RabbitConsumer
├── normalizer/
│   ├── base.py              # BaseNormalizer (ABC)
│   ├── ecs.py               # ECS модели + normalize_wazuh_alert()
│   └── wazuh/
│       ├── wazuh_base.py    # WazuhAlert, WazuhRule, WazuhAgent — Pydantic модели
│       └── wazuh_normalizer.py  # WazuhNormalizer (полный парсинг в ECSAlert)
├── siem_clients/
│   ├── base.py              # SiemClient (ABC)
│   ├── indexer.py           # IndexerClient — OpenSearch/Wazuh Indexer
│   └── wazuh.py             # WazuhClient — Wazuh Manager API
└── webhook/
    └── listener.py          # POST /webhook/wazuh, POST /webhook/generic
```

### 2.3. Запуск

**Локально:**
```bash
cd /home/carnat10n/fefu/asp
source venv/bin/activate
uvicorn connector.main:app --host 127.0.0.1 --port 8000 --reload
```

**Через Docker:**
```bash
docker compose up connector
```

### 2.4. API Endpoints

#### Health
```
GET /health
→ {"status": "ok", "module": "connector"}
```

#### Получение алертов из SIEM
```
GET /api/v1/alerts?limit=100&offset=0
GET /api/v1/alerts?source_ip=10.0.0.5&rule_level_min=7&rule_level_max=10
GET /api/v1/alerts/{alert_id}
```
Поддерживаемые фильтры: `source_ip`, `destination_ip`, `rule_id`, `rule_level_min`, `rule_level_max`, `protocol`, `user_name`, `agent_id`, `agent_name`, `location`, `rule_groups`, `rule_description`, `full_log`, `start_date`, `end_date`.

#### Публикация в очередь
```
POST /api/v1/publish
Body: {"alert_id": "alert-001"}

POST /api/v1/publish/batch
Body: {"alert_ids": ["alert-001", "alert-002"]}

POST /api/v1/publish/date-range?start_date=2026-05-01T00:00:00Z&end_date=2026-05-14T23:59:59Z&limit=100
```

#### Отправка плана в SIEM
```
POST /api/v1/plan/{alert_id}
Body: {"plan": {...}}
```

#### Webhook (push-режим)
```
POST /webhook/wazuh         — сырой алерт Wazuh → нормализация → очередь
POST /webhook/generic       — уже нормализованный NormalizedAlert → очередь
```

#### Прямой приём
```
POST /api/v1/alerts/direct
Body: {сырой Wazuh JSON или NormalizedAlert}
```

### 2.5. Конфигурация (ConnectorConfig)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `USE_RABBITMQ` | `false` | Включить RabbitMQ |
| `RABBITMQ_HOST` | `localhost` | Хост RabbitMQ |
| `RABBITMQ_PORT` | `5672` | Порт RabbitMQ |
| `RABBITMQ_USER` | `guest` | Пользователь |
| `RABBITMQ_PASS` | `guest` | Пароль |
| `RABBITMQ_QUEUE` | `aisoc_alerts` | Имя очереди |
| `WAZUH_API_URL` | — | URL Wazuh Manager API |
| `WAZUH_API_USER` | — | Пользователь Wazuh API |
| `WAZUH_API_PASS` | — | Пароль Wazuh API |
| `WAZUH_API_INDEXER_URL` | `https://localhost:9200` | URL Wazuh Indexer (OpenSearch) |
| `WAZUH_API_INDEXER_USER` | `admin` | Пользователь Indexer |
| `WAZUH_API_INDEXER_PASS` | — | Пароль Indexer |
| `WAZUH_API_INDEXER_ALERT` | `wazuh-alerts-4.x-` | Префикс индекса |
| `CONNECTOR_HOST` | `0.0.0.0` | Хост FastAPI |
| `CONNECTOR_PORT` | `8000` | Порт FastAPI |

---

## 3. Agent (модуль планирования) — `/agent/`

### 3.1. Назначение
Получает алерт из RabbitMQ или через REST API, прогоняет через три этапа:
1. **Категоризация** (Small LLM) — определяет тип инцидента
2. **RAG** (Chroma DB) — ищет релевантные плейбуки
3. **Планирование** (Large LLM) — формирует пошаговый план анализа

### 3.2. Структура модуля

```
agent/
├── main.py                  # FastAPI приложение + lifespan + RabbitMQ consumer
├── config.py                # AgentConfig (Pydantic Settings)
├── agent.py                 # LangGraph StateGraph (categorize → retrieve → plan)
├── pipeline.py              # AgentPipeline — обёртка над графом
├── categorizer.py           # Categorizer — Small LLM (with_structured_output)
├── planner.py               # Planner — Large LLM (with_structured_output)
├── models/
│   └── schemas.py           # NormalizedAlert, IncidentCategory, PlanStep, AnalysisPlan
└── rag/
    ├── knowledge_base.py    # Загрузка плейбуков из knowledge/*.md
    └── vector_store.py      # ChromaDB клиент
```

### 3.3. LangGraph pipeline (`agent/agent.py`)

```
                  ┌──────────────┐
                  │    START     │
                  └──────┬───────┘
                         │
                  ┌──────▼───────┐
                  │  categorize  │  Small LLM → IncidentCategory
                  │  ⏱  ~2-5s   │
                  └──────┬───────┘
                         │
                  ┌──────▼───────┐
                  │   retrieve   │  Chroma DB → list[Playbook]
                  │  ⏱  <0.1s   │
                  └──────┬───────┘
                         │
                  ┌──────▼───────┐
                  │     plan     │  Large LLM → AnalysisPlan
                  │  ⏱  ~10-30s │
                  └──────┬───────┘
                         │
                  ┌──────▼───────┐
                  │     END      │
                  └──────────────┘
```

Каждый узел логирует свою работу с таймингом. Логирование включается/выключается флагом `VERBOSE` в `.env`.

### 3.4. Запуск

**Локально (требуются Ollama + Chroma + RabbitMQ):**
```bash
cd /home/carnat10n/fefu/asp
source venv/bin/activate
uvicorn agent.main:app --host 127.0.0.1 --port 8001 --reload
```

**Через Docker:**
```bash
docker compose up agent
```

### 3.5. API Endpoints

```
GET  /health              → статус, кол-во плейбуков, модели
POST /api/v1/process      → обработать алерт (принимает dict)
POST /api/v1/process/alert → обработать алерт (принимает NormalizedAlert)
GET  /api/v1/playbooks    → список всех плейбуков
POST /api/v1/playbooks/reload → перезагрузить плейбуки в Chroma
```

### 3.6. Конфигурация (AgentConfig)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `RABBITMQ_HOST` | `localhost` | Хост RabbitMQ |
| `RABBITMQ_PORT` | `5672` | Порт RabbitMQ |
| `RABBITMQ_USER` | `guest` | Пользователь |
| `RABBITMQ_PASS` | `guest` | Пароль |
| `RABBITMQ_QUEUE` | `aisoc_alerts` | Имя очереди |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | URL Ollama API |
| `SMALL_LLM_MODEL` | `ministral-3:8b` | Модель для категоризации |
| `LARGE_LLM_MODEL` | `qwen3.6:27b` | Модель для планов |
| `CHROMA_HOST` | `localhost` | Хост Chroma |
| `CHROMA_PORT` | `8002` | Порт Chroma API |
| `CHROMA_COLLECTION` | `aisoc_playbooks` | Имя коллекции |
| `AGENT_HOST` | `0.0.0.0` | Хост FastAPI |
| `AGENT_PORT` | `8001` | Порт FastAPI |
| `VERBOSE` | `true` | Логирование этапов в терминал |

---

## 4. Модули Agent в деталях

### 4.1. Categorizer (`agent/categorizer.py`)

Использует `langchain_openai.ChatOpenAI.with_structured_output(IncidentCategory)`.

- **Модель:** `ministral-3:8b` (Small LLM)
- **Temperature:** 0.1 (низкая — детерминированные ответы)
- **Max tokens:** 150
- **Системный промпт:** инструктирует LLM категоризировать алерты
- **Структура ответа:** `IncidentCategory(category, confidence, description)`
- **Ошибка:** возвращает `unknown` с `confidence=0.0`

**Категории:**
```
brute-force, web-exploit, malware, phishing,
reconnaissance, unauthorized-access, data-exfiltration,
denial-of-service, policy-violation, unknown
```

### 4.2. RAG + Vector Store (`agent/rag/`)

Два слоя поиска плейбуков:
1. **Chroma DB** — семантический поиск по категории и тексту правила (`vector_store.search()`)
2. **Fallback** — `CATEGORY_PLAYBOOK_MAP` (прямой mapping из `knowledge_base.py`) если Chroma пуста
3. **Unknown** — поиск по категории "unknown", если категория не найдена

### 4.3. База знаний (`agent/rag/knowledge_base.py`)

Плейбуки загружаются из markdown-файлов в директории `knowledge/`:
- Имя файла → категория (напр. `brute-force.md` → `"brute-force"`)
- Первая строка `# ...` → заголовок
- Весь файл → содержимое плейбука

**Доступные плейбуки:**

| Файл | Категория | Содержание |
|------|-----------|------------|
| `brute-force.md` | brute-force | Атаки перебором паролей |
| `web-exploit.md` | web-exploit | Эксплуатация веб-уязвимостей |
| `malware.md` | malware | Вредоносное ПО |
| `reconnaissance.md` | reconnaissance | Разведка и сканирование |
| `unauthorized-access.md` | unauthorized-access | Несанкционированный доступ |
| `policy-violation.md` | policy-violation | Нарушение политик |

### 4.4. Planner (`agent/planner.py`)

Использует `langchain_openai.ChatOpenAI.with_structured_output(_PlanOutput)`.

- **Модель:** `qwen3.6:27b` (Large LLM)
- **Temperature:** 0.2
- **Max tokens:** 2000
- **На вход:** алерт + категория + плейбуки
- **На выходе:** `AnalysisPlan` со summary, steps (с командами), raw_markdown
- **Ошибка:** возвращает план с шагом "Manual Analysis Required"

---

## 5. Модели данных (`agent/models/schemas.py`)

### NormalizedAlert
```python
class NormalizedAlert(BaseModel):
    timestamp: datetime
    event_id: str
    event_kind: str = "alert"
    event_category: str = "unknown"
    event_type: str = "unknown"
    event_severity: int = 0
    rule_id: str = ""
    rule_name: str = ""
    rule_level: int = 0
    rule_description: str = ""
    source_ip: str | None = None
    source_port: int | None = None
    destination_ip: str | None = None
    destination_port: int | None = None
    user_name: str | None = None
    process_name: str | None = None
    network_protocol: str | None = None
    message: str = ""
    ecs_version: str = "8.11.0"
    raw: dict = {}
```

### IncidentCategory
```python
class IncidentCategory(BaseModel):
    category: str
    confidence: float
    description: str = ""
```

### PlanStep
```python
class PlanStep(BaseModel):
    order: int
    action: str
    description: str
    commands: list[str] = []
    expected_result: str = ""
```

### AnalysisPlan
```python
class AnalysisPlan(BaseModel):
    alert_id: str
    incident_category: str
    created_at: datetime
    summary: str
    steps: list[PlanStep]
    raw_markdown: str = ""
```

### Playbook
```python
class Playbook(BaseModel):
    title: str
    category: str
    content: str
    source: str | None = None
```

---

## 6. Запуск полного стека

### 6.1. Предварительные требования

- Python 3.12+
- Docker (для RabbitMQ и Chroma) — или запущенный вручную RabbitMQ + Chroma
- Ollama с моделями

### 6.2. Установка зависимостей

```bash
cd /home/carnat10n/fefu/asp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 6.3. Настройка `.env`

```bash
cp .env.example .env
# отредактировать под своё окружение
```

Ключевые параметры:
```env
# LLM
OLLAMA_BASE_URL=http://localhost:11434/v1
SMALL_LLM_MODEL=ministral-3:8b      # или phi3:mini
LARGE_LLM_MODEL=qwen3.6:27b         # или llama3.1:8b

# RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
USE_RABBITMQ=true

# Агент
VERBOSE=true

# Chroma
CHROMA_HOST=localhost
CHROMA_PORT=8002
```

### 6.4. Запуск зависимостей (Docker)

```bash
# RabbitMQ
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management

# Chroma
docker run -d --name chroma -p 8002:8000 chromadb/chroma:latest
```

### 6.5. Запуск Ollama

```bash
# Проверить, что Ollama запущен
ollama serve

# Скачать модели (если ещё нет)
ollama pull ministral-3:8b
ollama pull qwen3.6:27b

# Проверить GPU
nvidia-smi
# Во время работы модели должен появиться процесс ollama с GPU Memory > 0
```

### 6.6. Запуск микросервисов

**Терминал 1 — Connector:**
```bash
cd /home/carnat10n/fefu/asp
source venv/bin/activate
uvicorn connector.main:app --host 127.0.0.1 --port 8000 --reload
```

**Терминал 2 — Agent:**
```bash
cd /home/carnat10n/fefu/asp
source venv/bin/activate
uvicorn agent.main:app --host 127.0.0.1 --port 8001 --reload
```

### 6.7. Запуск через Docker Compose

```bash
docker compose up --build
```

> **Важно:** Ollama в compose закомментирован. Если нужен в Docker — раскомментируйте раздел `ollama` в `docker-compose.yml`.

---

## 7. Тестирование

### 7.1. Проверка здоровья

```bash
curl http://127.0.0.1:8000/health     # Connector
curl http://127.0.0.1:8001/health     # Agent
```

### 7.2. Прямая отправка алерта в агент (без SIEM)

```bash
curl -X POST "http://127.0.0.1:8001/api/v1/process" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-05-14T12:00:00Z",
    "event_id": "test-001",
    "rule_name": "SSH Brute Force Attack",
    "rule_level": 7,
    "source_ip": "10.0.0.5",
    "destination_ip": "192.168.1.1",
    "destination_port": 22,
    "user_name": "root",
    "network_protocol": "tcp",
    "message": "Failed password for root from 10.0.0.5 port 22"
  }'
```

Ответ — план анализа в JSON.
В терминале агента — пошаговый лог с таймингом.

### 7.3. Отправка через коннектор (полный пайплайн)

```bash
# Получить алерт из SIEM и опубликовать в очередь
curl -X POST "http://127.0.0.1:8000/api/v1/publish" \
  -H "Content-Type: application/json" \
  -d '{"alert_id": "test-001"}'
```

### 7.4. Webhook

```bash
curl -X POST "http://127.0.0.1:8000/webhook/generic" \
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

### 7.5. Проверка плейбуков

```bash
curl http://127.0.0.1:8001/api/v1/playbooks
```

### 7.6. Скрипты для работы с Wazuh Indexer

```bash
# Проверить соединение с индексером
python scripts/check_indexer.py

# Добавить тестовые алерты в индексер
python scripts/add_alert.py --count 5 --level 7
```

---

## 8. Docker Compose

```yaml
services:
  rabbitmq:
    image: rabbitmq:3-management
    ports: ["5672:5672", "15672:15672"]

  chroma:
    image: chromadb/chroma:latest
    ports: ["8002:8000"]

  connector:
    build: {context: ., dockerfile: Dockerfile.connector}
    ports: ["8000:8000"]
    depends_on: [rabbitmq]

  agent:
    build: {context: ., dockerfile: Dockerfile.agent}
    ports: ["8001:8001"]
    depends_on: [rabbitmq, chroma]
```

Запуск:
```bash
docker compose up --build
```

---

## 9. Пример вывода агента

При `VERBOSE=true` в терминал выводится:

```
────────────────────────────────────────────────────────────
  STAGE 1: CATEGORIZER
────────────────────────────────────────────────────────────
  Input alert:
    Rule: SSH Brute Force Attack (level=7)
    Source: 10.0.0.5 → 192.168.1.1
    Message: Failed password for root from 10.0.0.5 port 22

  Output category:
    category: brute-force (confidence: 0.95)
  ⏱  3.2s
────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────
  STAGE 2: RAG (Knowledge Base)
────────────────────────────────────────────────────────────
  Query: category=brute-force, rule=SSH Brute Force Attack
  Source: Chroma DB
  Results: 1 playbook(s) found
    • Brute Force Attack Analysis Playbook (1248 chars)
  ⏱  0.1s
────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────
  STAGE 3: PLANNER
────────────────────────────────────────────────────────────
  Category: brute-force
  Playbooks: 1
  Generating plan...

  ─── RESULT: AnalysisPlan ───
  Summary: SSH brute force attack from 10.0.0.5 targeting root account
  Steps:
    1. Check source IP reputation
    2. Review authentication logs
    3. Block offending IP on firewall
  ⏱  15.4s
────────────────────────────────────────────────────────────

════════════════════════════════════════════════════════════
  TOTAL: test-001 — brute-force
  ⏱  18.7s total
════════════════════════════════════════════════════════════
```

---

## 10. Расширение системы

### Добавить новый плейбук
1. Создать `knowledge/название-категории.md`
2. Перезагрузить плейбуки:
```bash
curl -X POST http://127.0.0.1:8001/api/v1/playbooks/reload
```

### Подключить другую SIEM
1. Создать класс-наследник `SiemClient` (как `IndexerClient`)
2. Реализовать `fetch_alerts()`, `get_alert_by_id()`, `send_plan()`
3. Зарегистрировать в `connector/main.py`

### Использовать OpenRouter вместо Ollama
1. Установить `OPENROUTER_API_KEY` в `.env`
2. Добавить `OPENROUTER_BASE_URL`
3. Изменить `api_key` и `base_url` в `Categorizer` и `Planner`

---

## 11. Справочник по файлам

| Файл | Строк | Назначение |
|------|-------|------------|
| `agent/main.py` | 126 | FastAPI + RabbitMQ consumer |
| `agent/agent.py` | 129 | LangGraph pipeline |
| `agent/categorizer.py` | 44 | Категоризация алертов |
| `agent/planner.py` | 86 | Генерация плана |
| `agent/pipeline.py` | 38 | Обёртка над графом |
| `agent/config.py` | 24 | Конфигурация агента |
| `agent/models/schemas.py` | 50 | Модели данных |
| `agent/rag/knowledge_base.py` | 34 | Загрузка плейбуков |
| `agent/rag/vector_store.py` | 76 | ChromaDB клиент |
| `connector/main.py` | 264 | FastAPI + эндпоинты |
| `connector/config.py` | 31 | Конфигурация коннектора |
| `connector/broker/rabbit.py` | 67 | RabbitMQ publisher/consumer |
| `connector/siem_clients/indexer.py` | 173 | OpenSearch клиент |
| `connector/siem_clients/wazuh.py` | 134 | Wazuh API клиент |
| `connector/normalizer/ecs.py` | 131 | ECS нормализация |
| `connector/normalizer/wazuh/wazuh_normalizer.py` | 192 | Wazuh→ECS парсер |
| `connector/webhook/listener.py` | 51 | Webhook эндпоинты |
| `knowledge/*.md` | ~27 | Плейбуки (6 шт.) |
| `.env` | 37 | Конфигурация окружения |
| `docker-compose.yml` | 87 | Оркестрация контейнеров |
| `requirements.txt` | 16 | Python зависимости |
| `main.py` | 54 | Точка входа |
