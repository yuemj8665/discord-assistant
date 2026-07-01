"""스케줄러 공통 골격.

6개 스케줄러가 각자 복붙하던 세 가지를 한곳에 모은다:
- 폴링 루프 (한 사이클 실패해도 루프는 계속)
- '매일 HH:MM 1회' 판정 + StateStore 영속화 (재시작 후 중복 실행 방지)
- 2000자 분할 채널 전송
"""
import asyncio
import logging
from typing import Awaitable, Callable

import discord

from src.core.state_store import scheduler_state
from src.core.timeutil import now_kst

logger = logging.getLogger(__name__)


class BaseScheduler:
    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot
        self._running = False
        self._state = scheduler_state

    @property
    def name(self) -> str:
        return type(self).__name__

    def stop(self) -> None:
        self._running = False

    def _spawn_loop(
        self,
        step: Callable[[], Awaitable[None]],
        interval: int,
        immediate: bool = False,
    ) -> None:
        """step 코루틴 함수를 interval 초 간격으로 반복하는 태스크를 띄운다."""
        self._running = True
        asyncio.create_task(self._run_loop(step, interval, immediate))

    async def _run_loop(
        self,
        step: Callable[[], Awaitable[None]],
        interval: int,
        immediate: bool = False,
    ) -> None:
        if not immediate:
            await asyncio.sleep(interval)
        while self._running:
            try:
                await step()
            except Exception as e:
                logger.error("[%s] 루프 오류: %s", self.name, e)
            await asyncio.sleep(interval)

    def _should_run_daily(self, key: str, hour: int, minute: int) -> bool:
        """매일 hour:minute 이후 첫 폴링에서 한 번만 True를 반환한다.

        마지막 실행 날짜를 StateStore에 기록하므로 봇이 재시작돼도
        같은 날 두 번 실행되지 않는다.
        """
        now = now_kst()
        today = now.strftime("%Y-%m-%d")
        if (now.hour == hour and now.minute >= minute
                and self._state.get(key) != today):
            self._state.set(key, today)
            return True
        return False

    async def _send_to(self, channel_id: int, message: str) -> None:
        """지정 채널로 전송한다. 2000자 초과 시 분할."""
        channel = self._bot.get_channel(channel_id)
        if not channel:
            logger.error("[%s] 채널을 찾을 수 없음: %d", self.name, channel_id)
            return
        for chunk in [message[i:i + 2000] for i in range(0, len(message), 2000)]:
            await channel.send(chunk)
