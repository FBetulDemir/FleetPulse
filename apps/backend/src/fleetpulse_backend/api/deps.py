"""Shared request dependencies: settings, the logged-in user, and role checks."""

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from fleetpulse_backend.auth.tokens import InvalidTokenError, decode_access_token
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.models import Role, User
from fleetpulse_backend.db.session import SessionDep

ACCESS_COOKIE = "fp_access"
REFRESH_COOKIE = "fp_refresh"


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


async def authenticate(token: str | None, session: AsyncSession, settings: Settings) -> User | None:
    """The active user an access token belongs to, or None. Also used by the WebSocket."""
    if not token:
        return None
    try:
        claims = decode_access_token(token, settings)
    except InvalidTokenError:
        return None
    # Loading the user (instead of trusting the token alone) means a deactivated user
    # loses access immediately, not when their token expires.
    user = await session.get(User, claims.user_id)
    return user if user is not None and user.is_active else None


async def current_user(request: Request, session: SessionDep, settings: SettingsDep) -> User:
    user = await authenticate(request.cookies.get(ACCESS_COOKIE), session, settings)
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(*roles: Role) -> Any:
    """Route dependency: 401 if not logged in, 403 if the user's role is not allowed."""

    async def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Your role does not allow this action")
        return user

    return Depends(check)
