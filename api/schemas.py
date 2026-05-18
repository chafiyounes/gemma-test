from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


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
    category: Optional[str] = Field(
        default=None,
        description=(
            "RAG scope: omit or 'all' / 'tout' → every indexed category; "
            "'procedures' or 'help_md' (aliases: aide, help) → that corpus only."
        ),
    ),
    agentic_rag: Optional[bool] = Field(
        default=None,
        description="Agentic RAG (map + tools). Omit or null to follow AGENTIC_RAG_DEFAULT_ON_CHAT when AGENTIC_RAG_ENABLED.",
    )

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
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthSessionResponse(BaseModel):
    authenticated: bool
    role: Optional[str] = None
    username: Optional[str] = None
    user_id: Optional[int] = Field(default=None, description="Numeric account id (SQLite users.id)")
    expires_at: Optional[int] = None


class AdminCreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2)
    password: str = Field(..., min_length=4)
    role: str = Field(default="user", description="'user', 'manager', or 'administrator'")

    @field_validator("role")
    @classmethod
    def role_ok(cls, v: str) -> str:
        key = (v or "").strip().lower()
        if key == "admin":
            key = "administrator"
        if key not in ("user", "manager", "administrator"):
            raise ValueError("role must be 'user', 'manager', or 'administrator'")
        return key


class AdminUserInfo(BaseModel):
    id: int
    username: str
    role: str
    created_at: str


class AdminUserListResponse(BaseModel):
    users: List[AdminUserInfo]


class AdminUpdateUserRequest(BaseModel):
    password: Optional[str] = Field(default=None, min_length=4)
    role: Optional[str] = Field(default=None, description="'user', 'manager', or 'administrator'")

    @field_validator("role")
    @classmethod
    def role_ok(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        key = v.strip().lower()
        if key == "admin":
            key = "administrator"
        if key not in ("user", "manager", "administrator"):
            raise ValueError("role must be 'user', 'manager', or 'administrator'")
        return key

    @model_validator(mode="after")
    def at_least_one(self) -> "AdminUpdateUserRequest":
        if self.password is None and self.role is None:
            raise ValueError("Provide password and/or role to update")
        return self


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
