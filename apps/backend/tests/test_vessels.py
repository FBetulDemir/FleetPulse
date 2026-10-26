import uuid
from typing import Any

import pytest

from fleetpulse_backend.db.models import Vessel, VesselType
from fleetpulse_backend.db.seed import DEMO_VESSELS, seed

from .conftest import DbClient, Sessionmaker

URL = "/api/v1/vessels"


def add_vessels(db: DbClient, *vessels: dict[str, Any]) -> None:
    async def insert(sessionmaker: Sessionmaker) -> None:
        async with sessionmaker() as session, session.begin():
            session.add_all(
                Vessel(vessel_type=VesselType.FERRY, length_m=20.0, **vessel) for vessel in vessels
            )

    db.run(insert)


@pytest.fixture
def fleet(db_client: DbClient) -> DbClient:
    add_vessels(
        db_client,
        {"identifier": "vessel-001", "name": "Charlie"},
        {"identifier": "vessel-002", "name": "alpha"},
        {"identifier": "vessel-003", "name": "Bravo", "is_active": False},
        {"identifier": "vessel-004", "name": "100% Delta"},
    )
    return db_client


def names(response: Any) -> list[str]:
    return [vessel["name"] for vessel in response.json()["items"]]


def test_lists_vessels_sorted_by_name(fleet: DbClient) -> None:
    response = fleet.client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert names(response) == ["100% Delta", "alpha", "Bravo", "Charlie"]
    assert set(body["items"][0]) == {
        "id",
        "identifier",
        "name",
        "vessel_type",
        "length_m",
        "is_active",
        "created_at",
        "updated_at",
    }


def test_sorts_descending(fleet: DbClient) -> None:
    response = fleet.client.get(URL, params={"sort": "-identifier"})

    assert response.json()["items"][0]["identifier"] == "vessel-004"


def test_searches_name_and_identifier_case_insensitively(fleet: DbClient) -> None:
    assert names(fleet.client.get(URL, params={"q": "ALPHA"})) == ["alpha"]
    assert names(fleet.client.get(URL, params={"q": "vessel-003"})) == ["Bravo"]


def test_search_treats_wildcards_literally(fleet: DbClient) -> None:
    assert names(fleet.client.get(URL, params={"q": "%"})) == ["100% Delta"]


def test_filters_by_active_state(fleet: DbClient) -> None:
    assert names(fleet.client.get(URL, params={"is_active": "false"})) == ["Bravo"]


def test_paginates_with_total(fleet: DbClient) -> None:
    response = fleet.client.get(URL, params={"limit": 2, "offset": 1})

    body = response.json()
    assert names(response) == ["alpha", "Bravo"]
    assert (body["total"], body["limit"], body["offset"]) == (4, 2, 1)


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"sort": "length_m"}]
)
def test_rejects_invalid_query_with_problem_details(
    db_client: DbClient, params: dict[str, Any]
) -> None:
    response = db_client.client.get(URL, params=params)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["title"] == "Unprocessable Content"
    assert problem["instance"] == URL
    assert problem["errors"][0]["location"].startswith("query.")


def test_gets_one_vessel(fleet: DbClient) -> None:
    vessel_id = fleet.client.get(URL, params={"q": "alpha"}).json()["items"][0]["id"]

    response = fleet.client.get(f"{URL}/{vessel_id}")

    assert response.status_code == 200
    assert response.json()["identifier"] == "vessel-002"


def test_unknown_vessel_is_404_problem(db_client: DbClient) -> None:
    response = db_client.client.get(f"{URL}/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "Vessel not found"


def test_malformed_vessel_id_is_422(db_client: DbClient) -> None:
    assert db_client.client.get(f"{URL}/not-a-uuid").status_code == 422


def test_seed_is_idempotent(db_client: DbClient) -> None:
    db_client.run(seed)
    db_client.run(seed)

    response = db_client.client.get(URL)
    assert response.json()["total"] == len(DEMO_VESSELS)


def test_ready_checks_the_database(db_client: DbClient) -> None:
    assert db_client.client.get("/api/v1/health/ready").json() == {"status": "ok"}
