# Архитектура AISOC

## Общая схема

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AISOC System                                 │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌───────────┐   ┌─────────────┐ │
│  │   SIEM   │──▶│  Connector   │──▶│ RabbitMQ  │──▶│    Agent    │ │
│  │ (Wazuh)  │◀──│  (FastAPI)   │   │ (Broker)  │   │  (FastAPI)  │ │
│  └──────────┘   └──────────────┘   └───────────┘   └──────┬──────┘ │
│       ▲                                                    │        │
│       │                         ┌──────────────────────────┘        │
│       │                         │                                    │
│       │                    ┌────▼──────┐  ┌──────────────────┐      │
│       │                    │ Categoriz │  │     RAG +        │      │
│       │                    │ (Small LLM)│  │  VectorStore     │      │
│       │                    └────┬──────┘  │  (Chroma DB)     │      │
│       │                         │         └────────┬─────────┘      │
│       │                    ┌────▼──────┐           │                │
│       └────────────────────┤  Planner  ◄───────────┘                │
│                            │ (Large LLM)│                            │
│                            └────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

## Компоненты системы

### 1. Connector (микросервис, порт 8000)

Отвечает за взаимодействие с SIEM. Реализует два способа получения событий:

| Режим | Направление | Применение |
|-------|-----------|------------|
| REST API Polling | Agent → SIEM | Получение списка алертов, контекста по ID, публикация по запросу |
| Webhook | SIEM → Agent | Мгновенное получение новых алертов от SIEM |

Выполняет нормализацию сырых событий в формат **ECS (Elastic Common Schema)**.

**Ключевые файлы:**
- `connector/main.py` — FastAPI-приложение, маршруты
- `connector/siem_clients/wazuh.py` — WazuhClient (+ MockWazuhClient)
- `connector/normalizer/ecs.py` — нормализация Wazuh → ECS
- `connector/broker/rabbit.py` — RabbitPublisher
- `connector/webhook/listener.py` — webhook-эндпоинты

### 2. RabbitMQ (брокер сообщений)

Буферизирует поток алертов между Connector и Agent. Обеспечивает:

- Гарантированную доставку (persistent messages + durable queue)
- Буферизацию при пиковых нагрузках (очередь)
- Асинхронную связь сервисов

**Очередь:** `aisoc_alerts` (durable)

### 3. Agent System (микросервис, порт 8001)

Интеллектуальный модуль анализа. Состоит из трёх подсистем:

| Подсистема | Компонент | Технология |
|-----------|-----------|-----------|
| Категоризация | Small LLM | phi3:mini (2.7B params) |
| База знаний | Vector Store | Chroma DB + семантический поиск |
| Планирование | Large LLM | llama3.1:8b (8B params) |

**Ключевые файлы:**
- `agent/pipeline.py` — оркестратор пайплайна
- `agent/categorizer.py` — категоризация через малую LLM
- `agent/planner.py` — формирование плана через большую LLM
- `agent/rag/vector_store.py` — клиент Chroma DB
- `agent/rag/knowledge_base.py` — встроенные плейбуки

### 4. База знаний (Chroma DB)

Векторная база данных для RAG-поиска. Хранит 6 плейбуков по категориям инцидентов.

### 5. SIEM (Wazuh)

Тестовая среда. Может быть заменена на любую SIEM через реализацию `SiemClient`.

---

## Пайплайн обработки события

```
1. SIEM генерирует алерт (или MockWazuh)
2. Connector получает алерт (REST poll или webhook)
3. Нормализация события в ECS (NormalizedAlert)
4. Публикация в RabbitMQ (JSON)
5. Agent получает событие из очереди
6. Small LLM категоризирует тип инцидента
7. RAG-запрос к Chroma DB — поиск плейбуков по категории
8. Large LLM формирует пошаговый план анализа
9. План возвращается клиенту / отправляется в SIEM
```

```
Время:  t0         t1          t2          t3           t4          t5
         │          │           │           │            │           │
Событие: SIEM ──► Connector ──► RabbitMQ ──► Categorizer ──► RAG ──► Planner ──► План
         (alert)   (normalize)  (queue)     (small LLM)   (Chroma)  (large LLM)
```

## Технологический стек

| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Язык | Python | 3.12+ |
| API-фреймворк | FastAPI | ≥0.115 |
| Брокер сообщений | RabbitMQ (aio-pika) | ≥9.0 |
| Векторная БД | Chroma DB | ≥0.5 |
| Малая LLM | phi3:mini (Ollama) | — |
| Большая LLM | llama3.1:8b (Ollama) | — |
| HTTP-клиент | httpx | ≥0.27 |
| Конфигурация | Pydantic Settings | ≥2.0 |
| Контейнеризация | Docker Compose | — |

## Взаимодействие сервисов

```
Connector ──port 8000──► RabbitMQ ──port 5672──► Agent ──port 8001
     │                                               │
     │  pull: GET /security/alerts                   │
     │  push: POST /webhook/wazuh                    │  LLM: Ollama:11434
     │  plan: POST /security/alerts/context           │  RAG: Chroma:8000
     │                                               │
     ▼                                               ▼
  Wazuh API                                      Ollama / Chroma
```

## Документация модулей

- [Connector (интеграция с SIEM)](connector-architecture.md)
- [Agent System (обработка алертов)](agent-architecture.md)
- [База знаний и RAG](knowledge-base.md)
- [Модели данных](data-models.md)
- [Развёртывание и конфигурация](deployment.md)
- [План разработки](plan.md)
