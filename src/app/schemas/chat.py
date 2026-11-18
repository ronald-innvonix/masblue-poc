from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FormContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form: str = Field(min_length=1, max_length=128)
    field: str = Field(min_length=1, max_length=128)


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=8_000)
    policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    policy_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        default_factory=list, max_length=50
    )
    form_context: FormContext | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=20)
    conversation_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def enforce_combined_input_limit(self) -> "ChatRequest":
        total_chars = len(self.message) + sum(len(item.content) for item in self.history)
        if total_chars > 8_000:
            raise ValueError("Message and conversation history exceed the 8000-character limit")
        return self


class ChatSource(BaseModel):
    source_type: Literal["policy_document", "policy_fact"] = "policy_document"
    policy_id: str
    document_id: str | None = None
    chunk_index: int | None = None
    excerpt: str
    section: str | None = None
    page: int | None = None


class ChatResponse(BaseModel):
    intent: Literal["field_help", "policy_qa", "handoff"]
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)
    conversation_id: str | None = None
    model: str


class ErrorResponse(BaseModel):
    error: dict[str, str]
