# План разработки агентной системы анализа событий ИБ

## 1. Архитектура системы

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│    SIEM      │────▶│   Connector     │────▶│  Message Broker  │
│  (Wazuh)     │◀────│  (микросервис)  │     │  (RabbitMQ/Kafka)│
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
| Small LLM | llama3.2:1b / phi3:mini | Через Ollama |
| Large LLM | llama3.1:8b / qwen2.5:7b | Через Ollama или OpenRouter |
| Нормализация | ECS (Elastic Common Schema) | — |
| SIEM | Wazuh (тестовый стенд) | — |
| Дашборд | Wazuh Custom Dashboard | — |
| Контейнеризация | Docker + Docker Compose | — |

## 3. Структура проекта

```
aisoc/
├── main.py                    # Точка входа (оркестратор)
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── pyproject.toml
├── connector/                 # Микросервис-коннектор
│   ├── __init__.py
│   ├── main.py               # FastAPI app
│   ├── siem_clients/
│   │   ├── __init__.py
│   │   ├── base.py           # Абстрактный клиент SIEM
│   │   └── wazuh.py          # Клиент Wazuh
│   ├── normalizer/
│   │   ├── __init__.py
│   │   └── ecs.py            # Нормализация в ECS
│   ├── webhook/
│   │   ├── __init__.py
│   │   └── listener.py       # Webhook listener
│   └── broker/
│       ├── __init__.py
│       └── rabbit.py         # Интеграция с RabbitMQ
├── agent/                    # Агентная система
│   ├── __init__.py
│   ├── categorizer.py        # Категоризация (small LLM)
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── vector_store.py   # Работа с векторной БД
│   │   └── knowledge_base.py # Управление базой знаний
│   ├── planner.py            # Формирование плана (large LLM)
│   └── models/
│       ├── __init__.py
│       └── schemas.py        # Pydantic модели
└── knowledge/                # База знаний (playbooks)
    ├── brute-force.md
    ├── web-exploit.md
    └── ...
```

## 4. Этапы реализации

### Этап 1: Базовый каркас проекта
- Инициализация проекта (pyproject.toml, requirements.txt)
- Docker Compose (RabbitMQ, Ollama, Chroma)
- Конфигурация (.env)

### Этап 2: Connector (микросервис-коннектор)
- FastAPI приложение
- REST API клиент для Wazuh
- Webhook listener
- Нормализатор событий → ECS
- Интеграция с RabbitMQ

### Этап 3: База знаний и RAG
- Векторная БД (Chroma)
- Индексация плейбуков
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
