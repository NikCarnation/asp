import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional, List

from connector.normalizer.base import BaseNormalizer
from connector.normalizer.ecs import (
    ECSAlert, EcsEvent, EcsHost, EcsRule,
    EcsSource, EcsDestination, EcsNetwork,
    EcsThreat, EcsCompliance, EcsSeverity,
)
from connector.normalizer.wazuh.wazuh_base import WazuhAlert

logger = logging.getLogger(__name__)

LEVEL_TO_SEVERITY = {
    range(1, 4):   EcsSeverity.LOW,
    range(4, 8):   EcsSeverity.MEDIUM,
    range(8, 12):  EcsSeverity.HIGH,
    range(12, 17): EcsSeverity.CRITICAL,
}

GROUP_TO_CATEGORY = {
    "authentication_failed":  ["authentication"],
    "authentication_success": ["authentication"],
    "web":                    ["web", "network"],
    "intrusion_detection":    ["intrusion_detection", "network"],
    "malware":                ["malware"],
    "vulnerability":          ["vulnerability"],
    "firewall":               ["network"],
    "syslog":                 ["host"],
    "windows":                ["host"],
    "linux":                  ["host"],
}

GROUP_TO_TYPE = {
    "authentication_failed":  ["denied"],
    "authentication_success": ["allowed"],
    "malware":                ["indicator"],
    "intrusion_detection":    ["denied"],
    "firewall":               ["connection"],
    "vulnerability":          ["info"],
}


def _wazuh_level_to_severity(level: int) -> int:
    for level_range, severity in LEVEL_TO_SEVERITY.items():
        if level in level_range:
            return severity
    return EcsSeverity.UNKNOWN


def _parse_timestamp(ts: Optional[str]) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


def _generate_event_id(alert: WazuhAlert) -> str:
    if alert.id:
        return alert.id
    raw = f"{alert.timestamp}{alert.agent.id}{alert.rule.id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _map_categories(groups: List[str]) -> tuple[List[str], List[str]]:
    categories, types = set(), set()
    for group in groups:
        for key, cats in GROUP_TO_CATEGORY.items():
            if key in group.lower():
                categories.update(cats)
        for key, typs in GROUP_TO_TYPE.items():
            if key in group.lower():
                types.update(typs)
    return list(categories) or ["other"], list(types) or ["info"]


def _build_mitre_threats(mitre: Optional[dict]) -> Optional[List[EcsThreat]]:
    if not mitre:
        return None
    threats = []
    tactics   = mitre.get("tactic", [])
    techniques = mitre.get("technique", [])
    ids        = mitre.get("id", [])

    for i, technique in enumerate(techniques):
        threats.append(EcsThreat(
            framework="MITRE ATT&CK",
            tactic={"name": tactics[i] if i < len(tactics) else "unknown"},
            technique={"id": ids[i] if i < len(ids) else "unknown", "name": technique},
        ))
    return threats if threats else None


class WazuhNormalizer(BaseNormalizer):

    def can_handle(self, raw_alert: Any) -> bool:
        if isinstance(raw_alert, WazuhAlert):
            return True
        if isinstance(raw_alert, dict):
            return "rule" in raw_alert and "agent" in raw_alert
        return False

    def normalize(self, raw_alert: Any) -> ECSAlert:
        if isinstance(raw_alert, dict):
            raw_alert = WazuhAlert(**raw_alert)

        alert: WazuhAlert = raw_alert
        groups = alert.rule.groups

        categories, types = _map_categories(groups)
        severity = _wazuh_level_to_severity(alert.rule.level)

        event = EcsEvent(
            id=_generate_event_id(alert),
            kind="alert",
            category=categories,
            type=types,
            severity=severity,
            dataset="wazuh.alerts",
            module="wazuh",
            provider="wazuh",
            action=alert.rule.description,
            original=alert.full_log,
            created=datetime.now(timezone.utc),
        )

        host = EcsHost(
            id=alert.agent.id,
            name=alert.agent.name,
            ip=[alert.agent.ip] if alert.agent.ip else None,
        )

        rule = EcsRule(
            id=alert.rule.id,
            name=alert.rule.description,
            description=alert.rule.description,
            category=", ".join(groups) if groups else None,
            ruleset="wazuh",
        )

        src = dst = net = None
        if alert.data:
            d = alert.data
            if d.srcip:
                src = EcsSource(
                    ip=d.srcip,
                    port=int(d.srcport) if d.srcport and d.srcport.isdigit() else None,
                )
            if d.dstip:
                dst = EcsDestination(
                    ip=d.dstip,
                    port=int(d.dstport) if d.dstport and d.dstport.isdigit() else None,
                )
            if d.protocol:
                net = EcsNetwork(protocol=d.protocol.lower())

        threats = _build_mitre_threats(alert.rule.mitre if alert.rule.mitre else None)

        compliance = EcsCompliance(
            gdpr=alert.rule.gdpr,
            pci_dss=alert.rule.pci_dss,
            hipaa=alert.rule.hipaa,
            nist_800_53=alert.rule.nist_800_53,
        ) if any([alert.rule.gdpr, alert.rule.pci_dss,
                  alert.rule.hipaa, alert.rule.nist_800_53]) else None

        tags = list(groups) + ["wazuh"]
        if severity >= EcsSeverity.HIGH:
            tags.append("high-priority")

        return ECSAlert(
            timestamp=_parse_timestamp(alert.timestamp),
            event=event,
            host=host,
            rule=rule,
            source=src,
            destination=dst,
            network=net,
            threat=threats,
            compliance=compliance,
            tags=tags,
            labels={
                "wazuh_rule_level": str(alert.rule.level),
                "agent_id":         alert.agent.id,
            },
            message=alert.full_log or alert.rule.description,
            raw=alert.model_dump() if hasattr(alert, "model_dump") else None,
        )
