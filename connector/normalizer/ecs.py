from datetime import datetime, timezone

from agent.models.schemas import NormalizedAlert


def normalize_wazuh_alert(raw: dict) -> NormalizedAlert:
    data = raw.get("data", raw)

    rule = data.get("rule", {})

    timestamp_str = data.get("timestamp") or data.get("@timestamp") or datetime.now(timezone.utc).isoformat()
    if timestamp_str.endswith("Z"):
        timestamp_str = timestamp_str[:-1] + "+00:00"

    return NormalizedAlert(
        timestamp=datetime.fromisoformat(timestamp_str),
        event_id=data.get("id", data.get("_id", "")),
        event_kind="alert",
        event_category=_map_category(rule.get("category", "")),
        event_type=_map_type(rule.get("level", 0)),
        event_severity=rule.get("level", 0),
        rule_id=rule.get("id", ""),
        rule_name=rule.get("name", ""),
        rule_level=rule.get("level", 0),
        rule_description=rule.get("description", ""),
        source_ip=_get_source_ip(data),
        source_port=data.get("srcport") or data.get("source", {}).get("port"),
        destination_ip=_get_dest_ip(data),
        destination_port=data.get("dstport") or data.get("destination", {}).get("port"),
        user_name=_get_user(data),
        process_name=data.get("process", {}).get("name"),
        network_protocol=data.get("protocol", ""),
        message=data.get("full_log", data.get("message", "")),
        ecs_version="8.11.0",
        raw=raw,
    )


def _map_category(category: str) -> str:
    mapping = {
        "authentication": "authentication",
        "authentication_failed": "authentication",
        "invalid_login": "authentication",
        "firewall": "network",
        "web": "web",
        "malware": "malware",
        "syslog": "system",
        "policy": "compliance",
    }
    return mapping.get(category.lower(), category.lower() or "unknown")


def _map_type(level: int) -> str:
    if level >= 12:
        return "critical"
    if level >= 7:
        return "warning"
    if level >= 4:
        return "info"
    return "notice"


def _get_source_ip(data: dict) -> str | None:
    for key in ("srcip", "src_ip", "source_ip", "source.ip"):
        if val := data.get(key):
            return val
    if src := data.get("source"):
        return src.get("ip") or src.get("address")
    return None


def _get_dest_ip(data: dict) -> str | None:
    for key in ("dstip", "dst_ip", "dest_ip", "destination.ip"):
        if val := data.get(key):
            return val
    if dst := data.get("destination"):
        return dst.get("ip") or dst.get("address")
    return None


def _get_user(data: dict) -> str | None:
    for key in ("user", "username", "user.name"):
        val = data.get(key)
        if isinstance(val, dict):
            return val.get("name") or val.get("id")
        if val:
            return str(val)
    return None
