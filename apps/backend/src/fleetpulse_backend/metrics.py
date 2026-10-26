"""Numeric telemetry fields that can be charted, averaged and used in alert rules."""

from enum import StrEnum


class Metric(StrEnum):
    """Metrics with meaningful averages. Course is left out on purpose: it is an angle,
    and the average of 359° and 1° is 180°, which is wrong."""

    SPEED_KNOTS = "speed_knots"
    BATTERY_PERCENT = "battery_percent"
    BATTERY_VOLTAGE = "battery_voltage"
    MOTOR_TEMPERATURE_C = "motor_temperature_c"
    AMBIENT_TEMPERATURE_C = "ambient_temperature_c"


UNITS: dict[Metric, str] = {
    Metric.SPEED_KNOTS: "kn",
    Metric.BATTERY_PERCENT: "%",
    Metric.BATTERY_VOLTAGE: "V",
    Metric.MOTOR_TEMPERATURE_C: "°C",
    Metric.AMBIENT_TEMPERATURE_C: "°C",
}
