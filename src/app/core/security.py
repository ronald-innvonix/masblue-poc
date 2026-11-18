import hmac
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import UnauthorizedError


async def require_internal_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.internal_api_key.get_secret_value()
    if x_internal_key is None or not hmac.compare_digest(x_internal_key, expected):
        raise UnauthorizedError("Invalid internal API key")
