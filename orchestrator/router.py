import json
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from pydantic import BaseModel

from src.bots.registry import BotDefinition
from src.orchestrator.models import ChatMessage, RouterDecision


VIETNAM_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")
VIETNAMESE_WEEKDAYS = (
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
    "Chủ Nhật",
)


def vietnam_today() -> date:
    return datetime.now(VIETNAM_TIMEZONE).date()


class StructuredGenerator(Protocol):
    async def generate_structured(
        self, prompt: str, output_model: type[BaseModel]
    ) -> BaseModel: ...


class Router:
    def __init__(
        self,
        llm: StructuredGenerator,
        bots: dict[str, BotDefinition],
    ) -> None:
        self._llm = llm
        self._bots = bots

    async def decide(
        self,
        context: list[ChatMessage],
        message: str,
        emp_name: str,
    ) -> tuple[RouterDecision, str]:
        bot_descriptions = [
            {
                "bot_id": bot.bot_id,
                "name": bot.name,
                "description": bot.description,
            }
            for bot in self._bots.values()
        ]
        employee_name = emp_name.strip()
        employee_name_json = json.dumps(employee_name, ensure_ascii=False)
        history = [
            {
                "speaker": employee_name if item.role == "user" else "Orchestrator",
                "content": item.content,
            }
            for item in context
        ]
        today_date = vietnam_today()
        today = today_date.strftime("%d/%m/%Y")
        today_weekday = VIETNAMESE_WEEKDAYS[today_date.weekday()]
        prompt = f"""
Bạn là bộ định tuyến của chatbot, có nhiệm vụ hiểu yêu cầu của {employee_name_json} 
và quyết định nên trả lời trực tiếp hay chuyển tiếp cho một bot chuyên môn trong danh sách sau:
{json.dumps(bot_descriptions, ensure_ascii=False, indent=2)}.

Quy tắc định tuyến:
- Chọn bot theo mong muốn dựa trên yêu cầu hiện tại của {employee_name_json}, không chỉ dựa vào từ khóa. 
- Tuyệt đối không xác nhận rằng đã thực hiện hành động (ví dụ: đã tạo, cập nhật, hủy, thu hồi, đặt, gửi...) liên quan tới chức năng của các bot đã liệt kê phía trên.
- Nếu yêu cầu thuộc rõ ràng chức năng của một bot, chọn action="delegate", target_bot là ID hợp lệ và response=null.
- Nếu {employee_name_json} đưa nhiều yêu cầu thuộc nhiều bot cùng lúc, dùng action="reply" để hỏi họ muốn xử lý yêu cầu nào trước.
- Nếu không bot nào phù hợp hoặc chỉ là hội thoại thông thường, dùng action="reply" và hãy trả lời nội dung của tin nhắn hiện tại như một trợ lý đang tiếp tục cuộc hội thoại tự nhiên, thân thiện. Câu phản hồi nên dễ đọc, nên tách dòng giữa các ý.
- Nếu yêu cầu ngoài phạm vi, dùng action="reply" giải thích các chức năng có thể hỗ trợ.

user_intent là yêu cầu đã được chuẩn hóa để Composer chuyển tiếp cho bot chuyên môn. Composer không xem lịch sử {employee_name_json} ↔ Orchestrator, vì vậy:
- user_intent phải chứa đầy đủ mọi thông tin đã biết và cần thiết cho tác vụ như đối tượng, ngày giờ, số lượng, lý do, mã tham chiếu hoặc lựa chọn trước đó. Không đưa yêu cầu của bot khác qua bot này.
- Lấy ý định hiện tại làm nội dung chính của yêu cầu.
- Nếu {employee_name_json} chuyển nhu cầu thuộc bot này sang bot khác, chỉ giữ lại phần của yêu cầu hiện tại thuộc phạm vi xử lý của bot được chọn; loại bỏ mọi nội dung dành cho bot khác.
- Phải thay các đại từ và tham chiếu mơ hồ trong tin nhắn hiện tại ("nó", "cái đó", "ngày đó", "như trên", "tiếp tục", ...) bằng cách kết hợp với lịch sử hội thoại. Hôm nay là {today} ({today_weekday}).
- Nếu còn thiếu thông tin nhưng đã xác định được bot, chỉ ghi rõ phần đã biết, không tự thêm dữ kiện; bot chuyên môn sẽ hỏi bổ sung.

user_intent và response viết bằng tiếng Việt, trừ khi {employee_name_json} yêu cầu ngôn ngữ khác.

Lịch sử {employee_name_json} ↔ Orchestrator (đã gồm tin nhắn hiện tại ở cuối):
{json.dumps(history, ensure_ascii=False, indent=2)}

Tin nhắn hiện tại của {employee_name_json}:
{message}
""".strip()
        result = await self._llm.generate_structured(prompt, RouterDecision)
        return RouterDecision.model_validate(result), prompt
