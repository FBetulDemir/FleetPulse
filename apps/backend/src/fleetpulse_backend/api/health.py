import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from fleetpulse_backend.api.problems import problem_responses
from fleetpulse_backend.db.session import SessionDep

logger = logging.getLogger("fleetpulse.api.health")

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """The process is running. Used to decide whether to restart the container."""
    return {"status": "ok"}


@router.get("/ready", responses=problem_responses(503))
async def ready(session: SessionDep) -> dict[str, str]:
    """The API can serve requests: its database is reachable."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as error:
        logger.warning("readiness check failed: %s", error)
        raise HTTPException(503, "Database unavailable") from error
    return {"status": "ok"}
