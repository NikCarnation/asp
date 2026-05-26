# База знаний и RAG (Retrieval-Augmented Generation)

## Роль в системе

Модуль базы знаний обеспечивает агентную систему релевантной информацией для анализа инцидентов. Он реализует подход **RAG (Retrieval-Augmented Generation)**: при поступлении алерта система ищет в векторной базе данных плейбуки, соответствующие типу инцидента, и передаёт их Large Language Model для формирования плана анализа.

```
Categorizer ──► VectorStore.search(category, rule, message) ──► Planner
                    │
                    ▼
          Chroma (langchain_chroma)
       локальное SQLite-хранилище
                    ▲
                    │
               Индексация
      ALL_PLAYBOOKS → разбивка на чанки → эмбеддинги (Ollama)
```

---

## Компоненты

### 1. Плейбуки (Playbook)

`agent/rag/knowledge_base.py` — загружает базу знаний из markdown-файлов директории `knowledge/`.

**Модель данных:**

```python
class Playbook(BaseModel):
    title: str           # Название плейбука (из первой строки # ...)
    category: str        # Категория (из имени файла: brute-force.md → "brute-force")
    content: str         # Полный текст плейбука (Markdown)
    source: str | None   # Источник (например "AISOC Knowledge Base")
```

**Загрузка из файлов:**

```python
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"

def _load_playbooks() -> list[Playbook]:
    for md_file in sorted(KNOWLEDGE_DIR.glob("*.md")):
        category = md_file.stem          # "brute-force"
        content = md_file.read_text(...)
        title = первая строка # ...
        playbooks.append(Playbook(title=title, category=category, content=content, ...))
    return playbooks
```

**Список плейбуков:**

| Категория | Плейбук | Содержание |
|-----------|---------|------------|
| `brute-force` | Brute Force Attack Response | Проверка репутации IP, блокировка, сброс паролей |
| `web-exploit` | Web Application Exploit Response | Анализ логов, проверка веб-шеллов |
| `malware` | Malware Infection Response | Изоляция хоста, анализ процессов |
| `reconnaissance` | Reconnaissance / Port Scan Response | Верификация сканирования, корреляция с IDS |
| `unauthorized-access` | Unauthorized Access Response | Проверка логов, компрометация учётных данных |
| `policy-violation` | Policy Violation Response | Проверка нарушения политик, DLP |

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
```

Этот маппинг используется как fallback, когда векторное хранилище пусто или поиск не дал результатов.

---

### 2. Векторное хранилище (VectorStore)

`agent/rag/vector_store.py` — класс `VectorStore`, построенный на `langchain_chroma.Chroma` с локальным SQLite-хранилищем. **Не требует отдельного Docker-контейнера.**

**Подключение:**

```python
class VectorStore:
    def __init__(self, persist_dir, collection_name, ollama_base_url, embedding_model):
        # OllamaEmbeddings — эмбеддинги через Ollama API
        self._embeddings = OllamaEmbeddings(
            model=embedding_model,        # nomic-embed-text
            base_url=ollama_base_url,
        )
        # Локальное Chroma-хранилище (SQLite на диске)
        self._store = Chroma(
            collection_name=collection_name,
            embedding_function=self._embeddings,
            persist_directory=persist_dir,
        )
```

**Разбивка на чанки (chunking):**

Перед индексацией каждый плейбук разбивается на семантические чанки:

1. **MarkdownHeaderTextSplitter** — разделяет по заголовкам `#`, `##`, `###`, сохраняя контекст
2. **RecursiveCharacterTextSplitter** — дробит длинные секции (более 2000 символов) на чанки по 1500 токенов с перекрытием 200

```python
def _chunk_playbook(self, pb: Playbook) -> list[Document]:
    md_chunks = self._md_splitter.split_text(pb.content)
    for chunk in md_chunks:
        header_ctx = build_header_context(chunk.metadata)
        enriched = f"{header_ctx}\n\n{chunk.page_content}"
        # если всё ещё длинный — ещё один проход сплиттера
        if len(enriched) > 2000:
            sub_chunks = self._text_splitter.split_text(enriched)
```

Каждый чанк сохраняется с метаданными: `title`, `category`, `source`, а также заголовки (`h1`, `h2`, `h3`).

**Поиск (MMR):**

Используется `max_marginal_relevance_search` — поиск по максимальной маргинальной релевантности, который обеспечивает **разнообразие результатов**:

```python
def search(self, category, query="", n_results=5, alert_message="") -> list[Playbook]:
    # Обогащённый запрос: категория + правило + текст алерта
    rich_query = f"category: {category} | {query} | {alert_message[:300]}"

    # MMR: баланс между релевантностью и разнообразием
    docs = self._store.max_marginal_relevance_search(
        rich_query,
        k=n_results,
        fetch_k=n_results * 3,   # кандидатов в 3 раза больше
        filter={"category": category} if category != "unknown" else None,
    )
```

- `k=5` — возвращается до 5 чанков
- `fetch_k=15` — из 15 кандидатов выбираются 5 самых релевантных и разнообразных
- Фильтрация по `category` через `where`

**Ленивая инициализация:**

В `agent/main.py` при старте проверяется `vector_store.count()`. Если коллекция пуста — загружаются все плейбуки с разбивкой на чанки:

```python
if vector_store.count() == 0:
    for attempt in range(30):
        try:
            vector_store.add_playbooks(ALL_PLAYBOOKS)
            break
        except Exception:
            await asyncio.sleep(2)  # ждём, пока Ollama скачает модель эмбеддингов
```

---

### 3. Эмбеддинги через Ollama

В отличие от предыдущей версии (встроенная модель Chroma `all-MiniLM-L6-v2`), эмбеддинги теперь создаются через **Ollama API** с моделью `nomic-embed-text`.

**Преимущества:**
- **Мультиязычность** — `nomic-embed-text` работает и с русским, и с английским текстом
- **Единый сервис** — не нужен отдельный контейнер для эмбеддингов, используется тот же Ollama
- **Гибкость** — модель можно заменить через `EMBEDDING_MODEL` в `.env`

Модель `nomic-embed-text` автоматически скачивается в `ollama-init.sh` при старте Docker Compose.

---

### 4. Интеграция в пайплайн

**Шаг 2 в `AgentPipeline.process()`:**

```python
playbooks = self.vector_store.search(
    category=category.category,   # "brute-force"
    query=alert.rule_name,        # "SSH Brute Force Attack"
    alert_message=alert.message,  # "Failed password for root from 10.0.0.5"
)

# Fallback на CATEGORY_PLAYBOOK_MAP
if not playbooks and category.category in CATEGORY_PLAYBOOK_MAP:
    playbooks = [CATEGORY_PLAYBOOK_MAP[category.category]]

# Если категория не найдена — поиск по "unknown"
elif not playbooks:
    playbooks = self.vector_store.search(category="unknown", query=alert.rule_name)
```

Три уровня поиска:
1. **VectorStore (Chroma + MMR)** — семантический поиск по обогащённому запросу
2. **CATEGORY_PLAYBOOK_MAP** — fallback если хранилище пусто
3. **Поиск по "unknown"** — если нет плейбука для данной категории

Найденные чанки передаются в `Planner.create_plan()`, который формирует финальный план.

---

## Markdown-файлы базы знаний

Директория `knowledge/` содержит Markdown-файлы плейбуков:

```
knowledge/
├── brute-force.md
├── web-exploit.md
├── malware.md
├── reconnaissance.md
├── unauthorized-access.md
├── policy-violation.md
└── Подбор пароля от SSH.md
```

Чтобы изменить или добавить плейбук:
1. Отредактировать существующий `.md` файл или создать новый
2. Перезагрузить плейбуки через API:
   ```bash
   curl -X POST http://localhost:8001/api/v1/playbooks/reload
   ```

---

## Технологии

| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Векторная БД | Chroma (langchain_chroma) | ≥0.2.0 |
| Хранилище | Локальный SQLite (файл) | — |
| Эмбеддинги | OllamaEmbeddings (nomic-embed-text) | через Ollama |
| Разбивка текста | MarkdownHeaderTextSplitter + RecursiveCharacterTextSplitter | langchain-text-splitters |
| Поиск | MMR (Max Marginal Relevance) | langchain-chroma |
