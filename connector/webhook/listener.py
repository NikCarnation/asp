import logging

from fastapi import APIRouter, HTTPException, Request

from agent.models.schemas import NormalizedAlert
from connector.broker.rabbit import RabbitPublisher
from connector.normalizer.ecs import normalize_wazuh_alert

logger = logging.getLogger(__name__)

router = APIRouter()
publisher: RabbitPublisher | None = None
use_rabbitmq: bool = True


def init_publisher(pub: RabbitPublisher, use_rmq: bool = True):
    global publisher, use_rabbitmq
    publisher = pub
    use_rabbitmq = use_rmq


@router.post("/webhook/wazuh")
async def wazuh_webhook(request: Request):
    body = await request.json()
    alert = normalize_wazuh_alert(body)
    
    if use_rabbitmq:
        if not publisher:
            raise HTTPException(status_code=503, detail="Publisher not initialized")
        await publisher.publish(alert)
        logger.info("Webhook: published alert %s to RabbitMQ", alert.event_id)
    else:
        logger.info("Webhook: alert %s received (direct mode, no RabbitMQ)", alert.event_id)
    
    return {"status": "ok", "event_id": alert.event_id}


@router.post("/webhook/generic")
async def generic_webhook(request: Request):
    body = await request.json()
    alert = NormalizedAlert(**body)
    
    if use_rabbitmq:
        if not publisher:
            raise HTTPException(status_code=503, detail="Publisher not initialized")
        await publisher.publish(alert)
        logger.info("Generic webhook: published alert %s to RabbitMQ", alert.event_id)
    else:
        logger.info("Generic webhook: alert %s received (direct mode, no RabbitMQ)", alert.event_id)
    
    return {"status": "ok", "event_id": alert.event_id}
