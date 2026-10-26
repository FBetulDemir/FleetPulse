import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, or_, select

from fleetpulse_backend.api.problems import problem_responses
from fleetpulse_backend.db.models import Vessel, VesselType
from fleetpulse_backend.db.session import SessionDep

router = APIRouter(prefix="/api/v1/vessels", tags=["vessels"])


class VesselOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    identifier: str
    name: str
    vessel_type: VesselType
    length_m: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class VesselPage(BaseModel):
    items: list[VesselOut]
    total: int
    limit: int
    offset: int


SortKey = Literal["name", "-name", "identifier", "-identifier", "created_at", "-created_at"]

SORT_COLUMNS = {
    # Case-insensitive, so "alpha" sorts before "Bravo".
    "name": func.lower(Vessel.name),
    "identifier": Vessel.identifier,
    "created_at": Vessel.created_at,
}


def apply_sort(statement: Select[Vessel], sort: SortKey) -> Select[Vessel]:
    column = SORT_COLUMNS[sort.removeprefix("-")]
    order = column.desc() if sort.startswith("-") else column.asc()
    # Ties are broken by id so pages are stable while paging.
    return statement.order_by(order, Vessel.id)


@router.get("", responses=problem_responses(422))
async def list_vessels(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Search name or identifier")] = None,
    is_active: bool | None = None,
    sort: SortKey = "name",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VesselPage:
    statement = select(Vessel)
    if q:
        # autoescape: a search for "%" or "_" matches those characters literally.
        statement = statement.where(
            or_(
                Vessel.name.icontains(q, autoescape=True),
                Vessel.identifier.icontains(q, autoescape=True),
            )
        )
    if is_active is not None:
        statement = statement.where(Vessel.is_active == is_active)

    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    vessels = await session.scalars(apply_sort(statement, sort).limit(limit).offset(offset))
    return VesselPage(
        items=[VesselOut.model_validate(vessel) for vessel in vessels],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{vessel_id}", responses=problem_responses(404, 422))
async def get_vessel(vessel_id: uuid.UUID, session: SessionDep) -> VesselOut:
    vessel = await session.get(Vessel, vessel_id)
    if vessel is None:
        raise HTTPException(404, "Vessel not found")
    return VesselOut.model_validate(vessel)
