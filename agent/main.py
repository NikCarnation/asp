import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent.categorizer import Categorizer
from agent.config import AgentConfig
from agent.models.schemas import NormalizedAlert
from agent.pipeline import AgentPipeline
from agent.planner import Planner
from agent.rag.knowledge_base import ALL_PLAYBOOKS
from agent.rag.vector_store import VectorStore
from connector.broker.rabbit import RabbitConsumer

logger = logging.getLogger(__name__)

config = AgentConfig()

categorizer: Categorizer | None = None
planner: Planner | None = None
vector_store: VectorStore | None = None
pipeline: AgentPipeline | None = None


async def handle_alert(alert: NormalizedAlert):
    logger.info("Processing alert %s via RabbitMQ", alert.event_id)
    if not pipeline:
        logger.error("Pipeline not initialized")
        return
    try:
        plan = await pipeline.process(alert)
        logger.info("Plan generated for alert %s: %s", alert.event_id, plan.summary[:100])
    except Exception as e:
        logger.error("Failed to process alert %s: %s", alert.event_id, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global categorizer, planner, vector_store, pipeline

    categorizer = Categorizer(
        base_url=config.llm_base_url,
        model=config.small_llm_model,
        api_key=config.llm_api_key,
    )

    planner = Planner(
        base_url=config.llm_base_url,
        model=config.large_llm_model,
        api_key=config.llm_api_key,
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
        db_path=config.db_path,
        verbose=config.verbose,
    )

    consumer = RabbitConsumer(
        host=config.rabbitmq_host,
        port=config.rabbitmq_port,
        user=config.rabbitmq_user,
        password=config.rabbitmq_pass,
        queue=config.rabbitmq_queue,
    )
    asyncio.create_task(consumer.consume(handle_alert))

    yield

    await consumer.close()


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
