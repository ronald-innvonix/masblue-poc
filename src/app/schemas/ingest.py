from pydantic import BaseModel


class IngestResponse(BaseModel):
    document_id: str
    policy_id: str
    chunks_created: int
    status: str


class IngestStatusResponse(BaseModel):
    document_id: str
    policy_id: str
    status: str
    error: str | None = None
