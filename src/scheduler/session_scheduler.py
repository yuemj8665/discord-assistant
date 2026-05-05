import asyncio
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import discord

from src.core.config import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
_WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

SESSION_LINES = [
    {"name": "Session Line 1", "start_hour": 1,  "start_minute": 30, "end_hour": 6,  "end_minute": 30},
    {"name": "Session Line 2", "start_hour": 7,  "start_minute": 0,  "end_hour": 12, "end_minute": 0},
    {"name": "Session Line 3", "start_hour": 13, "start_minute": 0,  "end_hour": 18, "end_minute": 0},
]

def _summary_time(sl: dict) -> tuple[int, int]:
    """세션 종료 15분 전 시각을 반환한다."""
    total = sl["end_hour"] * 60 + sl["end_minute"] - 15
    return total // 60, total % 60


class SessionScheduler:
    """Claude Code 세션 라인 시작/종료 알림 및 워밍업 관리."""

    def __init__(self, bot: discord.Client, session_manager) -> None:
        self._bot = bot
        self._session_manager = session_manager
        self._running = False
        self._notified: dict[str, str | None] = (
            {f"{sl['name']}_start": None for sl in SESSION_LINES}
            | {f"{sl['name']}_end": None for sl in SESSION_LINES}
            | {f"{sl['name']}_summary": None for sl in SESSION_LINES}
        )

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
                    start_key   = f"{sl['name']}_start"
                    end_key     = f"{sl['name']}_end"
                    summary_key = f"{sl['name']}_summary"
                    s_hour, s_min = _summary_time(sl)

                    if (now.hour == sl["start_hour"]
                            and now.minute >= sl["start_minute"]
                            and self._notified[start_key] != today):
                        self._notified[start_key] = today
                        await self._on_start(sl)
                    if (now.hour == s_hour
                            and now.minute >= s_min
                            and self._notified[summary_key] != today):
                        self._notified[summary_key] = today
                        await self._on_summary(sl)
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

    async def _on_summary(self, sl: dict) -> None:
        loop = asyncio.get_event_loop()
        llm = self._session_manager.get_by_role("general")
        now = datetime.now(KST)
        today = now.strftime("%Y-%m-%d")
        today_str = f"{today} ({_WEEKDAYS[now.weekday()]})"
        daily_file = Path(f"data/sessions/general/daily/{today}.md")

        if not daily_file.exists():
            logger.info("[SessionScheduler] %s 요약 생략 — 오늘 대화 없음", sl["name"])
            return

        prompt = (
            f"오늘({today_str}) 대화 기록을 정리할 시간이야.\n"
            f"data/sessions/general/daily/{today}.md 파일을 읽어서:\n"
            f"1. 해당 파일을 구조화된 상세 요약으로 업데이트해줘. 모든 주요 내용, 디테일, 맥락을 최대한 유지해.\n"
            f"2. 명재에 대해 새로 알게 된 정보(취향, 감정, 상태, 결정, 계획, 근황 등)가 있으면 "
            f"data/sessions/general/memory.md의 오늘 날짜 섹션에 추가해줘.\n"
            f"이미 memory.md에 있는 내용은 중복 추가하지 말고, 새로운 정보만 기록해줘."
        )

        logger.info("[SessionScheduler] %s 대화 요약 시작", sl["name"])
        try:
            await loop.run_in_executor(None, llm.ask, prompt)
            logger.info("[SessionScheduler] %s 대화 요약 완료", sl["name"])
            await self._send(f"<@{config.DISCORD_USER_ID}> 📝 오늘의 대화 내용을 memory에 저장했습니다.")
        except Exception as e:
            logger.error("[SessionScheduler] %s 요약 실패: %s", sl["name"], e)

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
