import asyncio
import logging
from datetime import timedelta

import discord

from src.core.config import config
from src.core.timeutil import now_kst, now_kst_str
from src.scheduler.base_scheduler import BaseScheduler
from src.services.calendar_service import CalendarService
from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class NotificationScheduler(BaseScheduler):
    """다가오는 캘린더 일정을 감지해 Discord 채널 + DM으로 알림을 보낸다."""

    def __init__(self, bot: discord.Client, llm: LLMService) -> None:
        super().__init__(bot)
        self._llm = llm
        self._calendar = CalendarService()
        # event_id → 알림 날짜. 재시작 후 같은 일정 중복 알림 방지를 위해 영속화.
        self._notified: dict[str, str] = self._state.get("notification.notified", {})

    def start(self) -> None:
        self._spawn_loop(self._check, 60, immediate=True)
        logger.info("[스케줄러] 캘린더 알림 스케줄러 시작 (%d분 전 알림)", config.NOTIFY_MINUTES_BEFORE)

    async def _check(self) -> None:
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None, self._calendar.get_upcoming_events, config.NOTIFY_MINUTES_BEFORE
        )

        for event in events:
            event_id = event.get("id", "")
            if event_id in self._notified:
                continue

            self._mark_notified(event_id)

            title = event.get("summary", "제목 없음")
            start = event.get("start", {})
            start_time = start.get("dateTime") or start.get("date", "")
            description = event.get("description", "")

            prompt = (
                f"현재 시각은 {now_kst_str()}이야. 곧 일정이 있어. 명재에게 자연스럽게 알려줘.\n"
                f"제목: {title}\n"
                f"시작: {start_time}\n"
                f"내용: {description}\n"
                f"친근하고 간결하게, 한국어로 알림 메시지를 작성해줘."
            )

            logger.info("[스케줄러] 일정 알림 생성 중: %s", title)
            response = await loop.run_in_executor(None, self._llm.ask, prompt)

            await self._send(response)

    def _mark_notified(self, event_id: str) -> None:
        today = now_kst().strftime("%Y-%m-%d")
        self._notified[event_id] = today
        # 알림 윈도우보다 충분히 오래된 항목은 정리해 무한 증가를 막는다.
        cutoff = (now_kst() - timedelta(days=2)).strftime("%Y-%m-%d")
        self._notified = {k: v for k, v in self._notified.items() if v >= cutoff}
        self._state.set("notification.notified", self._notified)

    async def _send(self, message: str) -> None:
        if config.NOTIFY_CHANNEL_ID:
            mention = f"<@{config.DISCORD_USER_ID}>"
            await self._send_to(config.NOTIFY_CHANNEL_ID, f"{mention}\n{message}")
            logger.info("[스케줄러] 채널 알림 전송 완료")
