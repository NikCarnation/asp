# Connector: микросервис взаимодействия с SIEM

## Роль в системе

Connector — это отдельный микросервис, отвечающий за взаимодействие агентной системы AISOC со средствами мониторинга (SIEM). Он выступает в роли шлюза: получает события информационной безопасности из SIEM, нормализует их в единый формат ECS и передаёт в брокер сообщений для дальнейшей обработки агентной системой.

```
SIEM (Wazuh) ──► Connector ──► RabbitMQ ──► Agent System
                    │
               REST API ──► Отдача алертов и приём планов
              Webhook ──► Приём алертов в реальном времени
```

Такой подход позволяет:
- Адаптировать систему под разные SIEM (Wazuh, Splunk, MaxPatrol, KUMA) без изменения ядра агента
- Буферизировать пиковые нагрузки через очередь
- Единообразно нормализовать данные вне зависимости от источника

---

## Два способа получения данных из SIEM

### 1. REST API Polling (pull-режим)

Инициатор запроса — Connector (или агентная система). Подходит для:
- Получения дополнительного контекста по уже обрабатываемому алерту
- Детального разбора конкретного события по ID
- Периодической синхронизации или отладки

**Реализация в коде:**

Интерфейс `SiemClient` (`connector/siem_clients/base.py`) определяет абстрактные методы:

```python
class SiemClient(ABC):
    async def fetch_alerts(self, limit, offset) -> list[NormalizedAlert]
    async def get_alert_by_id(self, alert_id) -> NormalizedAlert | None
    async def send_plan(self, alert_id, plan_data) -> bool
```

Класс `WazuhClient` (`connector/siem_clients/wazuh.py`) реализует эти методы через HTTP-запросы к Wazuh API:

- **Аутентификация** — JWT-токен через `POST /security/user/authenticate` с basic auth. Токен кэшируется, при 401 происходит автоматическая переаутентификация.
- `fetch_alerts` — `GET /security/alerts` с параметрами `limit`, `offset`, `sort=-timestamp`. Ответ маппится через нормализатор.
- `get_alert_by_id` — `GET /security/alerts?search=id={alert_id}`.
- `send_plan` — `POST /security/alerts/context` — отправляет сформированный агентом план анализа обратно в Wazuh для отображения в дашборде.

Эти методы экспонируются через FastAPI-эндпоинты коннектора:

| Метод | Путь | Действие |
|-------|------|----------|
| GET | `/api/v1/alerts?limit=100&offset=0` | Получить список алертов |
| GET | `/api/v1/alerts/{id}` | Получить алерт по ID |
| POST | `/api/v1/publish?alert_id=...` | Извлечь алерт по ID и опубликовать в очередь |
| POST | `/api/v1/plan/{alert_id}` | Отправить план анализа в SIEM |

### 2. Webhook (push-режим)

Инициатор — SIEM. Connector выступает в роли слушателя. Обеспечивает минимальное время реакции на новые события. SIEM отправляет HTTP POST при срабатывании правила безопасности.

**Реализация в коде** (`connector/webhook/listener.py`):

```python
@router.post("/webhook/wazuh")    # Приём алертов от Wazuh
@router.post("/webhook/generic")  # Приём алертов от любых SIEM
```

Webhook `/webhook/wazuh` принимает сырой алерт Wazuh, пропускает через `normalize_wazuh_alert()` и сразу публикует в RabbitMQ.

Webhook `/webhook/generic` принимает уже нормализованный алерт (в формате `NormalizedAlert`) и публикует в очередь. Это позволяет интегрировать SIEM, для которых уже есть внешний нормализатор.

**Комбинация двух подходов** обеспечивает:
- Скорость — webhook ловит новые события мгновенно
- Глубину — REST API позволяет запросить дополнительные детали по событию в ходе анализа

---

## Нормализация в ECS

`connector/normalizer/ecs.py` — модуль приведения сырых событий SIEM к стандарту **Elastic Common Schema (ECS) v8.11.0**.

Функция `normalize_wazuh_alert(raw: dict) -> NormalizedAlert`:

1. Извлекает из сырого JSON Wazuh вложенные секции: `rule`, `agent`, `data`
2. Парсит timestamp (поддерживает `Z`-суффикс)
3. Маппит поля Wazuh → ECS:

| Поле Wazuh | Поле ECS / NormalizedAlert |
|-----------|---------------------------|
| `rule.id` | `rule_id` |
| `rule.name` | `rule_name` |
| `rule.level` | `rule_level`, `event_severity`, `event_type` |
| `data.srcip` / `source.ip` | `source_ip` |
| `data.dstip` / `destination.ip` | `destination_ip` |
| `full_log` / `message` | `message` |
| `rule.category` | `event_category` (через маппинг) |

Маппинг категорий (`_map_category`):
- `authentication`, `authentication_failed` → `authentication`
- `firewall` → `network`
- `web` → `web`
- `malware` → `malware`
- `policy` → `compliance`
- остальное → `unknown`

Маппинг severity (`_map_type`):
- level ≥ 12 → `critical`
- level ≥ 7 → `warning`
- level ≥ 4 → `info`
- остальное → `notice`

Модель данных — `NormalizedAlert` (`agent/models/schemas.py`):

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

---

## Брокер сообщений (RabbitMQ)

`connector/broker/rabbit.py` — интеграция с RabbitMQ.

### RabbitPublisher

Используется Connector-ом для отправки нормализованных алертов в очередь.

```python
async def publish(self, alert: NormalizedAlert):
    body = alert.model_dump_json(default=str).encode()
    await self.channel.default_exchange.publish(
        aio_pika.Message(body=body, delivery_mode=PERSISTENT),
        routing_key=self.queue_name,
    )
```

- **Гарантированная доставка**: `delivery_mode=DeliveryMode.PERSISTENT` — сообщения сохраняются на диск RabbitMQ
- **Durable queue**: `declare_queue(queue, durable=True)` — очередь переживает перезапуск брокера
- **Сериализация**: `alert.model_dump_json(default=str)` — Pydantic-модель → JSON

### RabbitConsumer

Используется Agent System для получения алертов из очереди.

```python
async def consume(self, callback):
    async with self.channel.iterator(self.queue_name) as queue_iter:
        async for message in queue_iter:
            async with message.process():
                data = json.loads(message.body.decode())
                alert = NormalizedAlert(**data)
                await callback(alert)
```

- `message.process()` — автоматическое подтверждение (ack) при успехе, nack при ошибке
- Десериализация JSON → `NormalizedAlert` с валидацией Pydantic

---

## Mock-режим для тестирования

Для разработки и тестирования без реального SIEM используется `MockWazuhClient` (`connector/siem_clients/wazuh.py`).

- Включается флагом `WAZUH_MOCK=true` (значение по умолчанию)
- Генерирует 5 предопределённых алертов разных типов: SSH Brute Force, Web Shell, Malware, Port Scan, Unauthorized Access
- Имитирует `fetch_alerts`, `get_alert_by_id`, `send_plan`

Позволяет тестировать полный пайплайн:
```bash
curl -X POST "http://localhost:8000/api/v1/publish?alert_id=alert-001"
```

---

## Жизненный цикл коннектора

```
Старт приложения
     │
     ├─► Инициализация RabbitPublisher (подключение + объявление очереди)
     ├─► Инициализация SIEM клиента (WazuhClient или MockWazuhClient)
     │
     ▼
Ожидание запросов (FastAPI)
     │
     ├─► GET /api/v1/alerts       → siem_client.fetch_alerts()
     ├─► GET /api/v1/alerts/{id}  → siem_client.get_alert_by_id()
     ├─► POST /api/v1/publish     → siem_client.get_alert_by_id() → rabbit_publisher.publish()
     ├─► POST /api/v1/plan/{id}   → siem_client.send_plan()
     ├─► POST /webhook/wazuh      → normalize → rabbit_publisher.publish()
     └─► POST /webhook/generic    → rabbit_publisher.publish()
     │
     ▼
Завершение (shutdown)
     ├─► Закрытие RabbitMQ соединения
     └─► Закрытие HTTP-клиента SIEM
```

---

## Конфигурация

Все настройки — через переменные окружения (файл `.env`):

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `RABBITMQ_HOST` | localhost | Хост RabbitMQ |
| `RABBITMQ_PORT` | 5672 | Порт RabbitMQ |
| `RABBITMQ_USER` | guest | Пользователь RabbitMQ |
| `RABBITMQ_PASS` | guest | Пароль RabbitMQ |
| `RABBITMQ_QUEUE` | aisoc_alerts | Имя очереди |
| `WAZUH_API_URL` | http://localhost:55000 | URL Wazuh API |
| `WAZUH_API_USER` | wazuh-wui | Пользователь Wazuh API |
| `WAZUH_API_PASS` | wazuh-wui | Пароль Wazuh API |
| `WAZUH_MOCK` | true | Использовать mock SIEM |
| `CONNECTOR_HOST` | 0.0.0.0 | Хост для FastAPI |
| `CONNECTOR_PORT` | 8000 | Порт для FastAPI |

Загрузка конфигурации — через `ConnectorConfig` (Pydantic Settings) в `connector/config.py`.

---

## Структура модуля

```
connector/
├── __init__.py
├── config.py            # Pydantic Settings (ConnectorConfig)
├── main.py              # FastAPI приложение + lifespan
├── broker/
│   ├── __init__.py
│   └── rabbit.py        # RabbitPublisher + RabbitConsumer
├── normalizer/
│   ├── __init__.py
│   └── ecs.py           # normalize_wazuh_alert() + хелперы
├── siem_clients/
│   ├── __init__.py
│   ├── base.py          # SiemClient (ABC)
│   └── wazuh.py         # WazuhClient + MockWazuhClient
└── webhook/
    ├── __init__.py
    └── listener.py      # /webhook/wazuh и /webhook/generic
```

## Расширение для других SIEM

Для добавления поддержки новой SIEM-системы (например, Splunk или MaxPatrol):

1. Создать класс-наследник `SiemClient` (например `SplunkClient`)
2. Реализовать `fetch_alerts`, `get_alert_by_id`, `send_plan`
3. Создать нормализатор под формат этой SIEM
4. Зарегистрировать клиент в `connector/main.py` (в `lifespan`)

Брокер и вебхуки остаются без изменений.

## Поток данных

```
                          pull-режим:
                          GET /api/v1/alerts
                          GET /api/v1/alerts/{id}
                          POST /api/v1/publish?alert_id=X
                          POST /api/v1/plan/{id}

Wazuh API ────► Connector ────► RabbitMQ ────► Agent
  (REST)          │
                  │ push-режим:
                  │ POST /webhook/wazuh  (от Wazuh)
                  │ POST /webhook/generic (от других SIEM)
                  │
                  ▼
            Wazuh API ◄──── AnalysisPlan
            (send_plan)
```
