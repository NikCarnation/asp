# База знаний и RAG (Retrieval-Augmented Generation)

## Роль в системе

Модуль базы знаний обеспечивает агентную систему релевантной информацией для анализа инцидентов. Он реализует подход **RAG (Retrieval-Augmented Generation)**: при поступлении алерта система ищет в векторной базе данных плейбуки, соответствующие типу инцидента, и передаёт их Large Language Model для формирования плана анализа.

```
Categorizer ──► VectorStore.search() ──► Planner
                    │
                    ▼
              Chroma DB
           (коллекция плейбуков)
                    ▲
                    │
              Индексация
           ALL_PLAYBOOKS (6 шт.)
```

---

## Компоненты

### 1. Плейбуки (Playbook)

`agent/rag/knowledge_base.py` — содержит встроенную базу знаний из 6 плейбуков.

**Модель данных:**

```python
class Playbook(BaseModel):
    title: str           # Название плейбука
    category: str        # Категория (brute-force, web-exploit, ...)
    content: str         # Полный текст плейбука (Markdown)
    source: str | None   # Источник (например "AISOC Knowledge Base")
```

**Список плейбуков:**

| Категория | Плейбук | Содержание |
|-----------|---------|------------|
| `brute-force` | Brute Force Attack Response | Проверка репутации IP, блокировка, сброс паролей, команды `grep`, `journalctl` |
| `web-exploit` | Web Application Exploit Response | Анализ логов веб-сервера, проверка веб-шеллов, команды `tail`, `find`, `lsof` |
| `malware` | Malware Infection Response | Изоляция хоста, анализ процессов и персистентности, команды `wmic`, `netstat`, `schtasks` |
| `reconnaissance` | Reconnaissance / Port Scan Response | Верификация сканирования, корреляция с IDS, `tcpdump`, `ss` |
| `unauthorized-access` | Unauthorized Access Response | Проверка логов доступа, компрометация учётных данных, `last`, `ausearch` |
| `policy-violation` | Policy Violation Response | Проверка нарушения политик, DLP, оповещение менеджера |

Каждый плейбук содержит 5 секций:
1. **Initial Triage / Verification** — первичная проверка
2. **Investigation / Analysis** — углублённый анализ
3. **Containment / Response** — действия по сдерживанию
4. **Commands** — конкретные shell-команды
5. **Key Questions** — ключевые вопросы, на которые нужно ответить

**Маппинг категорий:**

```python
CATEGORY_PLAYBOOK_MAP: dict[str, Playbook] = {
    pb.category: pb for pb in ALL_PLAYBOOKS
}
# {'brute-force': Playbook(...), 'web-exploit': Playbook(...), ...}
```

Этот маппинг используется как fallback, когда VectorStore пуст или поиск не дал результатов.

---

### 2. Векторное хранилище (VectorStore)

`agent/rag/vector_store.py` — класс `VectorStore`, клиент для работы с Chroma DB.

**Подключение:**

```python
class VectorStore:
    def __init__(self, host, port, collection_name):
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(
            name=collection_name
        )
```

Используется HTTP-клиент Chroma (подключается к серверу `chromadb/chroma:latest` в Docker).

**Методы:**

| Метод | Описание |
|-------|----------|
| `add_playbook(pb)` | Добавить один плейбук в коллекцию |
| `add_playbooks(pbs)` | Добавить список плейбуков (batch) |
| `search(category, query, n_results)` | Поиск по категории и тексту |
| `count()` | Количество документов в коллекции |
| `reset()` | Удалить и пересоздать коллекцию |

**Добавление плейбуков:**

```python
def add_playbooks(self, playbooks: list[Playbook]):
    docs = []    # содержимое плейбуков (текст Markdown)
    metas = []   # метаданные: title, category, source
    ids = []     # UUID для каждого документа

    for pb in playbooks:
        docs.append(pb.content)
        metas.append({"title": pb.title, "category": pb.category, "source": pb.source})
        ids.append(str(uuid.uuid4()))

    self.collection.add(documents=docs, metadatas=metas, ids=ids)
```

- Каждый плейбук — отдельный документ в Chroma
- Метаданные: `title`, `category`, `source`
- ID — случайный UUID

**Поиск:**

```python
def search(self, category, query="", n_results=3) -> list[Playbook]:
    results = self.collection.query(
        query_texts=[search_query],    # текст запроса
        n_results=n_results,            # количество результатов
        where={"category": category} if category != "unknown" else None,
    )
```

- Фильтрация по `category` через `where`
- Поиск по тексту (semantic search через эмбеддинги Chroma)
- Возвращает до `n_results` (по умолчанию 3) плейбуков

**Ленивая инициализация:**

В `agent/main.py` при старте проверяется `vector_store.count()`. Если коллекция пуста — загружаются все 6 плейбуков:

```python
if vector_store.count() == 0:
    vector_store.add_playbooks(ALL_PLAYBOOKS)
```

---

### 3. Интеграция в пайплайн

**Шаг 2 в `AgentPipeline.process()`:**

```python
playbooks = self.vector_store.search(
    category=category.category,  # например "brute-force"
    query=alert.rule_name,       # например "SSH Brute Force Attack"
)

# Fallback на CATEGORY_PLAYBOOK_MAP
if not playbooks and category.category in CATEGORY_PLAYBOOK_MAP:
    playbooks = [CATEGORY_PLAYBOOK_MAP[category.category]]

# Если категория не найдена — поиск по "unknown"
elif not playbooks:
    playbooks = self.vector_store.search(category="unknown", query=alert.rule_name)
```

Три уровня поиска:
1. **Chroma DB** — semantic search по категории
2. **CATEGORY_PLAYBOOK_MAP** — fallback если Chroma пуста
3. **Поиск по "unknown"** — если нет плейбука для данной категории

Плейбуки передаются в `Planner.create_plan()`, который формирует финальный план.

---

## Markdown-файлы базы знаний

Директория `knowledge/` содержит Markdown-копии плейбуков для удобства редактирования:

```
knowledge/
├── brute-force.md
├── web-exploit.md
├── malware.md
├── reconnaissance.md
├── unauthorized-access.md
└── policy-violation.md
```

Содержимое этих файлов **дублирует** плейбуки из `knowledge_base.py`. При необходимости:
1. Отредактировать `.md` файл
2. Обновить соответствующий `Playbook(...)` в `knowledge_base.py`

В будущем можно реализовать авто-загрузку из `.md` файлов, убрав дублирование.

---

## Технологии

| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Векторная БД | Chroma DB | latest (Docker) |
| Клиент | chromadb (Python) | ≥0.5.0 |
| Эмбеддинги | Встроенные в Chroma (all-MiniLM-L6-v2) | — |
| HTTP-порт | 8000 (внутри Docker), 8002 (наружу) | — |

Chroma использует встроенную модель эмбеддингов `all-MiniLM-L6-v2` для преобразования текста плейбуков в векторные представления. Это не требует отдельного API ключа или сервера эмбеддингов.
