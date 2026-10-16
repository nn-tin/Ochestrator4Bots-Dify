import json
from collections.abc import Mapping
from typing import Any

import httpx

from src.bots.base import BotAdapter
from src.orchestrator.models import BotResponse


class DifyBotAdapter(BotAdapter):
    def __init__(
        self,
        bot_name: str,
        api_key: str | None,
        base_url: str = "https://aistudio.motivesfareast.com/dify/v1",
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._bot_name = bot_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def send(
        self,
        message: str,
        session_id: str | None = None,
        *,
        user_id: str | None = None,
        inputs: Mapping[str, Any] | None = None,
    ) -> BotResponse:
        if not self._api_key:
            raise RuntimeError(f"Dify API key is not configured for {self._bot_name}")
        if not user_id:
            raise RuntimeError("user_id is required when calling Dify")

        payload = {
            "inputs": dict(inputs or {}),
            "query": message,
            "response_mode": "streaming",
            "conversation_id": session_id or "",
            "user": user_id,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        if self._client is not None:
            response = await self._client.post(
                f"{self._base_url}/chat-messages",
                headers=headers,
                json=payload,
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat-messages",
                    headers=headers,
                    json=payload,
                )

        if response.is_error:
            detail = self._error_detail(response)
            raise RuntimeError(
                f"Dify request for {self._bot_name} failed "
                f"with HTTP {response.status_code}: {detail}"
            )

        return self._parse_response(response, session_id)

    def _parse_response(
        self,
        response: httpx.Response,
        previous_session_id: str | None,
    ) -> BotResponse:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            data = response.json()
            answer = data.get("answer")
            conversation_id = data.get("conversation_id") or previous_session_id
            if not isinstance(answer, str) or not answer:
                raise RuntimeError(f"Dify returned an empty answer for {self._bot_name}")
            return BotResponse(text=answer, session_id=conversation_id)

        answer_parts: list[str] = []
        conversation_id = previous_session_id

        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue

            raw_data = line.removeprefix("data:").strip()
            if not raw_data or raw_data == "[DONE]":
                continue

            try:
                event_data = json.loads(raw_data)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Dify returned invalid streaming data for {self._bot_name}"
                ) from exc

            event = event_data.get("event")
            conversation_id = event_data.get("conversation_id") or conversation_id

            if event in {"message", "agent_message"}:
                chunk = event_data.get("answer")
                if isinstance(chunk, str):
                    answer_parts.append(chunk)
            elif event == "message_replace":
                replacement = event_data.get("answer")
                if isinstance(replacement, str):
                    answer_parts = [replacement]
            elif event == "error":
                detail = event_data.get("message") or event_data.get("code") or "unknown error"
                raise RuntimeError(f"Dify error from {self._bot_name}: {detail}")

        answer = "".join(answer_parts)
        if not answer:
            raise RuntimeError(f"Dify returned an empty answer for {self._bot_name}")

        return BotResponse(text=answer, session_id=conversation_id)

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError):
            return response.text[:500] or "no response body"

        if isinstance(data, dict):
            detail = data.get("message") or data.get("code")
            if detail:
                return str(detail)
        return "request rejected"
