import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from agent.models.schemas import NormalizedAlert
from connector.broker.rabbit import RabbitPublisher
from connector.config import ConnectorConfig
from connector.normalizer.ecs import normalize_wazuh_alert
from connector.schemas import PublishBatchRequest, PublishRequest, SendPlanRequest
from connector.siem_clients.base import SiemClient
from connector.siem_clients.indexer import IndexerClient
from connector.webhook.listener import init_publisher, router as webhook_router

logger = logging.getLogger(__name__)

config = ConnectorConfig()

siem_client: SiemClient | None = None
rabbit_publisher: RabbitPublisher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global siem_client, rabbit_publisher

    if config.use_rabbitmq:
        rabbit_publisher = RabbitPublisher(
            host=config.rabbitmq_host,
            port=config.rabbitmq_port,
            user=config.rabbitmq_user,
            password=config.rabbitmq_pass,
            queue=config.rabbitmq_queue,
        )
        try:
            await rabbit_publisher.connect()
            logger.info("RabbitMQ publisher initialized")
        except Exception as e:
            logger.warning("RabbitMQ not available at startup, will retry on publish: %s", e)
        init_publisher(rabbit_publisher, use_rmq=True)
    else:
        logger.info("RabbitMQ disabled by configuration (use_rabbitmq=False)")
        init_publisher(None, use_rmq=False)

    logger.info("Using IndexerClient: %s", config.indexer_url)
    siem_client = IndexerClient(
        url=config.indexer_url,
        user=config.indexer_user,
        password=config.indexer_pass,
        index_prefix=config.indexer_prefix,
        verify_ssl=config.wazuh_verify_ssl,
    )

    yield

    if rabbit_publisher and rabbit_publisher.connection:
        await rabbit_publisher.close()
    if siem_client:
        await siem_client.close()


app = FastAPI(title="AISOC Connector", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(webhook_router)


_ui_path = Path(__file__).resolve().parent / "ui" / "index.html"
_ui_html = _ui_path.read_text(encoding="utf-8") if _ui_path.exists() else "<h1>UI not found</h1>"


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/")
async def ui_root():
    return HTMLResponse(content=_ui_html, headers={"Connection": "close"})


@app.get("/ui")
async def ui_root_alt():
    return await ui_root()


@app.get("/health")
async def health():
    return {"status": "ok", "module": "connector"}


@app.get("/health/rabbitmq")
async def health_rabbitmq():
    if not rabbit_publisher:
        return {"status": "disabled", "module": "rabbitmq"}
    try:
        conn = rabbit_publisher.connection
        if conn and not conn.is_closed:
            return {"status": "ok", "module": "rabbitmq"}
        await asyncio.wait_for(rabbit_publisher.connect(), timeout=3.0)
        return {"status": "ok", "module": "rabbitmq"}
    except asyncio.TimeoutError:
        return {"status": "error", "module": "rabbitmq", "detail": "timeout"}
    except Exception as e:
        return {"status": "error", "module": "rabbitmq", "detail": str(e)}


@app.get("/api/v1/alerts")
async def get_alerts(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    source_ip: str | None = Query(default=None, description="Filter by source IP"),
    destination_ip: str | None = Query(default=None, description="Filter by destination IP"),
    rule_id: str | None = Query(default=None, description="Filter by rule ID"),
    rule_level_min: int | None = Query(default=None, description="Minimum rule level"),
    rule_level_max: int | None = Query(default=None, description="Maximum rule level"),
    protocol: str | None = Query(default=None, description="Network protocol"),
    user_name: str | None = Query(default=None, description="Filter by username"),
    agent_id: str | None = Query(default=None, description="Filter by agent ID"),
    agent_name: str | None = Query(default=None, description="Filter by agent name"),
    location: str | None = Query(default=None, description="Log location"),
    rule_groups: str | None = Query(default=None, description="Rule groups (comma-separated)"),
    rule_description: str | None = Query(default=None, description="Search in rule description"),
    full_log: str | None = Query(default=None, description="Search in full log"),
):
    if not siem_client:
        raise HTTPException(status_code=503, detail="SIEM client not initialized")

    filters = {}
    if source_ip is not None:
        filters["source_ip"] = source_ip
    if destination_ip is not None:
        filters["destination_ip"] = destination_ip
    if rule_id is not None:
        filters["rule_id"] = rule_id
    if rule_level_min is not None:
        filters["rule_level_min"] = rule_level_min
    if rule_level_max is not None:
        filters["rule_level_max"] = rule_level_max
    if protocol is not None:
        filters["protocol"] = protocol
    if user_name is not None:
        filters["user_name"] = user_name
    if agent_id is not None:
        filters["agent_id"] = agent_id
    if agent_name is not None:
        filters["agent_name"] = agent_name
    if location is not None:
        filters["location"] = location
    if rule_groups is not None:
        filters["rule_groups"] = [g.strip() for g in rule_groups.split(",") if g.strip()]
    if rule_description is not None:
        filters["rule_description"] = rule_description
    if full_log is not None:
        filters["full_log"] = full_log


    try:
        alerts = await siem_client.fetch_alerts(
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            filters=filters or None,
        )
    except Exception as e:
        logger.error("Failed to fetch alerts: %s", e)
        raise HTTPException(status_code=502, detail=f"SIEM API error: {e}")
    return {
        "alerts": [a.model_dump(mode="json") for a in alerts],
        "count": len(alerts),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/alerts/{alert_id}")
async def get_alert(alert_id: str):
    if not siem_client:
        raise HTTPException(status_code=503, detail="SIEM client not initialized")
    try:
        alert = await siem_client.get_alert_by_id(alert_id)
    except Exception as e:
        logger.error("Failed to get alert %s: %s", alert_id, e)
        raise HTTPException(status_code=502, detail=f"SIEM API error: {e}")
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert.model_dump(mode="json")


@app.post("/api/v1/publish")
async def publish_alert(body: PublishRequest):
    if not siem_client:
        raise HTTPException(status_code=503, detail="Connector not initialized")
    
    try:
        alert = await siem_client.get_alert_by_id(body.alert_id)
    except Exception as e:
        logger.error("Failed to get alert %s: %s", body.alert_id, e)
        raise HTTPException(status_code=502, detail=f"SIEM API error: {e}")
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    if config.use_rabbitmq:
        if not rabbit_publisher:
            raise HTTPException(status_code=503, detail="RabbitMQ publisher not initialized")
        await rabbit_publisher.publish(alert)
        return {"status": "published", "event_id": body.alert_id, "mode": "rabbitmq"}
    else:
        return {"status": "received", "event_id": body.alert_id, "mode": "direct"}


@app.post("/api/v1/publish/batch")
async def publish_alerts_batch(body: PublishBatchRequest):
    if not siem_client:
        raise HTTPException(status_code=503, detail="Connector not initialized")
    
    published = []
    errors = []
    for alert_id in body.alert_ids:
        try:
            alert = await siem_client.get_alert_by_id(alert_id)
        except Exception as e:
            logger.error("Failed to get alert %s: %s", alert_id, e)
            errors.append(alert_id)
            continue
        if not alert:
            errors.append(alert_id)
            continue
        if config.use_rabbitmq:
            if not rabbit_publisher:
                raise HTTPException(status_code=503, detail="RabbitMQ publisher not initialized")
            await rabbit_publisher.publish(alert)
        published.append(alert_id)
    
    mode = "rabbitmq" if config.use_rabbitmq else "direct"
    return {"published": published, "errors": errors, "total": len(body.alert_ids), "mode": mode}


@app.post("/api/v1/publish/date-range")
async def publish_alerts_by_date_range(
    start_date: datetime = Query(),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    if not siem_client:
        raise HTTPException(status_code=503, detail="Connector not initialized")
    
    try:
        alerts = await siem_client.fetch_alerts(
            limit=limit,
            offset=0,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.error("Failed to fetch alerts: %s", e)
        raise HTTPException(status_code=502, detail=f"SIEM API error: {e}")
    
    if config.use_rabbitmq:
        if not rabbit_publisher:
            raise HTTPException(status_code=503, detail="RabbitMQ publisher not initialized")
        for alert in alerts:
            await rabbit_publisher.publish(alert)
    
    mode = "rabbitmq" if config.use_rabbitmq else "direct"
    return {"published": len(alerts), "start_date": start_date.isoformat(), "end_date": end_date.isoformat() if end_date else None, "mode": mode}


@app.post("/api/v1/plan/{alert_id}")
async def send_plan_to_siem(alert_id: str, body: SendPlanRequest):
    if not siem_client:
        raise HTTPException(status_code=503, detail="SIEM client not initialized")
    try:
        success = await siem_client.send_plan(alert_id, body.plan)
    except Exception as e:
        logger.error("Failed to send plan for alert %s: %s", alert_id, e)
        raise HTTPException(status_code=502, detail=f"SIEM API error: {e}")
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send plan")
    return {"status": "ok", "alert_id": alert_id}


@app.post("/api/v1/alerts/direct")
async def receive_alert_direct(body: dict):
    """Receive alert directly without RabbitMQ - for immediate processing"""
    alert = normalize_wazuh_alert(body) if "rule" in body.get("data", {}) else NormalizedAlert(**body)
    logger.info("Direct alert received: %s", alert.event_id)
    return {"status": "received", "event_id": alert.event_id, "mode": "direct"}
