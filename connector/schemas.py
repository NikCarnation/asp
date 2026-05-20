from pydantic import BaseModel


class PublishRequest(BaseModel):
    alert_id: str


class PublishBatchRequest(BaseModel):
    alert_ids: list[str]


class SendPlanRequest(BaseModel):
    plan: dict
