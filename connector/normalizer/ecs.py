from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field

from agent.models.schemas import NormalizedAlert


class EcsSeverity(int, Enum):
    UNKNOWN  = 0
    LOW      = 1
    MEDIUM   = 2
    HIGH     = 3
    CRITICAL = 4


class EcsEvent(BaseModel):
    id: str
    kind: str = "alert"
    category: List[str] = []
    type: List[str] = []
    severity: int = EcsSeverity.UNKNOWN
    outcome: Optional[str] = None
    action: Optional[str] = None
    dataset: str = "wazuh.alerts"
    module: str = "wazuh"
    provider: str = "wazuh"
    created: datetime = Field(default_factory=datetime.utcnow)
    original: Optional[str] = None


class EcsHost(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    ip: Optional[List[str]] = None
    hostname: Optional[str] = None
    os: Optional[Dict[str, Any]] = None


class EcsSource(BaseModel):
    ip: Optional[str] = None
    port: Optional[int] = None
    domain: Optional[str] = None
    geo: Optional[Dict[str, Any]] = None


class EcsDestination(BaseModel):
    ip: Optional[str] = None
    port: Optional[int] = None
    domain: Optional[str] = None


class EcsNetwork(BaseModel):
    protocol: Optional[str] = None
    transport: Optional[str] = None
    direction: Optional[str] = None


class EcsThreat(BaseModel):
    framework: str = "MITRE ATT&CK"
    tactic: Optional[Dict[str, Any]] = None
    technique: Optional[Dict[str, Any]] = None


class EcsRule(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    version: Optional[str] = None
    ruleset: Optional[str] = "wazuh"
    reference: Optional[str] = None


class EcsCompliance(BaseModel):
    gdpr: Optional[List[str]] = None
    pci_dss: Optional[List[str]] = None
    hipaa: Optional[List[str]] = None
    nist_800_53: Optional[List[str]] = None


class ECSAlert(BaseModel):
    schema_version: str = "8.11.0"
    source_system: str = "wazuh"
    timestamp: datetime
    event: EcsEvent
    host: EcsHost
    rule: EcsRule
    source: Optional[EcsSource] = None
    destination: Optional[EcsDestination] = None
    network: Optional[EcsNetwork] = None
    threat: Optional[List[EcsThreat]] = None
    tags: List[str] = []
    labels: Dict[str, str] = {}
    message: Optional[str] = None
    compliance: Optional[EcsCompliance] = None
    raw: Optional[Dict[str, Any]] = None

    model_config = {"use_enum_values": True}


def normalize_wazuh_alert(raw: dict) -> NormalizedAlert:
    data = raw.get("data", raw)
    rule = data.get("rule", {})

    ts = data.get("timestamp", datetime.utcnow().isoformat())
    if isinstance(ts, str):
        ts = ts.replace("Z", "+00:00")
        ts = datetime.fromisoformat(ts)

    return NormalizedAlert(
        timestamp=ts,
        event_id=data.get("id", data.get("_id", "")),
        event_kind="alert",
        event_category=rule.get("category", "unknown"),
        event_type="unknown",
        event_severity=rule.get("level", 0),
        rule_id=str(rule.get("id", "")),
        rule_name=rule.get("name", ""),
        rule_level=rule.get("level", 0),
        rule_description=rule.get("description", ""),
        source_ip=data.get("srcip"),
        source_port=data.get("srcport"),
        destination_ip=data.get("dstip"),
        destination_port=data.get("dstport"),
        user_name=data.get("user"),
        network_protocol=data.get("protocol"),
        message=data.get("full_log") or rule.get("description", ""),
        raw=data,
    )
