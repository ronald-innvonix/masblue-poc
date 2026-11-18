from collections.abc import Sequence

from app.db.models import PolicyFact
from app.db.repositories.chat_repository import ChatRepository


class FactsService:
    def __init__(self, repository: ChatRepository) -> None:
        self.repository = repository

    async def for_policies(
        self, user_id: str, policy_ids: Sequence[str] | None = None
    ) -> list[PolicyFact]:
        return await self.repository.policy_facts(user_id, policy_ids)
