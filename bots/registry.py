import os
from dataclasses import dataclass

from src.bots.base import BotAdapter
from src.bots.dify import DifyBotAdapter


@dataclass(frozen=True)
class BotDefinition:
    bot_id: str
    name: str
    description: str
    adapter: BotAdapter


def build_bot_registry() -> dict[str, BotDefinition]:
    return {
        "late": BotDefinition(
            bot_id="late",
            name="Late Request Agent",
            description=(
                "Xử lý yêu cầu đi trễ của nhân viên: tra cứu, tạo, gửi thu hồi hoặc hủy đơn xin đi trễ."
                "Chỉ chọn agent này cho nghiệp vụ đi trễ; không dùng cho nghỉ phép hay công tác."
            ),
            adapter=DifyBotAdapter(
                bot_name="Late Request Agent",
                api_key=os.getenv("DIFY_LATE_REQUEST_API_KEY"),
                base_url=os.getenv(
                    "DIFY_LATE_REQUEST_BASE_URL",
                    os.getenv(
                        "DIFY_BASE_URL", "https://aistudio.motivesfareast.com/dify/v1"
                    ),
                ),
            ),
        ),
        "leave": BotDefinition(
            bot_id="leave",
            name="Leave Request Agent",
            description=(
                "Xử lý yêu cầu nghỉ của nhân viên: tra cứu, tạo, gửi, cập nhật, thu hồi hoặc hủy các loại đơn nghỉ phép, nghỉ không lương và công tác."
                "Chỉ chọn agent này cho nghiệp vụ đi trễ, không dùng cho đi trễ."
            ),
            adapter=DifyBotAdapter(
                bot_name="Leave Request Agent",
                api_key=os.getenv("DIFY_LEAVE_REQUEST_API_KEY"),
                base_url=os.getenv(
                    "DIFY_LEAVE_REQUEST_BASE_URL",
                    os.getenv(
                        "DIFY_BASE_URL", "https://aistudio.motivesfareast.com/dify/v1"
                    ),
                ),
            ),
        ),
        "it_support": BotDefinition(
            bot_id="it_support",
            name="IT Helpdesk Agent",
            description=(
                "Hỗ trợ sự cố và yêu cầu IT nội bộ: máy tính, phần mềm, tài khoản, mạng, email, máy in, quyền truy cập và các vấn đề kỹ thuật."
                "hướng dẫn khắc phục hoặc tiếp nhận yêu cầu hỗ trợ IT."
            ),
            adapter=DifyBotAdapter(
                bot_name="IT Helpdesk Agent",
                api_key=os.getenv("DIFY_IT_HELPDESK_API_KEY"),
                base_url=os.getenv(
                    "DIFY_IT_HELPDESK_BASE_URL",
                    os.getenv(
                        "DIFY_BASE_URL", "https://aistudio.motivesfareast.com/dify/v1"
                    ),
                ),
            ),
        ),
        "meeting": BotDefinition(
            bot_id="meeting",
            name="Meeting Booking Agent",
            description=(
                "Quản lý lịch nội bộ: tạo và cập nhật lịch họp hoặc sự kiện, xem lịch theo ngày, tìm phòng họp trống và mời người tham gia. "
                "Không dùng cho hỗ trợ IT, nghỉ phép hoặc đi trễ."
            ),
            adapter=DifyBotAdapter(
                bot_name="Meeting Booking Agent",
                api_key=os.getenv("DIFY_MEETING_BOOKING_API_KEY"),
                base_url=os.getenv(
                    "DIFY_MEETING_BOOKING_BASE_URL",
                    os.getenv(
                        "DIFY_BASE_URL", "https://aistudio.motivesfareast.com/dify/v1"
                    ),
                ),
            ),
        ),
    }
