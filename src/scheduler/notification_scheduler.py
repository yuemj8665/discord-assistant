import asyncio
import logging
from datetime import datetime, timezone, timedelta

import discord

from src.core.config import config
from src.services.calendar_service import CalendarService
from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class NotificationScheduler:
    """다가오는 캘린더 일정을 감지해 Discord 채널 + DM으로 알림을 보낸다."""

    def __init__(self, bot: discord.Client, llm: LLMService) -> None:
        self._bot = bot
        self._llm = llm
        self._calendar = CalendarService()
        self._notified: set[str] = set()  # 이미 알린 event_id 중복 방지
        self._running = False

    def start(self) -> None:
        self._running = True
        asyncio.create_task(self._loop())
        logger.info("[스케줄러] 캘린더 알림 스케줄러 시작 (%d분 전 알림)", config.NOTIFY_MINUTES_BEFORE)

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check()
            except Exception as e:
                logger.error("[스케줄러] 오류: %s", e)
            await asyncio.sleep(60)

    async def _check(self) -> None:
        loop = asyncio.get_event_loop()
        events = await loop.run_in_executor(
            None, self._calendar.get_upcoming_events, config.NOTIFY_MINUTES_BEFORE
        )

        for event in events:
            event_id = event.get("id", "")
            if event_id in self._notified:
                continue

            self._notified.add(event_id)

            title = event.get("summary", "제목 없음")
            start = event.get("start", {})
            start_time = start.get("dateTime") or start.get("date", "")
            description = event.get("description", "")

            KST = timezone(timedelta(hours=9))
            weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
            now = datetime.now(KST)
            now_str = f"{now.strftime('%Y-%m-%d')} ({weekdays[now.weekday()]}) {now.strftime('%H:%M')}"

            prompt = (
                f"현재 시각은 {now_str}이야. 곧 일정이 있어. 명재에게 자연스럽게 알려줘.\n"
                f"제목: {title}\n"
                f"시작: {start_time}\n"
                f"내용: {description}\n"
                f"친근하고 간결하게, 한국어로 알림 메시지를 작성해줘."
            )

            logger.info("[스케줄러] 일정 알림 생성 중: %s", title)
            response = await loop.run_in_executor(None, self._llm.ask, prompt)

            await self._send(response)

    async def _send(self, message: str) -> None:
        mention = f"<@{config.DISCORD_USER_ID}>"

        # 채널 전송 (멘션 포함)
        if config.NOTIFY_CHANNEL_ID:
            channel = self._bot.get_channel(config.NOTIFY_CHANNEL_ID)
            if channel:
                await channel.send(f"{mention}\n{message}")
                logger.info("[스케줄러] 채널 알림 전송 완료")

