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
│       │                    │ Categoriz │  │    RAG +         │      │
│       │                    │ (Small LLM)│  │  VectorStore     │      │
│       │                    └────┬──────┘  │(локальный Chroma)│      │
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
| REST API Polling | Connector → SIEM | Получение списка алертов, контекста по ID, публикация по запросу |
| Webhook | SIEM → Connector | Мгновенное получение новых алертов от SIEM |

Выполняет нормализацию сырых событий в формат **ECS (Elastic Common Schema)**.

**Ключевые файлы:**
- `connector/main.py` — FastAPI-приложение, маршруты
- `connector/siem_clients/indexer.py` — IndexerClient (Wazuh Indexer / OpenSearch)
- `connector/siem_clients/wazuh.py` — WazuhClient (Wazuh Manager API)
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
| Категоризация | Small LLM | OpenAI-совместимая модель (Ollama / облачный провайдер) |
| База знаний | Vector Store | Chroma DB + семантический поиск |
| Планирование | Large LLM | OpenAI-совместимая модель (Ollama / облачный провайдер) |

**Ключевые файлы:**
- `agent/pipeline.py` — оркестратор пайплайна
- `agent/categorizer.py` — категоризация через малую LLM
- `agent/planner.py` — формирование плана через большую LLM
- `agent/rag/vector_store.py` — векторное хранилище (langchain_chroma + OllamaEmbeddings)
- `agent/rag/knowledge_base.py` — загрузка плейбуков из `knowledge/*.md`

### 4. База знаний (векторное хранилище)

Локальное Chroma-хранилище (SQLite) на базе `langchain_chroma` с эмбеддингами через Ollama. Хранит плейбуки, разбитые на семантические чанки, по категориям инцидентов. **Не требует отдельного Docker-контейнера.**

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
7. RAG-запрос к векторному хранилищу — поиск плейбуков (MMR + обогащённый запрос)
8. Large LLM формирует пошаговый план анализа
9. План возвращается клиенту / отправляется в SIEM
```

```
Время:  t0         t1          t2          t3           t4          t5
         │          │           │           │            │           │
Событие: SIEM ──► Connector ──► RabbitMQ ──► Categorizer ──► RAG ──► Planner ──► План
          (alert)   (normalize)  (queue)     (small LLM)   (VectorStore)  (large LLM)
```

## Технологический стек

| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Язык | Python | 3.12+ |
| API-фреймворк | FastAPI | ≥0.115 |
| Брокер сообщений | RabbitMQ (aio-pika) | ≥9.0 |
| Векторная БД | Chroma (langchain_chroma, локальный SQLite) | ≥0.2 (langchain-chroma) |
| Малая LLM | gemma2:2b / любая OpenAI-совместимая | Через Ollama или облачного провайдера |
| Большая LLM | gemma2:2b / любая OpenAI-совместимая | Через Ollama или облачного провайдера |
| HTTP-клиент | httpx | ≥0.27 |
| Конфигурация | Pydantic Settings | ≥2.0 |
| Контейнеризация | Docker Compose | — |

## Взаимодействие сервисов

```
Connector ──port 8000──► RabbitMQ ──port 5672──► Agent ──port 8001
     │                                               │
     │  pull: GET /security/alerts                   │
     │  push: POST /webhook/wazuh                    │  LLM: LLM_BASE_URL
     │  plan: POST /security/alerts/context                 │  RAG: локальный Chroma (SQLite) 
     │                                               │
     ▼                                               ▼
   Wazuh API                                      LLM / VectorStore
```

## Документация модулей

- [Connector (интеграция с SIEM)](connector-architecture.md)
- [Agent System (обработка алертов)](agent-architecture.md)
- [База знаний и RAG](knowledge-base.md)
- [Модели данных](data-models.md)
- [Развёртывание и конфигурация](deployment.md)
- [План разработки](plan.md)
