"""Validate bearer JWTs issued by the existing application."""

from typing import Any

import jwt

from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError, UnauthorizedError
from app.schemas.common import CurrentUser


def decode_access_token(token: str, settings: Settings) -> CurrentUser:
    """Validate a Node-issued token and expose its subject and claims."""
    algorithm = settings.jwt_algorithm
    # Select key type from the configured algorithm to avoid accepting token-chosen algorithms.
    key = settings.jwt_secret if algorithm.startswith("HS") else settings.jwt_public_key
    if not key:
        raise ServiceConfigurationError
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            options={"require": ["sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError from exc
    subject = claims.get("sub")
    if not isinstance(subject, str | int) or not str(subject):
        raise UnauthorizedError
    return CurrentUser(user_id=str(subject), claims=claims)
