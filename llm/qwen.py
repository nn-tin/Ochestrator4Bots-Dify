"""OpenAI-compatible Qwen adapter for validated structured generation."""

import json
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from src.config import Settings


OutputModel = TypeVar("OutputModel", bound=BaseModel)


class QwenClient:
    """Generate deterministic JSON and validate it against a Pydantic schema."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not settings.qwen_bearer:
            raise RuntimeError("QWEN_BEARER is not configured")

        self._base_url = settings.qwen_base_url.rstrip("/")
        self._bearer = settings.qwen_bearer
        self._model = settings.qwen_model
        self._max_tokens = settings.qwen_max_tokens
        self._client = client or httpx.AsyncClient(
            timeout=settings.qwen_timeout_seconds
        )
        self._owns_client = client is None

    async def generate_structured(
        self,
        prompt: str,
        output_model: type[OutputModel],
    ) -> OutputModel:
        schema = json.dumps(
            output_model.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Chỉ trả về một JSON object hợp lệ, không dùng Markdown "
                        f"và phải khớp JSON Schema sau: {schema}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self._max_tokens,
            "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": self._bearer,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError("Qwen request timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Qwen request failed: {exc}") from exc

        if not response.is_success:
            detail = response.text.strip()
            if len(detail) > 500:
                detail = f"{detail[:500]}..."
            message = f"Qwen returned HTTP {response.status_code}"
            raise RuntimeError(f"{message}: {detail}" if detail else message)

        try:
            content = self._message_content(response.json())
            value = self._decode_json_object(content)
            return output_model.model_validate(value)
        except (IndexError, KeyError, TypeError, ValueError, ValidationError) as exc:
            raise RuntimeError("Qwen returned an invalid structured response") from exc

    @staticmethod
    def _message_content(payload: Mapping[str, Any]) -> str:
        choices = payload["choices"]
        if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)):
            raise TypeError("choices must be a sequence")
        content = choices[0]["message"]["content"]
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
            parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, Mapping)
            ]
            joined = "".join(parts).strip()
            if joined:
                return joined
        raise ValueError("empty content")

    @staticmethod
    def _decode_json_object(content: str) -> object:
        decoder = json.JSONDecoder()
        candidates = [0]
        candidates.extend(
            index
            for index, character in enumerate(content)
            if character in "[{" and index > 0
        )
        for index in candidates:
            try:
                value, _ = decoder.raw_decode(content[index:])
            except json.JSONDecodeError:
                continue
            return value
        raise ValueError("response does not contain JSON")

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
