from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class BotMessage(BaseModel):
    role: Literal["orchestrator", "bot"]
    content: str


class BotSession(BaseModel):
    messages: list[BotMessage] = Field(default_factory=list)
    remote_session_id: str | None = None


class ConversationState(BaseModel):
    conversation_id: str
    user_messages: list[ChatMessage] = Field(default_factory=list)
    bot_sessions: dict[str, BotSession] = Field(default_factory=dict)
    orchestration_logs: list["OrchestrationLogEntry"] = Field(default_factory=list)


class RouterDecision(BaseModel):
    action: Literal["reply", "delegate"]
    target_bot: Literal["late", "leave", "it_support", "meeting"] | None = None
    response: str | None = None
    user_intent: str

    @model_validator(mode="after")
    def validate_action_fields(self) -> "RouterDecision":
        if self.action == "reply" and not self.response:
            raise ValueError("response is required when action is reply")
        if self.action == "delegate" and not self.target_bot:
            raise ValueError("target_bot is required when action is delegate")
        return self


class ComposedRequest(BaseModel):
    request: str


class BotResponse(BaseModel):
    text: str
    session_id: str | None = None


class StageTrace(BaseModel):
    prompt: str
    response: dict[str, Any]


class StepTrace(BaseModel):
    sequence: int = Field(ge=1)
    step_name: str = Field(min_length=1)
    call_number: int = Field(ge=1)
    reason: str = Field(min_length=1)
    status: Literal["success", "error", "timeout", "skipped"]
    duration_ms: float = Field(ge=0)
    request: Any = None
    response: Any = None
    error: dict[str, Any] | None = None


class OrchestrationTrace(BaseModel):
    turn_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    workflow_name: str = "llm_router_then_composer"
    workflow_version: str = "1"
    steps: list[StepTrace] = Field(default_factory=list)
    router: StageTrace
    composer: StageTrace | None = None


class OrchestrationLogEntry(BaseModel):
    turn_number: int = Field(ge=1)
    user_message: str = Field(min_length=1)
    trace: OrchestrationTrace


class OrchestratorResult(BaseModel):
    response: str
    trace: OrchestrationTrace


class ChatRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    emp_id: str | None = None
    emp_name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    debug: bool = False


class ChatResponse(BaseModel):
    response: str
    trace: OrchestrationTrace | None = None

