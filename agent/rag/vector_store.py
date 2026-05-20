import uuid

import chromadb

from agent.rag.knowledge_base import Playbook


class VectorStore:
    def __init__(
        self, host: str, port: int, collection_name: str, persist_dir: str = "./chroma_data"
    ):
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def add_playbook(self, playbook: Playbook):
        doc_id = str(uuid.uuid4())
        metadata = {
            "title": playbook.title,
            "category": playbook.category,
            "source": playbook.source or "",
        }
        self.collection.add(
            documents=[playbook.content],
            metadatas=[metadata],
            ids=[doc_id],
        )

    def add_playbooks(self, playbooks: list[Playbook]):
        docs = []
        metas = []
        ids = []
        for pb in playbooks:
            doc_id = str(uuid.uuid4())
            docs.append(pb.content)
            metas.append(
                {
                    "title": pb.title,
                    "category": pb.category,
                    "source": pb.source or "",
                }
            )
            ids.append(doc_id)
        if docs:
            self.collection.add(documents=docs, metadatas=metas, ids=ids)

    def search(self, category: str, query: str = "", n_results: int = 3) -> list[Playbook]:
        search_query = query or category
        results = self.collection.query(
            query_texts=[search_query],
            n_results=n_results,
            where={"category": category} if category != "unknown" else None,
        )
        playbooks = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = (
                    results["metadatas"][0][i]
                    if results["metadatas"] and results["metadatas"][0]
                    else {}
                )
                playbooks.append(
                    Playbook(
                        title=meta.get("title", ""),
                        category=meta.get("category", ""),
                        content=doc,
                        source=meta.get("source", ""),
                    )
                )
        return playbooks

    def count(self) -> int:
        return self.collection.count()

    def reset(self):
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(name=self.collection.name)
