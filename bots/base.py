from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from src.orchestrator.models import BotResponse


class BotAdapter(ABC):
    @abstractmethod
    async def send(
        self,
        message: str,
        session_id: str | None = None,
        *,
        user_id: str | None = None,
        inputs: Mapping[str, Any] | None = None,
    ) -> BotResponse:
        raise NotImplementedError
