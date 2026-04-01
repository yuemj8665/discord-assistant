import asyncio
import logging
import subprocess
from datetime import datetime, timezone, timedelta

import discord

from src.core.config import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

SESSION_LINES = [
    {"name": "Session Line 1", "start_hour": 1,  "start_minute": 30, "end_hour": 6,  "end_minute": 30},
    {"name": "Session Line 2", "start_hour": 7,  "start_minute": 0,  "end_hour": 12, "end_minute": 0},
    {"name": "Session Line 3", "start_hour": 13, "start_minute": 0,  "end_hour": 18, "end_minute": 0},
]


class SessionScheduler:
    """Claude Code 세션 라인 시작/종료 알림 및 워밍업 관리."""

    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot
        self._running = False
        self._notified: dict[str, str | None] = {
            f"{sl['name']}_start": None for sl in SESSION_LINES
        } | {
            f"{sl['name']}_end": None for sl in SESSION_LINES
        }

    def start(self) -> None:
        self._running = True
        asyncio.create_task(self._loop())
        logger.info("[SessionScheduler] 시작 — Session Line 1/2/3 시작·종료 알림")

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(60)
            try:
                now = datetime.now(KST)
                today = now.strftime("%Y-%m-%d")
                for sl in SESSION_LINES:
                    start_key = f"{sl['name']}_start"
                    end_key   = f"{sl['name']}_end"
                    if (now.hour == sl["start_hour"]
                            and now.minute >= sl["start_minute"]
                            and self._notified[start_key] != today):
                        self._notified[start_key] = today
                        await self._on_start(sl)
                    if (now.hour == sl["end_hour"]
                            and now.minute >= sl["end_minute"]
                            and self._notified[end_key] != today):
                        self._notified[end_key] = today
                        await self._on_end(sl)
            except Exception as e:
                logger.error("[SessionScheduler] 루프 오류: %s", e)

    async def _on_start(self, sl: dict) -> None:
        loop = asyncio.get_event_loop()
        end_str = f"{sl['end_hour']:02d}:{sl['end_minute']:02d}"
        logger.info("[SessionScheduler] %s 워밍업 시작", sl["name"])
        try:
            await loop.run_in_executor(None, self._warmup)
            await self._send(
                f"<@{config.DISCORD_USER_ID}> ☀️ **{sl['name']} 시작**\n"
                f"Claude 세션이 시작되었습니다. {end_str}까지 유지됩니다."
            )
            logger.info("[SessionScheduler] %s 워밍업 완료", sl["name"])
        except Exception as e:
            logger.error("[SessionScheduler] %s 워밍업 실패: %s", sl["name"], e)
            await self._send(
                f"<@{config.DISCORD_USER_ID}> ❌ **{sl['name']} 워밍업 실패**: {e}"
            )

    async def _on_end(self, sl: dict) -> None:
        now_str = datetime.now(KST).strftime("%H:%M")
        logger.info("[SessionScheduler] %s 종료", sl["name"])
        await self._send(
            f"<@{config.DISCORD_USER_ID}> 🌙 **{sl['name']} 종료**\n"
            f"Claude 세션이 만료되었습니다. ({now_str})"
        )

    @staticmethod
    def _warmup() -> None:
        """Claude CLI를 직접 호출해 세션을 시작한다."""
        subprocess.run(
            ["claude", "-p", "ping",
             "--output-format", "text",
             "--dangerously-skip-permissions"],
            capture_output=True,
            text=True,
            timeout=60,
        )

    async def _send(self, message: str) -> None:
        channel = self._bot.get_channel(config.SESSION_CHANNEL_ID)
        if not channel:
            logger.error("[SessionScheduler] 채널을 찾을 수 없음: %d", config.SESSION_CHANNEL_ID)
            return
        await channel.send(message)
