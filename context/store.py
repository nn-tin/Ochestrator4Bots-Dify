from collections.abc import Awaitable
from contextlib import AbstractAsyncContextManager
from typing import Protocol, TypeVar

from src.orchestrator.models import (
    BotSession,
    ChatMessage,
    ConversationState,
    OrchestrationTrace,
)


T = TypeVar("T")
MaybeAwaitable = T | Awaitable[T]


class ConversationStore(Protocol):
    """Storage contract used by the orchestrator.

    Returning either a value or an awaitable keeps the lightweight in-memory
    implementation useful in tests while allowing database-backed stores to do
    non-blocking I/O.
    """

    def lock_for(self, conversation_id: str) -> AbstractAsyncContextManager[None]: ...

    def add_user_message(
        self, conversation_id: str, content: str
    ) -> MaybeAwaitable[None]: ...

    def add_assistant_message(
        self, conversation_id: str, content: str
    ) -> MaybeAwaitable[None]: ...

    def get_user_context(
        self, conversation_id: str
    ) -> MaybeAwaitable[list[ChatMessage]]: ...

    def get_bot_session(
        self, conversation_id: str, bot_id: str
    ) -> MaybeAwaitable[BotSession]: ...

    def add_bot_exchange(
        self,
        conversation_id: str,
        bot_id: str,
        request: str,
        response: str,
        remote_session_id: str | None,
    ) -> MaybeAwaitable[None]: ...

    def add_orchestration_log(
        self,
        conversation_id: str,
        user_message: str,
        trace: OrchestrationTrace,
    ) -> MaybeAwaitable[None]: ...

    def get_state(
        self, conversation_id: str
    ) -> MaybeAwaitable[ConversationState]: ...
