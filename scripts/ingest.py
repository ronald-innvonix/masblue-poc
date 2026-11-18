import argparse
import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionFactory
from app.embeddings.factory import get_embeddings
from app.services.ingestion_service import IngestionService


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a policy PDF")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--policy-id", required=True)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    data = args.pdf.read_bytes()
    settings = get_settings()
    if len(data) > settings.max_upload_bytes:
        parser.error("PDF exceeds MAX_UPLOAD_BYTES")
    async with SessionFactory() as session:
        document_id, count = await IngestionService(session, get_embeddings(settings)).ingest(
            args.user_id, args.policy_id, args.pdf.name, data
        )
    print(f"Ingested {count} chunks as document {document_id}")


if __name__ == "__main__":
    asyncio.run(main())
