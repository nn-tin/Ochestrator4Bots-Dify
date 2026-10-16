import asyncio

from src.orchestrator.models import (
    BotMessage,
    BotSession,
    ChatMessage,
    ConversationState,
    OrchestrationLogEntry,
    OrchestrationTrace,
)


class InMemoryConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, ConversationState] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, conversation_id: str) -> asyncio.Lock:
        return self._locks.setdefault(conversation_id, asyncio.Lock())

    def _state(self, conversation_id: str) -> ConversationState:
        return self._conversations.setdefault(
            conversation_id,
            ConversationState(conversation_id=conversation_id),
        )

    def add_user_message(self, conversation_id: str, content: str) -> None:
        self._state(conversation_id).user_messages.append(
            ChatMessage(role="user", content=content)
        )

    def add_assistant_message(self, conversation_id: str, content: str) -> None:
        self._state(conversation_id).user_messages.append(
            ChatMessage(role="assistant", content=content)
        )

    def get_user_context(self, conversation_id: str) -> list[ChatMessage]:
        return list(self._state(conversation_id).user_messages)

    def get_bot_session(self, conversation_id: str, bot_id: str) -> BotSession:
        state = self._state(conversation_id)
        return state.bot_sessions.setdefault(bot_id, BotSession())

    def add_bot_exchange(
        self,
        conversation_id: str,
        bot_id: str,
        request: str,
        response: str,
        remote_session_id: str | None,
    ) -> None:
        session = self.get_bot_session(conversation_id, bot_id)
        session.messages.extend(
            [
                BotMessage(role="orchestrator", content=request),
                BotMessage(role="bot", content=response),
            ]
        )
        if remote_session_id is not None:
            session.remote_session_id = remote_session_id

    def add_orchestration_log(
        self,
        conversation_id: str,
        user_message: str,
        trace: OrchestrationTrace,
    ) -> None:
        state = self._state(conversation_id)
        state.orchestration_logs.append(
            OrchestrationLogEntry(
                turn_number=len(state.orchestration_logs) + 1,
                user_message=user_message,
                trace=trace.model_copy(deep=True),
            )
        )

    def get_state(self, conversation_id: str) -> ConversationState:
        return self._state(conversation_id).model_copy(deep=True)
