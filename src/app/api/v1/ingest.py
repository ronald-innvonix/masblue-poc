from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Path, Query, UploadFile

from app.api.deps import SessionDep, get_ingestion_service
from app.core.config import Settings, get_settings
from app.core.errors import InvalidDocumentError, NotFoundError, ProviderError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import require_internal_key
from app.db.repositories.chat_repository import ChatRepository
from app.db.session import SessionFactory
from app.llm.base import EmbeddingProvider
from app.schemas.ingest import IngestResponse, IngestStatusResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(
    prefix="/v1/policies",
    tags=["ingestion"],
    dependencies=[Depends(require_internal_key), Depends(enforce_rate_limit)],
)
logger = structlog.get_logger(__name__)


async def _run_ingestion(
    document_id: UUID,
    user_id: str,
    data: bytes,
    embeddings: EmbeddingProvider,
) -> None:
    async with SessionFactory() as session:
        service = IngestionService(session, embeddings)
        try:
            await service.process_queued(document_id, user_id, data)
        except (InvalidDocumentError, ProviderError) as exc:
            logger.warning("ingestion_failed", document_id=str(document_id), error_code=exc.code)


@router.post("/{policy_id}/documents", response_model=IngestResponse, status_code=201)
async def ingest_document(
    policy_id: Annotated[str, Path(min_length=1, max_length=128)],
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Form(min_length=1, max_length=128)],
    file: Annotated[UploadFile, File()],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IngestResponse:
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise InvalidDocumentError("Uploaded PDF exceeds the configured size limit")
    document_id = await service.enqueue(user_id, policy_id, file.filename or "", data)
    background_tasks.add_task(_run_ingestion, document_id, user_id, data, service.embeddings)
    return IngestResponse(
        document_id=str(document_id), policy_id=policy_id, chunks_created=0, status="queued"
    )


@router.get(
    "/{policy_id}/documents/{document_id}",
    response_model=IngestStatusResponse,
)
async def ingestion_status(
    policy_id: Annotated[str, Path(min_length=1, max_length=128)],
    document_id: UUID,
    user_id: Annotated[str, Query(min_length=1, max_length=128)],
    session: SessionDep,
) -> IngestStatusResponse:
    document = await ChatRepository(session).document_status(str(document_id), user_id)
    if document is None or document.policy_id != policy_id:
        raise NotFoundError("Policy document not found")
    return IngestStatusResponse(
        document_id=str(document.id),
        policy_id=document.policy_id,
        status=document.status,
        error=document.error_message,
    )
