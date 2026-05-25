# План разработки агентной системы анализа событий ИБ

## 1. Архитектура системы

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│    SIEM      │────▶│   Connector     │────▶│  Message Broker  │
│  (Wazuh)     │◀────│  (микросервис)  │     │  (RabbitMQ)      │
└──────────────┘     └─────────────────┘     └────────┬─────────┘
                                          ┌────────────▼─────────┐
                                          │   Agent System        │
                                          │  ┌─────────────────┐  │
                                          │  │  Categorizer    │  │
                                          │  │  (Small LLM)    │  │
                                          │  ├─────────────────┤  │
                                          │  │  RAG Module     │  │
                                          │  │  (Vector DB)    │  │
                                          │  ├─────────────────┤  │
                                          │  │  Planner        │  │
                                          │  │  (Large LLM)    │  │
                                          │  └─────────────────┘  │
                                          └───────────────────────┘
                                                      │
                                                      ▼
                                          ┌──────────────────┐
                                          │  SIEM Dashboard  │
                                          │  (вывод плана)   │
                                          └──────────────────┘
```

## 2. Технологический стек

| Компонент | Технология | Альтернативы |
|-----------|-----------|--------------|
| Язык | Python 3.12 | — |
| API-фреймворк | FastAPI | Flask |
| Брокер сообщений | RabbitMQ | Kafka |
| Векторная БД | Chroma | Qdrant, FAISS |
| Small LLM | gemma2:2b / любая OpenAI-совместимая | Через Ollama или облачного провайдера |
| Large LLM | gemma2:2b / любая OpenAI-совместимая | Через Ollama или облачного провайдера |
| Нормализация | ECS (Elastic Common Schema) | — |
| SIEM | Wazuh (тестовый стенд) | — |
| Дашборд | Wazuh Custom Dashboard | — |
| Контейнеризация | Docker + Docker Compose | — |

## 3. Структура проекта

```
aisoc/
├── main.py                    # Точка входа (оркестратор, AISOC_MODE)
├── docker-compose.yml
├── .env
├── requirements.txt
├── pyproject.toml
├── connector/                 # Микросервис-коннектор
│   ├── __init__.py
│   ├── main.py               # FastAPI app
│   ├── config.py             # ConnectorConfig
│   ├── schemas.py            # Pydantic модели запросов
│   ├── siem_clients/
│   │   ├── __init__.py
│   │   ├── base.py           # Абстрактный клиент SIEM
│   │   ├── indexer.py        # Клиент Wazuh Indexer (OpenSearch)
│   │   └── wazuh.py          # Клиент Wazuh Manager API
│   ├── normalizer/
│   │   ├── __init__.py
│   │   ├── base.py           # BaseNormalizer (ABC)
│   │   ├── ecs.py            # Нормализация в ECS
│   │   └── wazuh/
│   │       ├── wazuh_base.py
│   │       └── wazuh_normalizer.py
│   ├── webhook/
│   │   ├── __init__.py
│   │   └── listener.py       # Webhook listener
│   └── broker/
│       ├── __init__.py
│       └── rabbit.py         # Интеграция с RabbitMQ
├── agent/                    # Агентная система
│   ├── __init__.py
│   ├── main.py               # FastAPI + lifespan + RabbitMQ consumer
│   ├── config.py             # AgentConfig (LLM, RabbitMQ, Chroma)
│   ├── agent.py              # LangGraph StateGraph
│   ├── pipeline.py           # AgentPipeline — обёртка
│   ├── categorizer.py        # Категоризация (small LLM)
│   ├── planner.py            # Формирование плана (large LLM)
│   ├── db.py                 # SQLite persistence
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py        # Pydantic модели
│   └── rag/
│       ├── __init__.py
│       ├── vector_store.py   # Работа с векторной БД
│       └── knowledge_base.py # Загрузка плейбуков из *.md
├── scripts/
│   ├── check_indexer.py      # Проверка соединения с Wazuh Indexer
│   ├── add_alert.py          # Добавление тестовых алертов
│   └── ollama-init.sh        # Инициализация Ollama (pull моделей)
├── knowledge/                # База знаний (playbooks)
│   ├── brute-force.md
│   ├── web-exploit.md
│   ├── malware.md
│   ├── reconnaissance.md
│   ├── unauthorized-access.md
│   └── policy-violation.md
├── Dockerfile.connector
├── Dockerfile.agent
└── docs/                     # Документация
```

## 4. Этапы реализации

### Этап 1: Базовый каркас проекта
- Инициализация проекта (pyproject.toml, requirements.txt)
- Docker Compose (RabbitMQ, Ollama, Chroma)
- Конфигурация (.env)

### Этап 2: Connector (микросервис-коннектор)
- FastAPI приложение
- REST API клиент для Wazuh (Indexer + Manager API)
- Webhook listener
- Нормализатор событий → ECS
- Интеграция с RabbitMQ

### Этап 3: База знаний и RAG
- Векторная БД (Chroma)
- Индексация плейбуков из knowledge/*.md
- RAG pipeline для поиска

### Этап 4: Модуль планирования
- Small LLM для категоризации
- Large LLM для формирования плана
- Паттерн: алерт → категоризация → RAG → план

### Этап 5: Интеграция с Wazuh
- Отправка плана через Wazuh API
- Кастомный дашборд для отображения

### Этап 6: Оркестрация
- Docker Compose для всех компонентов
- Документация по развёртыванию

## 5. Схема данных (ECS нормализация)

Основные поля ECS для события ИБ:
- `@timestamp` — время события
- `event.id` — идентификатор события
- `event.category` — категория (authentication, intrusion_detection, etc.)
- `event.type` — тип (info, alert, etc.)
- `event.severity` — критичность
- `rule.id` — ID правила SIEM
- `rule.name` — название правила
- `source.ip` — IP источника
- `source.port` — порт источника
- `destination.ip` — IP цели
- `destination.port` — порт цели
- `user.name` — имя пользователя
- `message` — описание события
- `ecs.version` — версия ECS

## 6. Пайплайн обработки

1. SIEM генерирует алерт
2. Connector получает алерт (REST poll или webhook)
3. Нормализация события в ECS
4. Событие публикуется в RabbitMQ
5. Agent System получает событие из очереди
6. Small LLM категоризирует событие (brute-force, web-exploit, malware...)
7. RAG запрос к базе знаний на основе категории
8. Large LLM формирует пошаговый план анализа
9. План отправляется обратно в Wazuh через API
10. План отображается в кастомном дашборде Wazuh
