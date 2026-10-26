"""Access tokens (short-lived JWTs) and refresh tokens (random, stored hashed)."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt

from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.models import Role

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    role: Role


def create_access_token(user_id: uuid.UUID, role: Role, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + settings.access_token_ttl,
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            # Pinning the algorithm blocks "alg: none" and algorithm-confusion attacks.
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
        if payload["type"] != ACCESS_TOKEN_TYPE:
            raise InvalidTokenError("not an access token")
        return AccessClaims(user_id=uuid.UUID(payload["sub"]), role=Role(payload["role"]))
    except (jwt.InvalidTokenError, KeyError, ValueError) as error:
        raise InvalidTokenError(str(error)) from error


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    # A fast hash is fine here: the token is 256 random bits, not a guessable password.
    return hashlib.sha256(token.encode()).hexdigest()
