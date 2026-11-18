import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.models import Base, PolicyChunk, PolicyDocument
from app.db.repositories.chat_repository import ChatRepository

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to run pgvector tests")
async def test_retrieval_cannot_return_another_users_chunks() -> None:
    assert TEST_DATABASE_URL is not None
    schema = f"test_tenant_{uuid.uuid4().hex}"
    engine = create_async_engine(TEST_DATABASE_URL)
    vector = [1.0, *([0.0] * 383)]
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            scoped = await connection.execution_options(schema_translate_map={None: schema})
            await scoped.run_sync(Base.metadata.create_all)

        async with engine.connect() as connection:
            scoped = await connection.execution_options(schema_translate_map={None: schema})
            async with AsyncSession(scoped, expire_on_commit=False) as session:
                owner_document = PolicyDocument(
                    user_id="user-a",
                    policy_id="policy-shared-id",
                    filename="policy.pdf",
                    content_sha256="a" * 64,
                    status="ready",
                )
                session.add(owner_document)
                await session.flush()
                session.add_all(
                    [
                        PolicyChunk(
                            document_id=owner_document.id,
                            user_id="user-a",
                            policy_id="policy-shared-id",
                            chunk_index=0,
                            content="Private policy content",
                            section="Coverage",
                            page_number=1,
                            embedding=vector,
                        ),
                        PolicyChunk(
                            document_id=owner_document.id,
                            user_id="user-b",
                            policy_id="policy-shared-id",
                            chunk_index=1,
                            content="Mismatched tenant metadata",
                            section="Coverage",
                            page_number=2,
                            embedding=vector,
                        ),
                    ]
                )
                await session.commit()

                repository = ChatRepository(session)
                other_user_rows = await repository.retrieve_chunks("user-b", None, vector, 10)
                owner_rows = await repository.retrieve_chunks("user-a", None, vector, 10)

                assert other_user_rows == []
                assert [chunk.content for chunk, _ in owner_rows] == ["Private policy content"]
    finally:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await engine.dispose()
