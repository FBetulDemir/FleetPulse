import uuid
from collections.abc import Iterator

import pytest

from fleetpulse_backend.api.rate_limit import RateLimiter
from fleetpulse_backend.db.models import Role, Vessel, VesselType
from fleetpulse_contracts.commands import Scenario

from .conftest import DbClient, RecordingPublisher, Sessionmaker, make_db_client

URL = "/api/v1/demo/scenarios"


class Demo:
    def __init__(self, db: DbClient, publisher: RecordingPublisher) -> None:
        self.db = db
        self.client = db.client
        self.publisher = publisher
        self.vessel_id = uuid.uuid4()
        db.run(self._add_vessel)

    async def _add_vessel(self, sessionmaker: Sessionmaker) -> None:
        async with sessionmaker() as session, session.begin():
            session.add(
                Vessel(
                    id=self.vessel_id,
                    identifier="vessel-003",
                    name="Vinga Pilot",
                    vessel_type=VesselType.PILOT,
                    length_m=16.8,
                )
            )

    def trigger(self, scenario: str = "overheat", vessel_id: uuid.UUID | None = None) -> int:
        body = {"vessel_id": str(vessel_id or self.vessel_id), "scenario": scenario}
        return self.client.post(URL, json=body).status_code


@pytest.fixture
def demo(database_url: str) -> Iterator[Demo]:
    publisher = RecordingPublisher()
    with make_db_client(database_url, publisher, demo_mode=True) as db:
        yield Demo(db, publisher)


def test_operator_sends_a_scenario_to_the_vessels_device(demo: Demo) -> None:
    demo.db.login_as(Role.OPERATOR)

    assert demo.trigger("battery_drain") == 202

    [(device, command)] = demo.publisher.commands
    assert device == "vessel-003"  # addressed by MQTT identifier, not database id
    assert command.scenario is Scenario.BATTERY_DRAIN


def test_viewers_cannot_trigger_scenarios(demo: Demo) -> None:
    demo.db.login_as(Role.VIEWER)

    assert demo.trigger() == 403
    assert demo.publisher.commands == []


def test_unknown_scenario_or_vessel_is_rejected(demo: Demo) -> None:
    demo.db.login_as(Role.ADMIN)

    assert demo.trigger("explode") == 422
    assert demo.trigger(vessel_id=uuid.uuid4()) == 404


def test_unreachable_broker_is_503(demo: Demo) -> None:
    demo.db.login_as(Role.OPERATOR)
    demo.publisher.unavailable = True

    assert demo.trigger() == 503


def test_scenarios_are_rate_limited_per_user(demo: Demo) -> None:
    demo.db.login_as(Role.OPERATOR)

    statuses = [demo.trigger() for _ in range(11)]

    assert statuses[:10] == [202] * 10
    assert statuses[10] == 429


def test_demo_controls_are_off_outside_demo_mode(database_url: str) -> None:
    with make_db_client(database_url) as db:
        db.login_as(Role.ADMIN)

        body = {"vessel_id": str(uuid.uuid4()), "scenario": "overheat"}
        assert db.client.post(URL, json=body).status_code == 404


def test_rate_limiter_uses_a_sliding_window() -> None:
    now = [0.0]
    limiter = RateLimiter(limit=2, window_s=10, clock=lambda: now[0])

    assert [limiter.allow("a"), limiter.allow("a"), limiter.allow("a")] == [True, True, False]
    assert limiter.allow("b")  # separate per key

    now[0] = 10.0
    assert limiter.allow("a")
