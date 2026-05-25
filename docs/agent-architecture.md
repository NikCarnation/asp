# Agent System: модуль планирования анализа инцидентов

## Роль в системе

Agent System — центральный модуль, отвечающий за интеллектуальную обработку событий информационной безопасности. Он получает нормализованные алерты из очереди RabbitMQ (или напрямую через REST API), категоризирует их, обогащает информацией из базы знаний через RAG и формирует структурированный план анализа инцидента.

```
RabbitMQ ──► Agent System ──► SIEM Dashboard (план анализа)
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
 Categorizer    RAG        Planner
 (Small LLM)  (Chroma)   (Large LLM)
```

---

## Архитектура модуля

```
agent/
├── main.py              # FastAPI-приложение, lifespan, эндпоинты
├── config.py            # Конфигурация (RabbitMQ, LLM, Chroma)
├── pipeline.py          # Оркестратор: категоризация → RAG → планирование
├── categorizer.py       # Small LLM для категоризации типа инцидента
├── planner.py           # Large LLM для формирования плана анализа
├── models/
│   ├── schemas.py       # Pydantic-модели (NormalizedAlert, AnalysisPlan, ...)
│   └── __init__.py
└── rag/
    ├── knowledge_base.py   # Загрузка плейбуков из knowledge/*.md
    ├── vector_store.py     # Клиент Chroma DB для RAG
    └── __init__.py
```

---

## Пайплайн обработки (Pipeline)

`agent/pipeline.py` — класс `AgentPipeline`, оркестрирующий последовательную обработку одного алерта.

### Схема работы

```
NormalizedAlert
      │
      ▼
┌──────────────────────┐
│     CATEGORIZER      │
│  (Small LLM:gemma2)  │
│                      │
│  Alert ──► LLM ──►   │
│  category + conf     │
└──────────┬───────────┘
           ▼
     IncidentCategory
      (category="brute-force")
           │
           ▼
┌──────────────────────┐
│   RAG (VectorStore)  │
│                      │
│  category ──► Chroma │
│  ──► playbooks       │
└──────────┬───────────┘
           ▼
     list[Playbook]
           │
           ▼
┌──────────────────────┐
│      PLANNER         │
│  (Large LLM:gemma2)  │
│                      │
│  alert + category +  │
│  playbooks ──► LLM   │
│  ──► AnalysisPlan    │
└──────────┬───────────┘
           ▼
     AnalysisPlan
      (шаги + markdown)
           │
           ▼
   Возвращается клиенту
   или отправляется в SIEM
```

### Код пайплайна

```python
class AgentPipeline:
    async def process(self, alert: NormalizedAlert) -> AnalysisPlan:
        # 1. Категоризация
        category = await self.categorizer.categorize(alert)

        # 2. Поиск плейбуков по категории
        playbooks = self.vector_store.search(
            category=category.category,
            query=alert.rule_name,
        )

        # Fallback: если Chroma пуста, берём из CATEGORY_PLAYBOOK_MAP
        if not playbooks and category.category in CATEGORY_PLAYBOOK_MAP:
            playbooks = [CATEGORY_PLAYBOOK_MAP[category.category]]

        # 3. Формирование плана (Large LLM + playbooks)
        plan = await self.planner.create_plan(
            alert=alert,
            category=category.category,
            playbooks=playbooks,
        )
        return plan
```

- Если RAG не вернул результат по категории — используется `CATEGORY_PLAYBOOK_MAP` (прямой mapping из `knowledge_base.py`)
- Если категория не найдена — поиск по "unknown"
- При ошибке на любом этапе возвращается `AnalysisPlan` с полем `summary`, содержащим описание ошибки

---

## Категоризатор (Categorizer)

`agent/categorizer.py` — класс `Categorizer`, использующий **малую языковую модель** (по умолчанию `gemma2:2b`) для определения типа инцидента.

### Системный промпт

```text
You are an AI SOC analyst. Your task is to categorize security alerts
into incident types.

Analyze the alert data and determine the most likely incident category.
Return ONLY a JSON object with:
- "category": one of [brute-force, web-exploit, malware, phishing,
  reconnaissance, unauthorized-access, data-exfiltration,
  denial-of-service, policy-violation, unknown]
- "confidence": float between 0.0 and 1.0
- "description": brief explanation of your reasoning
```

### Входные данные для модели

```text
Rule: SSH Brute Force Attack (id=5710, level=7)
Category: authentication
Source: 192.168.1.100:54321
Destination: 10.0.0.5:22
User: root
Process: None
Protocol: tcp
Message: SSHD 5 failed login attempts from 192.168.1.100 to user root
```

### Выходные данные

```json
{
  "category": "brute-force",
  "confidence": 0.95,
  "description": "Multiple failed SSH login attempts from single source"
}
```

### Параметры LLM

| Параметр | Значение |
|----------|----------|
| Модель | `gemma2:2b` (настраивается через `SMALL_LLM_MODEL`) |
| Temperature | 0.1 (низкая — детерминированные ответы) |
| Max tokens | 150 |
| API | OpenAI-совместимый (Ollama / OpenRouter / OpenAI) |
| API Key | Из `LLM_API_KEY` (пустой для Ollama → fallback "ollama") |

- При ошибке парсинга JSON возвращается категория `"unknown"` с `confidence=0.0`

---

## Планировщик (Planner)

`agent/planner.py` — класс `Planner`, использующий **большую языковую модель** (по умолчанию `gemma2:2b`) для создания детального пошагового плана анализа.

### Системный промпт

```text
You are a senior SOC analyst creating an incident investigation plan.

You will receive:
1. A security alert
2. The incident category determined by preliminary analysis
3. Relevant playbook information from the knowledge base

Create a structured investigation plan with specific, actionable steps.
```

### Входные данные

- **Alert**: те же поля, что у категоризатора
- **Category**: результат категоризации (например `"brute-force"`)
- **Playbooks**: от 1 до 3 плейбуков из Chroma (либо fallback из `CATEGORY_PLAYBOOK_MAP`)

### Формат ответа

```json
{
  "summary": "SSH brute force attack from 192.168.1.100 targeting root account",
  "steps": [
    {
      "order": 1,
      "action": "Check source IP reputation",
      "description": "Query VirusTotal and AbuseIPDB for 192.168.1.100",
      "commands": [
        "curl -s https://www.virustotal.com/api/v3/ip_addresses/192.168.1.100",
        "curl -s https://api.abuseipdb.com/api/v2/check?ipAddress=192.168.1.100"
      ],
      "expected_result": "IP reputation score and abuse reports"
    }
  ],
  "raw_markdown": "# Analysis Plan\n## 1. Check source IP reputation..."
}
```

### Параметры LLM

| Параметр | Значение |
|----------|----------|
| Модель | `gemma2:2b` (настраивается через `LARGE_LLM_MODEL`) |
| Temperature | 0.2 |
| Max tokens | 2000 |
| API | OpenAI-совместимый (Ollama / OpenRouter / OpenAI) |
| API Key | Из `LLM_API_KEY` (пустой для Ollama → fallback "ollama") |

- При ошибке возвращается план с описанием ошибки

---

## FastAPI-приложение

`agent/main.py` — точка входа микросервиса.

### Жизненный цикл (lifespan)

```
Старт
  │
  ├─► Categorizer(base_url=LLM_BASE_URL, model=SMALL_LLM_MODEL, api_key=LLM_API_KEY)
  ├─► Planner(base_url=LLM_BASE_URL, model=LARGE_LLM_MODEL, api_key=LLM_API_KEY)
  ├─► VectorStore(host=chroma, collection=aisoc_playbooks)
  │
  ├─► Если Chroma пуста → загрузить ALL_PLAYBOOKS (6 шт.)
  │
  ├─► AgentPipeline(categorizer, planner, vector_store)
  │
  ▼
Ожидание запросов
  │
  ▼
Завершение (shutdown)
```

### API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Статус: модель, количество плейбуков |
| POST | `/api/v1/process` | Обработать алерт (из тела JSON → `NormalizedAlert`) |
| POST | `/api/v1/process/alert` | Обработать уже нормализованный `NormalizedAlert` |
| GET | `/api/v1/playbooks` | Список загруженных плейбуков |
| POST | `/api/v1/playbooks/reload` | Перезагрузить плейбуки (сброс + переиндексация) |

### Обработка алерта через REST

```bash
curl -X POST "http://localhost:8001/api/v1/process" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-05-14T12:00:00Z",
    "event_id": "test-001",
    "rule_name": "SSH Brute Force",
    "rule_level": 7,
    "source_ip": "10.0.0.5",
    "destination_ip": "192.168.1.1",
    "message": "Failed password for root"
  }'
```

Ответ — `AnalysisPlan` в JSON.

---

## Конфигурация Agent System

`agent/config.py` — `AgentConfig` (Pydantic Settings), загружается из `.env`.

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `RABBITMQ_*` | localhost/5672/guest | Настройки RabbitMQ |
| `LLM_BASE_URL` | http://localhost:11434/v1 | URL OpenAI-совместимого API |
| `LLM_API_KEY` | *(пусто)* | API-ключ (для Ollama оставить пустым) |
| `SMALL_LLM_MODEL` | gemma2:2b | Модель для категоризации |
| `LARGE_LLM_MODEL` | gemma2:2b | Модель для планов |
| `CHROMA_HOST` | localhost | Хост Chroma DB |
| `CHROMA_PORT` | 8002 | Порт Chroma DB (внешний) |
| `CHROMA_COLLECTION` | aisoc_playbooks | Имя коллекции в Chroma |
| `AGENT_HOST` | 0.0.0.0 | Хост FastAPI |
| `AGENT_PORT` | 8001 | Порт FastAPI |
| `VERBOSE` | true | Логирование этапов в терминал |
