from typing import TypeVar

from pydantic import BaseModel

from src.config import Settings

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "google-genai is not installed; run pip install -r requirements.txt"
            ) from exc

        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._async_client = self._client.aio
        self._types = types
        self._model = settings.gemini_model

    async def generate_structured(
        self,
        prompt: str,
        output_model: type[OutputModel],
    ) -> OutputModel:
        response = await self._async_client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=output_model,
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response")
        return output_model.model_validate_json(response.text)

    async def close(self) -> None:
        await self._async_client.aclose()
        self._client.close()
