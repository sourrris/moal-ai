from __future__ import annotations

from typing import Any


def resolve_routing_destinations(destinations: list[dict], policy_json: dict[str, Any], severity: str) -> list[dict]:
    enabled_destinations = [item for item in destinations if bool(item.get("enabled"))]
    if not enabled_destinations:
        return []

    severity_map = policy_json.get("severity_destination_ids")
    if isinstance(severity_map, dict):
        raw_ids = severity_map.get(severity)
        if isinstance(raw_ids, list) and raw_ids:
            desired = {str(item) for item in raw_ids}
            selected = [item for item in enabled_destinations if str(item.get("destination_id")) in desired]
            if selected:
                return selected

    default_ids = policy_json.get("default_destination_ids")
    if isinstance(default_ids, list) and default_ids:
        desired = {str(item) for item in default_ids}
        selected = [item for item in enabled_destinations if str(item.get("destination_id")) in desired]
        if selected:
            return selected

    return enabled_destinations
