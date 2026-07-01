import asyncio
import logging
import os
import subprocess

import discord

from src.core.config import config
from src.core.timeutil import WEEKDAYS, now_kst
from src.scheduler.base_scheduler import BaseScheduler
from src.services.llm_service import _resolve_oauth_token

logger = logging.getLogger(__name__)

SESSION_LINES = [
    {"name": "Session Line 1", "start_hour": 1,  "start_minute": 30, "end_hour": 6,  "end_minute": 30},
    {"name": "Session Line 2", "start_hour": 7,  "start_minute": 0,  "end_hour": 12, "end_minute": 0},
    {"name": "Session Line 3", "start_hour": 13, "start_minute": 0,  "end_hour": 18, "end_minute": 0},
]

def _summary_time(sl: dict) -> tuple[int, int]:
    """세션 종료 15분 전 시각을 반환한다."""
    total = sl["end_hour"] * 60 + sl["end_minute"] - 15
    return total // 60, total % 60


class SessionScheduler(BaseScheduler):
    """Claude Code 세션 라인 시작/종료 알림 및 워밍업 관리."""

    def __init__(self, bot: discord.Client, session_manager) -> None:
        super().__init__(bot)
        self._session_manager = session_manager

    def start(self) -> None:
        self._spawn_loop(self._tick, 60)
        logger.info("[SessionScheduler] 시작 — Session Line 1/2/3 시작·종료 알림")

    async def _tick(self) -> None:
        for sl in SESSION_LINES:
            s_hour, s_min = _summary_time(sl)
            if self._should_run_daily(
                f"session.{sl['name']}.start", sl["start_hour"], sl["start_minute"]
            ):
                await self._on_start(sl)
            if self._should_run_daily(f"session.{sl['name']}.summary", s_hour, s_min):
                await self._on_summary(sl)
            if self._should_run_daily(
                f"session.{sl['name']}.end", sl["end_hour"], sl["end_minute"]
            ):
                await self._on_end(sl)

    async def _on_start(self, sl: dict) -> None:
        loop = asyncio.get_running_loop()
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
        loop = asyncio.get_running_loop()
        llm = self._session_manager.get_by_role("general")
        now = now_kst()
        today = now.strftime("%Y-%m-%d")
        today_str = f"{today} ({WEEKDAYS[now.weekday()]})"
        daily_file = llm.daily_dir / f"{today}.md"

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
            await self._send(
                f"<@{config.DISCORD_USER_ID}> ⚠️ 오늘 대화 요약 저장에 실패했습니다: {e}"
            )

    async def _on_end(self, sl: dict) -> None:
        now_str = now_kst().strftime("%H:%M")
        logger.info("[SessionScheduler] %s 종료", sl["name"])
        await self._send(
            f"<@{config.DISCORD_USER_ID}> 🌙 **{sl['name']} 종료**\n"
            f"Claude 세션이 만료되었습니다. ({now_str})"
        )

    @staticmethod
    def _warmup() -> None:
        """Claude CLI를 직접 호출해 세션을 시작한다.

        launchd 환경은 Keychain 자격증명을 읽지 못하므로 llm_service와
        동일하게 OAuth 토큰을 env로 주입한다.
        """
        env = os.environ.copy()
        token = _resolve_oauth_token()
        if token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        subprocess.run(
            ["claude", "-p", "ping",
             "--output-format", "text",
             "--dangerously-skip-permissions"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

    async def _send(self, message: str) -> None:
        await self._send_to(config.SESSION_CHANNEL_ID, message)
