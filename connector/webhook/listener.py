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


async def _try_publish(alert: NormalizedAlert) -> None:
    global publisher
    if not publisher:
        raise HTTPException(status_code=503, detail="Publisher not initialized")
    if not publisher.channel:
        await publisher.connect()
    await publisher.publish(alert)


@router.post("/webhook/wazuh")
async def wazuh_webhook(request: Request):
    body = await request.json()
    alert = normalize_wazuh_alert(body)
    
    if use_rabbitmq:
        try:
            await _try_publish(alert)
            logger.info("Webhook: published alert %s to RabbitMQ", alert.event_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Webhook: failed to publish alert %s: %s", alert.event_id, e)
            raise HTTPException(status_code=502, detail=f"RabbitMQ error: {e}")
    else:
        logger.info("Webhook: alert %s received (direct mode, no RabbitMQ)", alert.event_id)
    
    return {"status": "ok", "event_id": alert.event_id}


@router.post("/webhook/generic")
async def generic_webhook(request: Request):
    body = await request.json()
    alert = NormalizedAlert(**body)
    
    if use_rabbitmq:
        try:
            await _try_publish(alert)
            logger.info("Generic webhook: published alert %s to RabbitMQ", alert.event_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Generic webhook: failed to publish alert %s: %s", alert.event_id, e)
            raise HTTPException(status_code=502, detail=f"RabbitMQ error: {e}")
    else:
        logger.info("Generic webhook: alert %s received (direct mode, no RabbitMQ)", alert.event_id)
    
    return {"status": "ok", "event_id": alert.event_id}
