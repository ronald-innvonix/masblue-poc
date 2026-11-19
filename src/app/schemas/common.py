"""Shared API data structures."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class CurrentUser(BaseModel):
    """Authenticated identity and validated claims from the upstream JWT."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    claims: dict[str, Any]
