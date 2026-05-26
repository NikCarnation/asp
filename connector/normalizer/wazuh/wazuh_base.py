from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class WazuhRule(BaseModel):
    id: str
    level: int
    description: str
    groups: List[str] = []
    mitre: Optional[Dict[str, Any]] = None
    gdpr: Optional[List[str]] = None
    pci_dss: Optional[List[str]] = None
    hipaa: Optional[List[str]] = None
    nist_800_53: Optional[List[str]] = None


class WazuhAgent(BaseModel):
    id: str = "000"
    name: str = "unknown"
    ip: Optional[str] = None


class WazuhData(BaseModel):
    srcip: Optional[str] = None
    dstip: Optional[str] = None
    srcport: Optional[str] = None
    dstport: Optional[str] = None
    protocol: Optional[str] = None
    url: Optional[str] = None
    id: Optional[str] = None

    model_config = {"extra": "allow"}


class WazuhAlert(BaseModel):
    """
    Модель входящего алерта от Wazuh.
    Принимает как webhook payload, так и документ из индексера.
    """
    id: Optional[str] = Field(None, alias="_id")
    timestamp: Optional[str] = None
    rule: WazuhRule
    agent: WazuhAgent = Field(default_factory=WazuhAgent)
    manager: Optional[Dict[str, Any]] = None
    location: Optional[str] = None
    full_log: Optional[str] = None
    data: Optional[WazuhData] = None
    decoder: Optional[Dict[str, Any]] = None
    input: Optional[Dict[str, Any]] = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class WazuhAlertBatch(BaseModel):
    """Пакет алертов из индексера."""
    alerts: List[WazuhAlert]
    total: int
    took_ms: int