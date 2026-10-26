import random
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fleetpulse_contracts import NavigationStatus, TelemetryMessage
from fleetpulse_contracts.commands import Scenario
from fleetpulse_simulator.config import Settings
from fleetpulse_simulator.geo import bearing_deg, distance_m, move
from fleetpulse_simulator.main import build_fleet, invalid_payload, parse_command
from fleetpulse_simulator.routes import ROUTES
from fleetpulse_simulator.vessel import CHARGE_UNTIL_PERCENT, Vessel

NOW = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)


def make_vessel(**kwargs: float) -> Vessel:
    return Vessel(
        vessel_id="vessel-001",
        device_id="device-001",
        route=ROUTES[0],
        rng=random.Random(42),
        **kwargs,  # type: ignore[arg-type]
    )


def run(vessel: Vessel, seconds: int) -> None:
    for _ in range(seconds):
        vessel.step(1.0)


def test_move_then_measure_round_trip() -> None:
    start = (57.70, 11.95)
    end = move(start, 90.0, 1000.0)

    assert distance_m(start, end) == pytest.approx(1000.0, rel=1e-6)
    assert bearing_deg(start, end) == pytest.approx(90.0, abs=0.01)


def test_departs_after_short_stop_and_moves_toward_next_waypoint() -> None:
    vessel = make_vessel(battery_percent=90.0, dock_remaining_s=5.0)
    start = vessel.position

    run(vessel, 60)

    assert vessel.status is NavigationStatus.UNDERWAY
    assert vessel.speed_knots > 6
    assert distance_m(vessel.position, ROUTES[0][1]) < distance_m(start, ROUTES[0][1])


def test_battery_drains_while_underway() -> None:
    vessel = make_vessel(battery_percent=90.0, dock_remaining_s=0.0)

    run(vessel, 600)

    assert vessel.battery_percent < 90.0


def test_low_battery_vessel_stays_docked_until_charged() -> None:
    vessel = make_vessel(battery_percent=40.0, dock_remaining_s=0.0)

    run(vessel, 600)
    assert vessel.status is NavigationStatus.DOCKED

    for _ in range(4 * 3600):
        vessel.step(1.0)
        if vessel.status is NavigationStatus.UNDERWAY:
            break

    assert vessel.status is NavigationStatus.UNDERWAY
    assert vessel.battery_percent >= CHARGE_UNTIL_PERCENT


def test_completes_a_loop_and_docks_at_home() -> None:
    vessel = make_vessel(battery_percent=90.0, dock_remaining_s=0.0)
    docked_at_home = False

    for _ in range(4 * 3600):
        vessel.step(1.0)
        if vessel.status is NavigationStatus.DOCKED:
            docked_at_home = vessel.position == ROUTES[0][0]
            break

    assert docked_at_home


def test_telemetry_is_always_valid() -> None:
    # Constructing TelemetryMessage validates every field, so this would raise on bad data.
    for vessel in build_fleet(Settings(random_seed=1)):
        for _ in range(3 * 3600):
            vessel.step(1.0)
            vessel.telemetry(NOW)


def test_fleet_ids_are_unique_and_formatted() -> None:
    fleet = build_fleet(Settings(random_seed=1))

    assert [v.vessel_id for v in fleet] == [f"vessel-00{i}" for i in range(1, 6)]
    assert len({v.device_id for v in fleet}) == 5


# Demo scenarios: each must cross its alert threshold within seconds, and end by itself.


@pytest.mark.parametrize("docked", [False, True])
def test_overheat_crosses_the_alert_threshold_quickly_and_ends(docked: bool) -> None:
    # A docked vessel's motor runs cool; the fault must still overheat it.
    vessel = make_vessel(battery_percent=90.0, dock_remaining_s=10_000 if docked else 0.0)
    run(vessel, 120)
    assert vessel.motor_temperature_c < 70
    assert (vessel.status is NavigationStatus.DOCKED) == docked

    vessel.start_scenario(Scenario.OVERHEAT)
    run(vessel, 20)
    assert vessel.motor_temperature_c > 70

    run(vessel, 80)
    assert vessel.scenario is None

    # Once cooling works again the motor is back under the alert threshold quickly.
    run(vessel, 30)
    assert vessel.motor_temperature_c < 66


def test_battery_drain_crosses_both_battery_thresholds_then_recovers() -> None:
    vessel = make_vessel(battery_percent=90.0, dock_remaining_s=0.0)

    vessel.start_scenario(Scenario.BATTERY_DRAIN)
    run(vessel, 60)
    assert vessel.battery_percent < 10

    run(vessel, 60)
    assert vessel.scenario is None
    assert vessel.battery_percent >= 80  # the demo battery is "swapped"


def test_go_offline_and_invalid_data_change_what_the_device_sends() -> None:
    vessel = make_vessel()

    vessel.start_scenario(Scenario.GO_OFFLINE)
    assert vessel.silent and not vessel.sends_invalid_data

    vessel.start_scenario(Scenario.INVALID_DATA)
    assert vessel.sends_invalid_data and not vessel.silent
    run(vessel, 21)
    assert not vessel.sends_invalid_data


def test_reset_ends_a_scenario_immediately() -> None:
    vessel = make_vessel()
    vessel.start_scenario(Scenario.GO_OFFLINE)

    vessel.start_scenario(Scenario.RESET)

    assert vessel.scenario is None


def test_invalid_payload_fails_validation() -> None:
    message = make_vessel().telemetry(NOW)

    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate_json(invalid_payload(message))


def test_parse_command() -> None:
    assert parse_command(b'{"scenario": "overheat"}') is Scenario.OVERHEAT
    assert parse_command(b'{"scenario": "explode"}') is None
    assert parse_command(b"not json") is None
