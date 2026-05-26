# Модели данных AISOC

## Обзор

Все модели данных в проекте описаны через **Pydantic BaseModel** в `agent/models/schemas.py`. Эти модели используются как в **Connector**, так и в **Agent System**, обеспечивая единый контракт данных между микросервисами.

```
SIEM ──► Connector ──► RabbitMQ ──► Agent System
          │                            │
      normalize_wazuh_alert()      NormalizedAlert
          │                            │
    NormalizedAlert              AnalysisPlan ──► SIEM
```

---

## NormalizedAlert

Основная модель для представления события информационной безопасности, нормализованного в формат **Elastic Common Schema (ECS) v8.11.0**.

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

### Поля

| Поле | Тип | ECS-аналог | Описание |
|------|-----|-----------|----------|
| `timestamp` | `datetime` | `@timestamp` | Время события |
| `event_id` | `str` | `event.id` | Уникальный идентификатор события в SIEM |
| `event_kind` | `str` | `event.kind` | Тип события (по умолчанию "alert") |
| `event_category` | `str` | `event.category` | Категория: authentication, web, malware, network, compliance, unknown |
| `event_type` | `str` | `event.type` | Тип: critical, warning, info, notice |
| `event_severity` | `int` | `event.severity` | Уровень критичности (0-15, Wazuh rule level) |
| `rule_id` | `str` | `rule.id` | ID правила SIEM, сработавшего на событие |
| `rule_name` | `str` | `rule.name` | Название правила |
| `rule_level` | `int` | `rule.level` | Уровень правила (0-15) |
| `rule_description` | `str` | `rule.description` | Описание правила |
| `source_ip` | `str\|None` | `source.ip` | IP-адрес источника атаки |
| `source_port` | `int\|None` | `source.port` | Порт источника |
| `destination_ip` | `str\|None` | `destination.ip` | IP-адрес цели |
| `destination_port` | `int\|None` | `destination.port` | Порт цели |
| `user_name` | `str\|None` | `user.name` | Имя пользователя |
| `process_name` | `str\|None` | `process.name` | Имя процесса |
| `network_protocol` | `str\|None` | `network.protocol` | Протокол (tcp, udp, ...) |
| `message` | `str` | `message` | Текстовое описание события |
| `ecs_version` | `str` | `ecs.version` | Версия ECS ("8.11.0") |
| `raw` | `dict` | — | Сырой JSON-алерт из SIEM (для аудита и отладки) |

### Маппинг маппинг severity → event_type

| rule_level | event_type |
|-----------|------------|
| ≥ 12 | `critical` |
| 7-11 | `warning` |
| 4-6 | `info` |
| 0-3 | `notice` |

### Сериализация

При публикации в RabbitMQ модель сериализуется в JSON:
```python
alert.model_dump_json(default=str)  # datetime → ISO string
```

При получении десериализуется с валидацией:
```python
alert = NormalizedAlert(**data)  # data из JSON
```

---

## IncidentCategory

Результат работы малой LLM (Categorizer):

```python
class IncidentCategory(BaseModel):
    category: str        # brute-force, web-exploit, malware, ...
    confidence: float    # 0.0 - 1.0
    description: str = ""  # Пояснение от модели
```

### Возможные категории

| Категория | Описание |
|-----------|----------|
| `brute-force` | Атаки перебором паролей (SSH, RDP, веб-форм) |
| `web-exploit` | Эксплуатация веб-уязвимостей (SQLi, XSS, RCE) |
| `malware` | Вредоносное ПО (трояны, шифровальщики, майнеры) |
| `phishing` | Фишинговые атаки |
| `reconnaissance` | Разведка и сканирование |
| `unauthorized-access` | Несанкционированный доступ |
| `data-exfiltration` | Утечка данных |
| `denial-of-service` | DDoS/DoS атаки |
| `policy-violation` | Нарушение политик безопасности |
| `unknown` | Не удалось определить |

---

## PlanStep

Один шаг плана анализа:

```python
class PlanStep(BaseModel):
    order: int               # Порядковый номер шага
    action: str              # Краткое название (например "Check source IP")
    description: str         # Подробное описание действий
    commands: list[str] = [] # Команды для выполнения (shell, API-запросы)
    expected_result: str = ""  # Ожидаемый результат
```

Пример:
```json
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
```

---

## AnalysisPlan

Полный план анализа инцидента — результат работы Planner (Large LLM):

```python
class AnalysisPlan(BaseModel):
    alert_id: str                 # ID исходного алерта
    incident_category: str        # Категория (из Categorizer)
    created_at: datetime          # Время создания плана
    summary: str                  # Краткое описание инцидента (1-2 предложения)
    steps: list[PlanStep]         # Пошаговый план
    raw_markdown: str = ""        # Markdown-версия для вывода в дашборде
```

### Пример

```json
{
  "alert_id": "alert-001",
  "incident_category": "brute-force",
  "created_at": "2026-05-14T12:05:00Z",
  "summary": "SSH brute force attack detected from 192.168.1.100 targeting root account. 5 failed attempts in 2 minutes.",
  "steps": [
    {
      "order": 1,
      "action": "Check source IP reputation",
      "description": "Query VirusTotal...",
      "commands": ["curl -s ..."],
      "expected_result": "Reputation score"
    }
  ],
  "raw_markdown": "# Analysis Plan\n## 1. Check source IP reputation\n..."
}
```

---

## Playbook

Модель плейбука из базы знаний:

```python
class Playbook(BaseModel):
    title: str              # Название
    category: str           # Категория инцидента
    content: str            # Markdown-текст
    source: str | None      # Источник (опционально)
```

---

## Схема передачи данных между сервисами

```
Connector                              Agent
   │                                      │
   │  1. GET /security/alerts             │
   │  (Wazuh API)                         │
   │                                      │
   │  2. normalize_wazuh_alert()          │
   │  dict ──► NormalizedAlert            │
   │                                      │
   │  3. RabbitMQ publish                 │
   │  NormalizedAlert ──► JSON ──► Queue  │
   │                                      │
   │                             4. RabbitMQ consume
   │                             JSON ──► NormalizedAlert
   │                                      │
   │                             5. pipeline.process(alert)
   │                             Categorizer ──► IncidentCategory
   │                             RAG ──► list[Playbook]
   │                             Planner ──► AnalysisPlan
   │                                      │
   │  6. POST /security/alerts/context    │
   │  AnalysisPlan ──► Wazuh API          │
   │                                      │
```

### Формат JSON в RabbitMQ

```json
{
  "timestamp": "2026-05-14T12:00:00+00:00",
  "event_id": "alert-001",
  "event_kind": "alert",
  "event_category": "authentication",
  "event_type": "warning",
  "event_severity": 7,
  "rule_id": "5710",
  "rule_name": "SSH Brute Force Attack",
  "rule_level": 7,
  "rule_description": "Multiple failed SSH login attempts detected",
  "source_ip": "192.168.1.100",
  "source_port": 54321,
  "destination_ip": "10.0.0.5",
  "destination_port": 22,
  "user_name": "root",
  "process_name": null,
  "network_protocol": "tcp",
  "message": "SSHD 5 failed login attempts from 192.168.1.100",
  "ecs_version": "8.11.0",
  "raw": {"data": {"rule": {"id": "5710", "name": "...", "level": 7}}}
}
```
