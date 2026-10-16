import asyncio
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, AsyncMongoClient

from src.orchestrator.models import (
    BotMessage,
    BotSession,
    ChatMessage,
    ConversationState,
    OrchestrationLogEntry,
    OrchestrationTrace,
)


class MongoConversationStore:
    """Persist the complete state of each conversation in one Mongo document."""

    def __init__(
        self,
        uri: str,
        database: str,
        collection: str,
        *,
        server_selection_timeout_ms: int = 5000,
    ) -> None:
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
            uri,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
            tz_aware=True,
        )
        self._collection = self._client[database][collection]
        self._locks: dict[str, asyncio.Lock] = {}

    async def initialize(self) -> None:
        await self._client.admin.command("ping")
        await self._collection.create_index(
            [("updated_at", ASCENDING)], name="updated_at_idx"
        )

    async def close(self) -> None:
        await self._client.close()

    def lock_for(self, conversation_id: str) -> asyncio.Lock:
        # The Docker image intentionally runs one Uvicorn worker. This lock
        # serializes turns for a conversation within that process.
        return self._locks.setdefault(conversation_id, asyncio.Lock())

    async def add_user_message(self, conversation_id: str, content: str) -> None:
        await self._append_chat_message(conversation_id, "user", content)

    async def add_assistant_message(
        self, conversation_id: str, content: str
    ) -> None:
        await self._append_chat_message(conversation_id, "assistant", content)

    async def _append_chat_message(
        self, conversation_id: str, role: str, content: str
    ) -> None:
        now = datetime.now(timezone.utc)
        await self._collection.update_one(
            {"_id": conversation_id},
            {
                "$setOnInsert": {
                    "conversation_id": conversation_id,
                    "bot_sessions": {},
                    "orchestration_logs": [],
                    "created_at": now,
                },
                "$set": {"updated_at": now},
                "$push": {"user_messages": {"role": role, "content": content}},
            },
            upsert=True,
        )

    async def get_user_context(self, conversation_id: str) -> list[ChatMessage]:
        document = await self._collection.find_one(
            {"_id": conversation_id}, {"user_messages": 1}
        )
        messages = document.get("user_messages", []) if document else []
        return [ChatMessage.model_validate(message) for message in messages]

    async def get_bot_session(
        self, conversation_id: str, bot_id: str
    ) -> BotSession:
        document = await self._collection.find_one(
            {"_id": conversation_id}, {f"bot_sessions.{bot_id}": 1}
        )
        if not document:
            return BotSession()
        session = document.get("bot_sessions", {}).get(bot_id)
        return BotSession.model_validate(session) if session else BotSession()

    async def add_bot_exchange(
        self,
        conversation_id: str,
        bot_id: str,
        request: str,
        response: str,
        remote_session_id: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        update: dict[str, Any] = {
            "$setOnInsert": {
                "conversation_id": conversation_id,
                "user_messages": [],
                "orchestration_logs": [],
                "created_at": now,
            },
            "$set": {"updated_at": now},
            "$push": {
                f"bot_sessions.{bot_id}.messages": {
                    "$each": [
                        BotMessage(role="orchestrator", content=request).model_dump(
                            mode="json"
                        ),
                        BotMessage(role="bot", content=response).model_dump(mode="json"),
                    ]
                }
            },
        }
        if remote_session_id is not None:
            update["$set"][
                f"bot_sessions.{bot_id}.remote_session_id"
            ] = remote_session_id
        await self._collection.update_one(
            {"_id": conversation_id}, update, upsert=True
        )

    async def add_orchestration_log(
        self,
        conversation_id: str,
        user_message: str,
        trace: OrchestrationTrace,
    ) -> None:
        document = await self._collection.find_one(
            {"_id": conversation_id}, {"orchestration_logs": 1}
        )
        turn_number = len(document.get("orchestration_logs", [])) + 1 if document else 1
        log = OrchestrationLogEntry(
            turn_number=turn_number,
            user_message=user_message,
            trace=trace.model_copy(deep=True),
        )
        now = datetime.now(timezone.utc)
        await self._collection.update_one(
            {"_id": conversation_id},
            {
                "$setOnInsert": {
                    "conversation_id": conversation_id,
                    "user_messages": [],
                    "bot_sessions": {},
                    "created_at": now,
                },
                "$set": {"updated_at": now},
                "$push": {"orchestration_logs": log.model_dump(mode="json")},
            },
            upsert=True,
        )

    async def get_state(self, conversation_id: str) -> ConversationState:
        document = await self._collection.find_one({"_id": conversation_id})
        if not document:
            return ConversationState(conversation_id=conversation_id)
        return ConversationState.model_validate(
            {
                "conversation_id": document.get("conversation_id", conversation_id),
                "user_messages": document.get("user_messages", []),
                "bot_sessions": document.get("bot_sessions", {}),
                "orchestration_logs": document.get("orchestration_logs", []),
            }
        )

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete one exact conversation, primarily for maintenance/tests."""
        result = await self._collection.delete_one({"_id": conversation_id})
        self._locks.pop(conversation_id, None)
        return result.deleted_count == 1
