import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from connector.broker.rabbit import RabbitPublisher
from connector.config import ConnectorConfig
from connector.normalizer.ecs import normalize_wazuh_alert
from connector.schemas import PublishBatchRequest, PublishRequest, SendPlanRequest
from connector.siem_clients.base import SiemClient
from connector.siem_clients.wazuh import WazuhClient
from connector.webhook.listener import init_publisher, router as webhook_router
from agent.models.schemas import NormalizedAlert

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
            init_publisher(rabbit_publisher, use_rmq=True)
            logger.info("RabbitMQ publisher initialized")
        except Exception as e:
            logger.warning("RabbitMQ not available, continuing without broker: %s", e)
            rabbit_publisher = None
            init_publisher(None, use_rmq=False)
    else:
        logger.info("RabbitMQ disabled by configuration (use_rabbitmq=False)")
        init_publisher(None, use_rmq=False)

    if config.wazuh_mock:
        logger.info("Using MockWazuhClient")
    else:
        logger.info("Using WazuhClient: %s", config.wazuh_api_url)
        siem_client = WazuhClient(
            api_url=config.wazuh_api_url,
            api_user=config.wazuh_api_user,
            api_pass=config.wazuh_api_pass,
        )

    yield

    if rabbit_publisher and rabbit_publisher.connection:
        await rabbit_publisher.close()
    if siem_client:
        await siem_client.close()


app = FastAPI(title="AISOC Connector", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/health")
async def health():
    return {"status": "ok", "module": "connector"}


@app.get("/api/v1/alerts")
async def get_alerts(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
):
    if not siem_client:
        raise HTTPException(status_code=503, detail="SIEM client not initialized")
    alerts = await siem_client.fetch_alerts(
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
    )
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
    alert = await siem_client.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert.model_dump(mode="json")


@app.post("/api/v1/publish")
async def publish_alert(body: PublishRequest):
    if not siem_client:
        raise HTTPException(status_code=503, detail="Connector not initialized")
    
    alert = await siem_client.get_alert_by_id(body.alert_id)
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
        alert = await siem_client.get_alert_by_id(alert_id)
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
    
    alerts = await siem_client.fetch_alerts(
        limit=limit,
        offset=0,
        start_date=start_date,
        end_date=end_date,
    )
    
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
    success = await siem_client.send_plan(alert_id, body.plan)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send plan")
    return {"status": "ok", "alert_id": alert_id}


@app.post("/api/v1/alerts/direct")
async def receive_alert_direct(body: dict):
    """Receive alert directly without RabbitMQ - for immediate processing"""
    alert = normalize_wazuh_alert(body) if "rule" in body.get("data", {}) else NormalizedAlert(**body)
    logger.info("Direct alert received: %s", alert.event_id)
    return {"status": "received", "event_id": alert.event_id, "mode": "direct"}
