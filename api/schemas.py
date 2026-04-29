from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ConversationTurn(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message (max 2000 chars)")
    user_id: str = Field(default="anonymous")
    session_id: Optional[str] = Field(default=None)
    conversation_history: List[ConversationTurn] = Field(default_factory=list)
    system_prompt: Optional[str] = Field(default=None, description="Override system prompt (admin only)")
    skip_persist: bool = Field(default=False)
    category: Optional[str] = Field(default=None, description="Document category to use for RAG context")

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        if len(v) > 2000:
            raise ValueError("Message must be 2000 characters or less")
        return v


class ChatResponse(BaseModel):
    response: str
    interaction_id: Optional[str] = None
    model: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    interaction_id: str
    value: str = Field(..., description="'like' or 'dislike'")
    reason: Optional[str] = None
    comment: Optional[str] = None

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: str) -> str:
        if v not in ("like", "dislike"):
            raise ValueError("value must be 'like' or 'dislike'")
        return v


class AuthLoginRequest(BaseModel):
    password: str


class AuthSessionResponse(BaseModel):
    authenticated: bool
    role: Optional[str] = None
    expires_at: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    model_available: bool
    model_name: str
    vllm_url: str


class ModelInfo(BaseModel):
    current_model: str
    available_models: List[str]
    vllm_url: str


class CategoryInfo(BaseModel):
    name: str
    doc_count: int
    doc_names: List[str]


class CategoriesResponse(BaseModel):
    categories: List[CategoryInfo]
