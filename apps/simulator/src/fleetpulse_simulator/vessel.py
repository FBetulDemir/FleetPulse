"""Physics of one simulated electric vessel. Pure logic with no I/O, so it is easy to test.

A vessel loops over its route. Each time it reaches its home port (the first waypoint)
it docks: a short stop if the battery is healthy, or until charged if it is low.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime

from fleetpulse_contracts import NavigationStatus, TelemetryMessage
from fleetpulse_simulator.geo import (
    METERS_PER_NAUTICAL_MILE,
    Position,
    bearing_deg,
    distance_m,
    move,
)

CRUISE_KNOTS = 8.0
ACCELERATION_KNOTS_PER_S = 0.5
DRAIN_PERCENT_PER_HOUR_AT_CRUISE = 12.0
CHARGE_PERCENT_PER_HOUR = 60.0
CHARGE_BELOW_PERCENT = 60.0
CHARGE_UNTIL_PERCENT = 95.0
SHORT_STOP_S = 60.0
MOTOR_TEMP_TIME_CONSTANT_S = 120.0


@dataclass
class Vessel:
    vessel_id: str
    device_id: str
    route: list[Position]
    rng: random.Random = field(default_factory=random.Random)
    battery_percent: float = 90.0
    dock_remaining_s: float = SHORT_STOP_S

    speed_knots: float = field(default=0.0, init=False)
    course_degrees: float = field(default=0.0, init=False)
    motor_temperature_c: float = field(default=15.0, init=False)
    status: NavigationStatus = field(default=NavigationStatus.DOCKED, init=False)
    position: Position = field(default=(0.0, 0.0), init=False)
    _target_index: int = field(default=1, init=False)
    _charging: bool = field(default=False, init=False)
    _elapsed_s: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if len(self.route) < 2:
            raise ValueError("a route needs at least two waypoints")
        self.position = self.route[0]
        self.course_degrees = bearing_deg(self.route[0], self.route[1])
        self._charging = self.battery_percent < CHARGE_BELOW_PERCENT

    @property
    def ambient_temperature_c(self) -> float:
        # Slow drift around 12 °C so the value is not perfectly flat.
        return 12.0 + 2.0 * math.sin(self._elapsed_s / 3600.0)

    def step(self, dt_s: float) -> None:
        self._elapsed_s += dt_s
        if self.status is NavigationStatus.DOCKED:
            self._step_docked(dt_s)
        else:
            self._step_underway(dt_s)
        self._update_motor_temperature(dt_s)

    def _step_docked(self, dt_s: float) -> None:
        self.speed_knots = 0.0
        self.battery_percent = min(
            100.0, self.battery_percent + CHARGE_PERCENT_PER_HOUR * dt_s / 3600
        )
        if self._charging and self.battery_percent >= CHARGE_UNTIL_PERCENT:
            self._charging = False
        self.dock_remaining_s -= dt_s
        if self.dock_remaining_s <= 0 and not self._charging:
            self.status = NavigationStatus.UNDERWAY

    def _step_underway(self, dt_s: float) -> None:
        target_speed = CRUISE_KNOTS + self.rng.uniform(-0.5, 0.5)
        max_change = ACCELERATION_KNOTS_PER_S * dt_s
        change = max(-max_change, min(max_change, target_speed - self.speed_knots))
        self.speed_knots = max(0.0, self.speed_knots + change)

        target = self.route[self._target_index]
        travel_m = self.speed_knots * METERS_PER_NAUTICAL_MILE * dt_s / 3600
        if travel_m >= distance_m(self.position, target):
            self._arrive(target)
        else:
            self.course_degrees = bearing_deg(self.position, target)
            self.position = move(self.position, self.course_degrees, travel_m)

        load = (self.speed_knots / CRUISE_KNOTS) ** 2
        drain = DRAIN_PERCENT_PER_HOUR_AT_CRUISE * load * dt_s / 3600
        self.battery_percent = max(0.0, self.battery_percent - drain)

    def _arrive(self, waypoint: Position) -> None:
        self.position = waypoint
        self._target_index = (self._target_index + 1) % len(self.route)
        self.course_degrees = bearing_deg(waypoint, self.route[self._target_index])
        if waypoint == self.route[0]:
            self.status = NavigationStatus.DOCKED
            self.speed_knots = 0.0
            self.dock_remaining_s = SHORT_STOP_S
            self._charging = self.battery_percent < CHARGE_BELOW_PERCENT

    def _update_motor_temperature(self, dt_s: float) -> None:
        target = self.ambient_temperature_c + 8.0 + 4.0 * self.speed_knots
        alpha = 1 - math.exp(-dt_s / MOTOR_TEMP_TIME_CONSTANT_S)
        self.motor_temperature_c += (target - self.motor_temperature_c) * alpha

    def telemetry(self, now: datetime) -> TelemetryMessage:
        """Current state as a message, with a little sensor noise added."""
        lat, lon = self.position
        speed = max(0.0, self.speed_knots + self.rng.gauss(0, 0.05)) if self.speed_knots else 0.0
        voltage = 22.0 + 4.0 * self.battery_percent / 100 + self.rng.gauss(0, 0.02)
        return TelemetryMessage(
            vessel_id=self.vessel_id,
            device_id=self.device_id,
            timestamp=now,
            latitude=round(lat, 6),
            longitude=round(lon, 6),
            speed_knots=round(speed, 2),
            course_degrees=round(self.course_degrees, 1) % 360,
            battery_percent=round(self.battery_percent, 1),
            battery_voltage=round(voltage, 2),
            motor_temperature_c=round(self.motor_temperature_c + self.rng.gauss(0, 0.2), 1),
            ambient_temperature_c=round(self.ambient_temperature_c, 1),
            status=self.status,
        )
