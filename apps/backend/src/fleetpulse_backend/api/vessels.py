import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError

from fleetpulse_backend.api.deps import require_role
from fleetpulse_backend.api.problems import problem_responses
from fleetpulse_backend.db.models import Role, Vessel, VesselType
from fleetpulse_backend.db.session import SessionDep
from fleetpulse_contracts.telemetry import Identifier

router = APIRouter(prefix="/api/v1/vessels", tags=["vessels"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Length = Annotated[float, Field(gt=0, lt=10_000)]


class VesselCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: Identifier
    name: Name
    vessel_type: VesselType
    length_m: Length


class VesselUpdate(BaseModel):
    """Partial update: only the fields sent are changed. The identifier cannot change,
    because it links the vessel to its device and stored telemetry."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    vessel_type: VesselType | None = None
    length_m: Length | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


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


@router.post(
    "",
    status_code=201,
    dependencies=[require_role(Role.ADMIN)],
    responses=problem_responses(401, 403, 409, 422),
)
async def create_vessel(body: VesselCreate, response: Response, session: SessionDep) -> VesselOut:
    vessel = Vessel(**body.model_dump())
    session.add(vessel)
    try:
        await session.commit()
    except IntegrityError as error:
        # The unique constraint is the source of truth; checking first would race.
        raise HTTPException(409, "A vessel with this identifier already exists") from error
    await session.refresh(vessel)
    response.headers["Location"] = f"{router.prefix}/{vessel.id}"
    return VesselOut.model_validate(vessel)


@router.patch(
    "/{vessel_id}",
    dependencies=[require_role(Role.ADMIN)],
    responses=problem_responses(401, 403, 404, 422),
)
async def update_vessel(vessel_id: uuid.UUID, body: VesselUpdate, session: SessionDep) -> VesselOut:
    """Deactivate a vessel with `{"is_active": false}`; vessels are never deleted,
    so their history stays intact."""
    vessel = await session.get(Vessel, vessel_id)
    if vessel is None:
        raise HTTPException(404, "Vessel not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(vessel, field, value)
    await session.commit()
    await session.refresh(vessel)
    return VesselOut.model_validate(vessel)
