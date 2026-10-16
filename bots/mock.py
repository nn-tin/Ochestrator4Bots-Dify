from uuid import uuid4
from collections.abc import Mapping
from typing import Any

from src.bots.base import BotAdapter
from src.orchestrator.models import BotResponse


class MockBotAdapter(BotAdapter):
    def __init__(self, bot_name: str) -> None:
        self.bot_name = bot_name
        self.requests: list[str] = []
        self.inputs: list[dict[str, Any]] = []

    async def send(
        self,
        message: str,
        session_id: str | None = None,
        *,
        user_id: str | None = None,
        inputs: Mapping[str, Any] | None = None,
    ) -> BotResponse:
        del user_id
        self.requests.append(message)
        self.inputs.append(dict(inputs or {}))
        current_session_id = session_id or f"mock-{uuid4()}"
        lowered = message.lower()

        if self.bot_name == "Project Bot" and "tạo" in lowered:
            text = "Đã tạo công việc OP-483 thành công."
        elif self.bot_name == "Project Bot" and any(
            word in lowered for word in ("đổi", "cập nhật", "deadline", "hạn")
        ):
            text = "Đã cập nhật công việc OP-483 thành công."
        elif self.bot_name == "Mail Bot" and "quantum" in lowered:
            text = "Email từ Fuji cho biết hạn chót của dự án Quantum là ngày 30/09."
        else:
            text = f"{self.bot_name} đã nhận yêu cầu: {message}"

        return BotResponse(text=text, session_id=current_session_id)
