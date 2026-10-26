import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr, ValidationError

from fleetpulse_backend.api.deps import ACCESS_COOKIE, REFRESH_COOKIE
from fleetpulse_backend.auth.tokens import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
)
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.models import Role
from fleetpulse_backend.db.seed import demo_email, seed

from .conftest import PASSWORD, DbClient, make_db_client

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


def set_cookie_headers(response: object) -> list[str]:
    return response.headers.get_list("set-cookie")  # type: ignore[attr-defined, no-any-return]


# Login


def test_login_sets_secure_cookies_and_returns_the_user(db_client: DbClient) -> None:
    email = db_client.add_user(Role.OPERATOR)

    response = db_client.client.post(LOGIN, json={"email": email, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["role"] == "operator"
    assert "password_hash" not in response.json()
    cookies = set_cookie_headers(response)
    access = next(c for c in cookies if c.startswith(f"{ACCESS_COOKIE}="))
    refresh = next(c for c in cookies if c.startswith(f"{REFRESH_COOKIE}="))
    for cookie in (access, refresh):
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
    assert "Path=/;" in access
    # The refresh token is only ever sent to the auth endpoints.
    assert "Path=/api/v1/auth" in refresh


def test_login_ignores_email_case_and_whitespace(db_client: DbClient) -> None:
    db_client.add_user(Role.VIEWER, email="viewer@example.com")

    response = db_client.client.post(
        LOGIN, json={"email": "  Viewer@Example.COM ", "password": PASSWORD}
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [("admin@example.com", "wrong password"), ("nobody@example.com", PASSWORD)],
)
def test_failed_login_does_not_reveal_whether_the_email_exists(
    db_client: DbClient, email: str, password: str
) -> None:
    db_client.add_user(Role.ADMIN)

    response = db_client.client.post(LOGIN, json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert not set_cookie_headers(response)


def test_deactivated_user_cannot_log_in(db_client: DbClient) -> None:
    email = db_client.add_user(Role.ADMIN, is_active=False)

    response = db_client.client.post(LOGIN, json={"email": email, "password": PASSWORD})

    assert response.status_code == 401


# Current user


def test_me_requires_login(db_client: DbClient) -> None:
    response = db_client.client.get(ME)

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


def test_me_returns_the_logged_in_user(db_client: DbClient) -> None:
    db_client.login_as(Role.ADMIN)

    assert db_client.client.get(ME).json()["email"] == "admin@example.com"


@pytest.mark.parametrize("token", ["not-a-jwt", "forged"])
def test_me_rejects_invalid_access_tokens(db_client: DbClient, token: str) -> None:
    if token == "forged":
        claims = {"sub": str(uuid.uuid4()), "role": "admin", "type": "access", "iat": 0}
        claims["exp"] = datetime.now(UTC) + timedelta(hours=1)
        token = jwt.encode(claims, "an attacker's own 32+ byte signing key", algorithm="HS256")
    db_client.client.cookies.set(ACCESS_COOKIE, token)

    assert db_client.client.get(ME).status_code == 401


# Refresh and logout


def test_refresh_rotates_the_refresh_token(db_client: DbClient) -> None:
    db_client.login_as(Role.VIEWER)
    first = db_client.client.cookies.get(REFRESH_COOKIE, path="/api/v1/auth")

    response = db_client.client.post(REFRESH)

    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
    second = db_client.client.cookies.get(REFRESH_COOKIE, path="/api/v1/auth")
    assert second and second != first


def use_refresh_token(db: DbClient, token: str | None) -> None:
    assert token is not None
    db.client.cookies.delete(REFRESH_COOKIE)  # replace, rather than add a second cookie
    db.client.cookies.set(REFRESH_COOKIE, token, path="/api/v1/auth")


def test_reusing_a_refresh_token_ends_the_whole_session(db_client: DbClient) -> None:
    db_client.login_as(Role.VIEWER)
    stolen = db_client.client.cookies.get(REFRESH_COOKIE, path="/api/v1/auth")
    assert db_client.client.post(REFRESH).status_code == 200  # the real user refreshes
    current = db_client.client.cookies.get(REFRESH_COOKIE, path="/api/v1/auth")

    # An attacker replays the old token: rejected, and the session is revoked...
    use_refresh_token(db_client, stolen)
    assert db_client.client.post(REFRESH).status_code == 401

    # ...so the real user's current token stops working too.
    use_refresh_token(db_client, current)
    assert db_client.client.post(REFRESH).status_code == 401


def test_logout_revokes_the_session_and_clears_cookies(db_client: DbClient) -> None:
    db_client.login_as(Role.OPERATOR)
    token = db_client.client.cookies.get(REFRESH_COOKIE, path="/api/v1/auth")

    response = db_client.client.post(LOGOUT)

    assert response.status_code == 204
    assert all('="";' in c or "Max-Age=0" in c for c in set_cookie_headers(response))
    use_refresh_token(db_client, token)
    assert db_client.client.post(REFRESH).status_code == 401


def test_refresh_without_a_session_is_401(db_client: DbClient) -> None:
    assert db_client.client.post(REFRESH).status_code == 401


# Demo login


def test_demo_login_is_disabled_by_default(db_client: DbClient) -> None:
    response = db_client.client.post("/api/v1/auth/demo-login", json={"role": "admin"})

    assert response.status_code == 404


def test_demo_login_logs_in_as_the_demo_user_of_a_role(database_url: str) -> None:
    with make_db_client(database_url, demo_mode=True) as db:
        db.run(lambda sessionmaker: seed(sessionmaker, "demo password"))

        response = db.client.post("/api/v1/auth/demo-login", json={"role": "operator"})

        assert response.status_code == 200
        assert db.client.get(ME).json()["email"] == demo_email(Role.OPERATOR)


# Tokens and configuration


def test_expired_access_token_is_rejected() -> None:
    settings = Settings(access_token_ttl=timedelta(seconds=-1))
    token = create_access_token(uuid.uuid4(), Role.ADMIN, settings)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings)


def test_production_requires_a_real_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret=SecretStr("too-short"))

    settings = Settings(environment="production", jwt_secret=SecretStr("x" * 32))
    assert settings.cookie_secure
