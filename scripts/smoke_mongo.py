"""Verify the Mongo conversation store against the configured database."""

import asyncio
from uuid import uuid4

from src.config import Settings
from src.context.mongo_store import MongoConversationStore


async def main() -> None:
    conversation_id = f"__mongo_store_smoke_test__{uuid4()}"
    settings = Settings.from_env()
    store = MongoConversationStore(
        uri=settings.mongodb_uri,
        database=settings.mongodb_database,
        collection=settings.mongodb_collection,
        server_selection_timeout_ms=(
            settings.mongodb_server_selection_timeout_ms
        ),
    )
    await store.initialize()
    try:
        await store.add_user_message(conversation_id, "xin chào")
        await store.add_assistant_message(conversation_id, "chào bạn")
        state = await store.get_state(conversation_id)
        contents = [message.content for message in state.user_messages]
        if contents != ["xin chào", "chào bạn"]:
            raise RuntimeError(f"Unexpected persisted messages: {contents!r}")
        print("Mongo conversation round-trip: OK")
    finally:
        await store.delete_conversation(conversation_id)
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
