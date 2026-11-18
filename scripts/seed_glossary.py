import asyncio

from app.db.repositories.chat_repository import ChatRepository
from app.db.session import SessionFactory

SEED_ENTRIES = [
    (
        "deductible",
        "Deductible",
        "The amount you pay out of pocket for a covered loss before insurance pays.",
    ),
    (
        "coverage_limit",
        "Coverage limit",
        "The maximum amount the policy may pay for a covered loss, subject to policy terms.",
    ),
    (
        "coverage_type",
        "Coverage type",
        "The category of loss or property protection selected for this policy.",
    ),
]


async def main() -> None:
    async with SessionFactory() as session:
        repository = ChatRepository(session)
        for field_key, label, definition in SEED_ENTRIES:
            await repository.upsert_glossary(field_key, label, definition)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
