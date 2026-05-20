from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent.categorizer import Categorizer
from agent.config import AgentConfig
from agent.pipeline import AgentPipeline
from agent.planner import Planner
from agent.rag.knowledge_base import ALL_PLAYBOOKS
from agent.rag.vector_store import VectorStore

config = AgentConfig()

categorizer: Categorizer | None = None
planner: Planner | None = None
vector_store: VectorStore | None = None
pipeline: AgentPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global categorizer, planner, vector_store, pipeline

    categorizer = Categorizer(
        base_url=config.ollama_base_url,
        model=config.small_llm_model,
    )

    planner = Planner(
        base_url=config.ollama_base_url,
        model=config.large_llm_model,
    )

    vector_store = VectorStore(
        host=config.chroma_host,
        port=config.chroma_port,
        collection_name=config.chroma_collection,
    )

    if vector_store.count() == 0:
        vector_store.add_playbooks(ALL_PLAYBOOKS)

    pipeline = AgentPipeline(
        categorizer=categorizer,
        planner=planner,
        vector_store=vector_store,
    )

    yield


app = FastAPI(title="AISOC Agent", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "module": "agent",
        "playbooks_count": vector_store.count() if vector_store else 0,
        "small_llm": config.small_llm_model,
        "large_llm": config.large_llm_model,
    }


@app.post("/api/v1/process")
async def process_alert(alert: dict):
    from agent.models.schemas import NormalizedAlert
    if not pipeline:
        return {"error": "pipeline not initialized"}
    normalized = NormalizedAlert(**alert)
    plan = await pipeline.process(normalized)
    return plan.model_dump(mode="json")


@app.post("/api/v1/process/alert")
async def process_alert_full(alert: NormalizedAlert):
    if not pipeline:
        return {"error": "pipeline not initialized"}
    plan = await pipeline.process(alert)
    return plan.model_dump(mode="json")


@app.get("/api/v1/playbooks")
async def list_playbooks():
    if not vector_store:
        return {"error": "not initialized"}
    return {"playbooks": [pb.model_dump() for pb in ALL_PLAYBOOKS]}


@app.post("/api/v1/playbooks/reload")
async def reload_playbooks():
    if not vector_store:
        return {"error": "not initialized"}
    vector_store.reset()
    vector_store.add_playbooks(ALL_PLAYBOOKS)
    return {"status": "ok", "count": vector_store.count()}
