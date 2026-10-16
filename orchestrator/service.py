import inspect
from collections.abc import Awaitable
from time import perf_counter
from typing import TypeVar
from uuid import uuid4

from src.bots.registry import BotDefinition
from src.context.store import ConversationStore
from src.orchestrator.composer import ContextComposer
from src.orchestrator.models import (
    OrchestrationTrace,
    OrchestratorResult,
    StageTrace,
    StepTrace,
)
from src.orchestrator.router import (
    VIETNAMESE_WEEKDAYS,
    Router,
    vietnam_today,
)


T = TypeVar("T")


class OrchestratorService:
    def __init__(
        self,
        store: ConversationStore,
        router: Router,
        composer: ContextComposer,
        bots: dict[str, BotDefinition],
    ) -> None:
        self._store = store
        self._router = router
        self._composer = composer
        self._bots = bots

    async def initialize(self) -> None:
        initialize = getattr(self._store, "initialize", None)
        if initialize is not None:
            await self._resolve(initialize())

    async def close(self) -> None:
        close = getattr(self._store, "close", None)
        if close is not None:
            await self._resolve(close())

    async def handle_message(
        self,
        conversation_id: str,
        user_id: str,
        message: str,
        emp_name: str,
        emp_id: str | None = None,
        include_trace: bool = False,
    ) -> str | OrchestratorResult:
        async with self._store.lock_for(conversation_id):
            turn_id = str(uuid4())
            steps: list[StepTrace] = []
            await self._resolve(self._store.add_user_message(conversation_id, message))
            global_context = await self._resolve(
                self._store.get_user_context(conversation_id)
            )
            router_started = perf_counter()
            try:
                decision, router_prompt = await self._router.decide(
                    global_context, message, emp_name
                )
            except Exception:
                raise
            steps.append(
                StepTrace(
                    sequence=1,
                    step_name="llm",
                    call_number=1,
                    reason="router",
                    status="success",
                    duration_ms=(perf_counter() - router_started) * 1000,
                    request=router_prompt,
                    response=decision.model_dump(mode="json"),
                )
            )
            trace = OrchestrationTrace(
                turn_id=turn_id,
                steps=steps,
                router=StageTrace(
                    prompt=router_prompt,
                    response=decision.model_dump(mode="json"),
                )
            )

            if decision.action == "reply":
                response = decision.response or ""
                await self._resolve(
                    self._store.add_assistant_message(conversation_id, response)
                )
                trace.steps.append(
                    StepTrace(
                        sequence=2,
                        step_name="answer_user",
                        call_number=1,
                        reason="router_reply",
                        status="success",
                        duration_ms=0,
                        request={"response": response},
                        response={"response": response},
                    )
                )
                await self._resolve(
                    self._store.add_orchestration_log(
                        conversation_id, message, trace
                    )
                )
                return self._result(response, trace, include_trace)

            bot_id = decision.target_bot
            if bot_id is None or bot_id not in self._bots:
                raise RuntimeError("Router selected an unknown bot")

            selected_bot = self._bots[bot_id]
            bot_session = await self._resolve(
                self._store.get_bot_session(conversation_id, bot_id)
            )
            composer_started = perf_counter()
            try:
                composed, composer_prompt = await self._composer.compose(
                    bot_context=bot_session.model_copy(deep=True),
                    user_intent=decision.user_intent,
                    bot_name=selected_bot.name,
                    emp_name=emp_name,
                )
            except Exception as exc:
                trace.steps.append(
                    self._error_step(2, "composer", 2, composer_started, exc)
                )
                raise
            trace.composer = StageTrace(
                prompt=composer_prompt,
                response=composed.model_dump(mode="json"),
            )
            trace.steps.append(
                StepTrace(
                    sequence=2,
                    step_name="llm",
                    call_number=2,
                    reason="composer",
                    status="success",
                    duration_ms=(perf_counter() - composer_started) * 1000,
                    request=composer_prompt,
                    response=composed.model_dump(mode="json"),
                )
            )
            bot_started = perf_counter()
            today = vietnam_today()
            bot_response = await selected_bot.adapter.send(
                composed.request,
                session_id=bot_session.remote_session_id,
                user_id=user_id,
                inputs={
                    "emp_id": emp_id or user_id,
                    "emp_name": emp_name,
                    "today": today.strftime("%m/%d/%Y"),
                    "today_weekday": VIETNAMESE_WEEKDAYS[today.weekday()],
                },
            )
            await self._resolve(
                self._store.add_bot_exchange(
                    conversation_id=conversation_id,
                    bot_id=bot_id,
                    request=composed.request,
                    response=bot_response.text,
                    remote_session_id=bot_response.session_id,
                )
            )
            await self._resolve(
                self._store.add_assistant_message(
                    conversation_id, bot_response.text
                )
            )
            trace.steps.append(
                StepTrace(
                    sequence=3,
                    step_name="bot",
                    call_number=1,
                    reason="dispatch",
                    status="success",
                    duration_ms=(perf_counter() - bot_started) * 1000,
                    request={"bot_id": bot_id, "content": composed.request},
                    response={
                        "text": bot_response.text,
                        "session_id": bot_response.session_id,
                    },
                )
            )
            await self._resolve(
                self._store.add_orchestration_log(conversation_id, message, trace)
            )
            return self._result(bot_response.text, trace, include_trace)

    @staticmethod
    async def _resolve(value: T | Awaitable[T]) -> T:
        if inspect.isawaitable(value):
            return await value
        return value

    @staticmethod
    def _error_step(
        sequence: int,
        reason: str,
        call_number: int,
        started: float,
        error: Exception,
    ) -> StepTrace:
        return StepTrace(
            sequence=sequence,
            step_name="llm",
            call_number=call_number,
            reason=reason,
            status="error",
            duration_ms=(perf_counter() - started) * 1000,
            error={"type": type(error).__name__, "message": str(error)},
        )

    @staticmethod
    def _result(
        response: str,
        trace: OrchestrationTrace,
        include_trace: bool,
    ) -> str | OrchestratorResult:
        if include_trace:
            return OrchestratorResult(response=response, trace=trace)
        return response
