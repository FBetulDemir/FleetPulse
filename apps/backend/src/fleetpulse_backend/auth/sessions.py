"""Login sessions backed by rotating refresh tokens."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fleetpulse_backend.auth.tokens import hash_refresh_token, new_refresh_token
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.models import RefreshToken, User


class InvalidSessionError(Exception):
    pass


async def start_session(session: AsyncSession, user: User, settings: Settings) -> str:
    """Creates a new session (token family) and returns its first refresh token."""
    return await _issue(session, user.id, uuid.uuid4(), settings)


async def rotate_session(session: AsyncSession, token: str, settings: Settings) -> tuple[User, str]:
    """Exchanges a refresh token for a new one. Each token can be used only once."""
    now = datetime.now(UTC)
    stored = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(token))
        # Locks the row so two concurrent refreshes cannot both succeed.
        .with_for_update()
    )
    if stored is None:
        raise InvalidSessionError("unknown refresh token")
    if stored.revoked_at is not None:
        # Already used or logged out: someone is replaying it. End the whole session.
        await _revoke_family(session, stored.family_id, now)
        await session.commit()
        raise InvalidSessionError("refresh token reused")
    if stored.expires_at <= now:
        raise InvalidSessionError("refresh token expired")

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise InvalidSessionError("user unavailable")

    stored.revoked_at = now
    new_token = await _issue(session, user.id, stored.family_id, settings)
    return user, new_token


async def end_session(session: AsyncSession, token: str) -> None:
    """Logs out: revokes every token of the session the token belongs to."""
    family_id = await session.scalar(
        select(RefreshToken.family_id).where(RefreshToken.token_hash == hash_refresh_token(token))
    )
    if family_id is not None:
        await _revoke_family(session, family_id, datetime.now(UTC))
        await session.commit()


async def _issue(
    session: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID, settings: Settings
) -> str:
    token = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_refresh_token(token),
            expires_at=datetime.now(UTC) + settings.refresh_token_ttl,
        )
    )
    await session.commit()
    return token


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
