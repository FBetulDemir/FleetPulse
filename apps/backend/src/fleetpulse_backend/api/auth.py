"""Login, token refresh, logout and the current user.

Tokens live in httpOnly cookies, so page scripts (and therefore XSS) cannot read them.
SameSite=Strict keeps the browser from sending them on cross-site requests (CSRF).
The refresh cookie is only sent to /api/v1/auth, never to other endpoints.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleetpulse_backend.api.deps import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    CurrentUser,
    SettingsDep,
)
from fleetpulse_backend.api.problems import problem_response, problem_responses
from fleetpulse_backend.auth.passwords import verify_password
from fleetpulse_backend.auth.sessions import (
    InvalidSessionError,
    end_session,
    rotate_session,
    start_session,
)
from fleetpulse_backend.auth.tokens import create_access_token
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.models import Role, User
from fleetpulse_backend.db.seed import demo_email
from fleetpulse_backend.db.session import SessionDep

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
REFRESH_COOKIE_PATH = "/api/v1/auth"

Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254)]
# Argon2 hashing cost grows with input length; capping it prevents abuse.
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class LoginRequest(BaseModel):
    email: Email
    password: Password


class DemoLoginRequest(BaseModel):
    role: Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: Role


def _set_cookie(
    response: Response, name: str, value: str, max_age: int, path: str, settings: Settings
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def set_auth_cookies(response: Response, access: str, refresh: str, settings: Settings) -> None:
    access_age = int(settings.access_token_ttl.total_seconds())
    refresh_age = int(settings.refresh_token_ttl.total_seconds())
    _set_cookie(response, ACCESS_COOKIE, access, access_age, "/", settings)
    _set_cookie(response, REFRESH_COOKIE, refresh, refresh_age, REFRESH_COOKIE_PATH, settings)


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name, path in ((ACCESS_COOKIE, "/"), (REFRESH_COOKIE, REFRESH_COOKIE_PATH)):
        response.delete_cookie(
            name, path=path, httponly=True, secure=settings.cookie_secure, samesite="strict"
        )


async def log_in(
    response: Response, session: AsyncSession, user: User, settings: Settings
) -> UserOut:
    refresh = await start_session(session, user, settings)
    set_auth_cookies(response, create_access_token(user.id, user.role, settings), refresh, settings)
    return UserOut.model_validate(user)


@router.post("/login", responses=problem_responses(401, 422))
async def login(
    body: LoginRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> UserOut:
    user = await session.scalar(select(User).where(User.email == body.email))
    password_ok = verify_password(body.password, user.password_hash if user else None)
    if user is None or not password_ok or not user.is_active:
        # One message for every failure, so the response does not reveal which emails exist.
        raise HTTPException(401, "Invalid email or password")
    return await log_in(response, session, user, settings)


@router.post("/demo-login", responses=problem_responses(404, 422))
async def demo_login(
    body: DemoLoginRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> UserOut:
    """Logs in as the demo user of a role. Only available when demo mode is on."""
    if not settings.demo_mode:
        raise HTTPException(404, "Demo login is not enabled")
    user = await session.scalar(select(User).where(User.email == demo_email(body.role)))
    if user is None or not user.is_active:
        raise HTTPException(404, "Demo user not found")
    return await log_in(response, session, user, settings)


@router.post("/refresh", response_model=UserOut, responses=problem_responses(401))
async def refresh(
    request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> UserOut | Response:
    token = request.cookies.get(REFRESH_COOKIE)
    try:
        if not token:
            raise InvalidSessionError("no refresh token")
        user, new_refresh = await rotate_session(session, token, settings)
    except InvalidSessionError:
        failed = problem_response(request, 401, "Session expired, please log in again")
        clear_auth_cookies(failed, settings)
        return failed
    access = create_access_token(user.id, user.role, settings)
    set_auth_cookies(response, access, new_refresh, settings)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, session: SessionDep, settings: SettingsDep) -> Response:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        await end_session(session, token)
    response = Response(status_code=204)
    clear_auth_cookies(response, settings)
    return response


@router.get("/me", responses=problem_responses(401))
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
