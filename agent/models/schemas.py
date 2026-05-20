from datetime import datetime
from pydantic import BaseModel


class NormalizedAlert(BaseModel):
    timestamp: datetime
    event_id: str
    event_kind: str = "alert"
    event_category: str = "unknown"
    event_type: str = "unknown"
    event_severity: int = 0
    rule_id: str = ""
    rule_name: str = ""
    rule_level: int = 0
    rule_description: str = ""
    source_ip: str | None = None
    source_port: int | None = None
    destination_ip: str | None = None
    destination_port: int | None = None
    user_name: str | None = None
    process_name: str | None = None
    network_protocol: str | None = None
    message: str = ""
    ecs_version: str = "8.11.0"
    raw: dict = {}


class PlanStep(BaseModel):
    order: int
    action: str
    description: str
    commands: list[str] = []
    expected_result: str = ""


class AnalysisPlan(BaseModel):
    alert_id: str
    incident_category: str
    created_at: datetime
    summary: str
    steps: list[PlanStep]
    raw_markdown: str = ""


class IncidentCategory(BaseModel):
    category: str
    confidence: float
    description: str = ""
