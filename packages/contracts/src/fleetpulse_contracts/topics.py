"""MQTT topic names. Every service builds topics through these helpers."""

PREFIX = "fleetpulse/v1"

TELEMETRY_SUBSCRIPTION = f"{PREFIX}/vessels/+/telemetry"
STATUS_SUBSCRIPTION = f"{PREFIX}/vessels/+/status"
ALERTS_TOPIC = f"{PREFIX}/alerts"


def telemetry_topic(vessel_id: str) -> str:
    return f"{PREFIX}/vessels/{vessel_id}/telemetry"


def status_topic(vessel_id: str) -> str:
    return f"{PREFIX}/vessels/{vessel_id}/status"


def vessel_id_from_topic(topic: str) -> str | None:
    """Return the vessel id from a vessel topic, or None if the topic has another shape."""
    parts = topic.split("/")
    if len(parts) != 5 or "/".join(parts[:2]) != PREFIX or parts[2] != "vessels" or not parts[3]:
        return None
    return parts[3]
