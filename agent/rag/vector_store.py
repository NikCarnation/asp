from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
import os

from agent.rag.knowledge_base import Playbook


class VectorStore:
    def __init__(
        self,
        persist_dir: str,
        collection_name: str = os.getenv("CHROMA_COLLECTION"),
        ollama_base_url: str = "http://localhost:11434",
        embedding_model: str = os.getenv("EMBEDDING_MODEL"),
    ):
        self._persist_dir = persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self._embeddings = OllamaEmbeddings(
            model=embedding_model,
            base_url=ollama_base_url.removesuffix("/v1").removesuffix("/v1/"),
        )

        self._store = Chroma(
            collection_name=collection_name,
            embedding_function=self._embeddings,
            persist_directory=persist_dir,
        )

        self._md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
            ],
            strip_headers=False,
        )
        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=200,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def _chunk_playbook(self, pb: Playbook) -> list[Document]:
        md_chunks = self._md_splitter.split_text(pb.content)
        result = []
        for chunk in md_chunks:
            header_ctx = _build_header_context(chunk.metadata)
            enriched = f"{header_ctx}\n\n{chunk.page_content}" if header_ctx else chunk.page_content
            if len(enriched) > 2000:
                for sub in self._text_splitter.split_text(enriched):
                    result.append(Document(
                        page_content=sub,
                        metadata={
                            **chunk.metadata,
                            "title": pb.title,
                            "category": pb.category,
                            "source": pb.source or "",
                        },
                    ))
            else:
                result.append(Document(
                    page_content=enriched,
                    metadata={
                        **chunk.metadata,
                        "title": pb.title,
                        "category": pb.category,
                        "source": pb.source or "",
                    },
                ))
        return result

    def add_playbook(self, playbook: Playbook):
        docs = self._chunk_playbook(playbook)
        if docs:
            self._store.add_documents(docs)

    def add_playbooks(self, playbooks: list[Playbook]):
        docs = []
        for pb in playbooks:
            docs.extend(self._chunk_playbook(pb))
        if docs:
            self._store.add_documents(docs)

    def search(
        self,
        category: str,
        query: str = "",
        n_results: int = 5,
        alert_message: str = "",
    ) -> list[Playbook]:
        parts = [f"category: {category}"]
        if query:
            parts.append(query)
        if alert_message:
            parts.append(alert_message[:300])
        rich_query = " | ".join(parts)

        where = {"category": category} if category != "unknown" else None

        docs = self._store.max_marginal_relevance_search(
            rich_query,
            k=n_results,
            fetch_k=n_results * 3,
            filter=where,
        )

        seen: set[str] = set()
        playbooks = []
        for doc in docs:
            key = f"{doc.metadata.get('title', '')}|{doc.page_content[:100]}"
            if key in seen:
                continue
            seen.add(key)
            playbooks.append(Playbook(
                title=doc.metadata.get("title", ""),
                category=doc.metadata.get("category", category),
                content=doc.page_content,
                source=doc.metadata.get("source", ""),
            ))
        return playbooks

    def count(self) -> int:
        return self._store._collection.count()

    def reset(self):
        name = self._store._collection.name
        self._store.delete_collection()
        self._store = Chroma(
            collection_name=name,
            embedding_function=self._embeddings,
            persist_directory=self._persist_dir,
        )


def _build_header_context(metadata: dict) -> str:
    parts = []
    for level in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        if level in metadata:
            prefix = "#" * int(level[1])
            parts.append(f"{prefix} {metadata[level]}")
    return "\n".join(parts)
