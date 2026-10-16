import json
from typing import Protocol

from pydantic import BaseModel

from src.orchestrator.models import BotSession, ComposedRequest


class StructuredGenerator(Protocol):
    async def generate_structured(
        self, prompt: str, output_model: type[BaseModel]
    ) -> BaseModel: ...


class ContextComposer:
    def __init__(self, llm: StructuredGenerator) -> None:
        self._llm = llm

    async def compose(
        self,
        bot_context: BotSession,
        user_intent: str,
        bot_name: str,
        emp_name: str,
    ) -> tuple[ComposedRequest, str]:
        employee_name = json.dumps(emp_name.strip(), ensure_ascii=False)
        prompt = f"""
Bạn là bộ biên soạn yêu cầu cho {bot_name}. 
Nhiệm vụ của bạn là biến ý định hiện tại của {employee_name}, kết hợp với ngữ cảnh cần thiết từ lịch sử, thành một yêu cầu tiếng Việt hoàn chỉnh và độc lập để {bot_name} có thể tiếp tục đúng tác vụ đang xử lý.

Yêu cầu hiện tại của {employee_name}: {json.dumps(user_intent, ensure_ascii=False)}

Quy tắc:
- Nội dung chính là yêu cầu của {employee_name}.
- Chỉ dùng lịch sử để bổ sung những thông tin cần thiết như đối tượng, mã tham chiếu, lựa chọn trước đó hoặc thông tin {bot_name} đang chờ.
- Không thay đổi ý định, không thêm dữ kiện không có trong lịch sử.
- Không kể lại hội thoại, không giải thích và không tự trả lời yêu cầu.

Lịch sử với bot:
{
            json.dumps(
                [item.model_dump() for item in bot_context.messages],
                ensure_ascii=False,
                indent=2,
            )
        }
""".strip()

        result = await self._llm.generate_structured(prompt, ComposedRequest)
        return ComposedRequest.model_validate(result), prompt
