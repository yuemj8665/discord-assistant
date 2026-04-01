import asyncio
import logging
from datetime import datetime, timezone, timedelta

import discord

from src.core.config import config
from src.services.infra_service import InfraService
from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
_WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def _now_str() -> str:
    now = datetime.now(KST)
    return f"{now.strftime('%Y-%m-%d')} ({_WEEKDAYS[now.weekday()]}) {now.strftime('%H:%M')}"


def _analysis_prompt() -> str:
    return (
        f"[현재 시각: {_now_str()}] "
        "현재 홈서버 상태를 분석해줘. "
        "get_server_resources와 get_docker_containers 도구를 호출해서 "
        "데이터를 수집한 뒤, Discord 채팅에 최적화된 형식으로 분석 결과를 정리해줘."
    )


def _alert_prompt() -> str:
    return (
        f"[현재 시각: {_now_str()}] "
        "홈서버에서 리소스 경보가 발생했어. "
        "get_server_resources와 get_docker_containers 도구를 호출해서 "
        "현재 상태를 확인하고, 어떤 리소스가 임계값을 초과했는지 마크다운 표로 정리해줘. "
        "심각도 평가와 간단한 조치 방안도 포함해줘."
    )


class InfraScheduler:
    """홈서버 리소스 모니터링 + 아침 9시 일일 리포트 (LLM 분석 포함)."""

    def __init__(self, bot: discord.Client, infra_llm: LLMService) -> None:
        self._bot = bot
        self._llm = infra_llm
        self._infra = InfraService()
        self._running = False
        self._last_report_date: str | None = None

    def start(self) -> None:
        self._running = True
        asyncio.create_task(self._resource_loop())
        asyncio.create_task(self._daily_report_loop())
        logger.info(
            "[InfraScheduler] 시작 — 리소스 체크 %d초, 임계값 CPU:%d%% MEM:%d%% DISK:%d%%",
            config.INFRA_CHECK_INTERVAL,
            config.INFRA_CPU_THRESHOLD,
            config.INFRA_MEMORY_THRESHOLD,
            config.INFRA_DISK_THRESHOLD,
        )

    # ── 리소스 경보 루프 ──────────────────────────────────────────────────────

    async def _resource_loop(self) -> None:
        while self._running:
            await asyncio.sleep(config.INFRA_CHECK_INTERVAL)
            try:
                await self._check_resources()
            except Exception as e:
                logger.error("[InfraScheduler] 리소스 체크 오류: %s", e)

    async def _check_resources(self) -> None:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, self._infra.get_resources)

        over_threshold = (
            res.cpu >= config.INFRA_CPU_THRESHOLD
            or res.memory >= config.INFRA_MEMORY_THRESHOLD
            or res.disk >= config.INFRA_DISK_THRESHOLD
        )
        if not over_threshold:
            return

        logger.warning("[InfraScheduler] 리소스 임계값 초과 — LLM 분석 요청")
        mention = f"<@{config.DISCORD_USER_ID}>"
        try:
            analysis = await loop.run_in_executor(None, self._llm.ask, _alert_prompt())
            await self._send(f"{mention} ⚠️ **서버 리소스 경보**\n\n{analysis}")
        except Exception as e:
            logger.error("[InfraScheduler] LLM 경보 분석 실패: %s", e)
            await self._send(
                f"{mention} ⚠️ **서버 리소스 경보** (LLM 분석 실패)\n"
                f"CPU: `{res.cpu:.1f}%` / 메모리: `{res.memory:.1f}%` / 디스크: `{res.disk:.1f}%`"
            )

    # ── 아침 일일 리포트 루프 ─────────────────────────────────────────────────

    async def _daily_report_loop(self) -> None:
        while self._running:
            await asyncio.sleep(60)
            try:
                now = datetime.now(KST)
                today = now.strftime("%Y-%m-%d")
                if (now.hour == config.INFRA_DAILY_REPORT_HOUR
                        and now.minute >= config.INFRA_DAILY_REPORT_MINUTE
                        and self._last_report_date != today):
                    self._last_report_date = today
                    await self._send_daily_report()
            except Exception as e:
                logger.error("[InfraScheduler] 일일 리포트 오류: %s", e)

    async def _send_daily_report(self) -> None:
        loop = asyncio.get_event_loop()
        now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        mention = f"<@{config.DISCORD_USER_ID}>"

        logger.info("[InfraScheduler] 일일 리포트 — LLM 분석 요청")
        try:
            analysis = await loop.run_in_executor(None, self._llm.ask, _analysis_prompt())
            await self._send(f"{mention} 🌅 **오전 9시 서버 리포트** ({now_str})\n\n{analysis}")
        except Exception as e:
            logger.error("[InfraScheduler] LLM 일일 분석 실패: %s", e)
            res = await loop.run_in_executor(None, self._infra.get_resources)
            containers = await loop.run_in_executor(None, self._infra.get_containers)
            report = (
                f"{mention} 🌅 **오전 9시 서버 리포트** ({now_str}) (LLM 분석 실패)\n\n"
                f"{self._infra.format_resource_report(res)}\n\n"
                f"{self._infra.format_container_report(containers)}"
            )
            await self._send(report)

        logger.info("[InfraScheduler] 일일 리포트 전송 완료")

    # ── 수동 트리거 ───────────────────────────────────────────────────────────

    async def send_report_now(self) -> None:
        """즉시 LLM 분석 리포트를 발송한다. !infra 명령어용."""
        loop = asyncio.get_event_loop()
        now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        mention = f"<@{config.DISCORD_USER_ID}>"
        logger.info("[InfraScheduler] 수동 리포트 요청")
        try:
            analysis = await loop.run_in_executor(None, self._llm.ask, _analysis_prompt())
            await self._send(f"{mention} 🖥️ **서버 현황 리포트** ({now_str})\n\n{analysis}")
        except Exception as e:
            logger.error("[InfraScheduler] 수동 리포트 LLM 실패: %s", e)
            res = await loop.run_in_executor(None, self._infra.get_resources)
            containers = await loop.run_in_executor(None, self._infra.get_containers)
            await self._send(
                f"{mention} 🖥️ **서버 현황 리포트** ({now_str}) (LLM 분석 실패)\n\n"
                f"{self._infra.format_resource_report(res)}\n\n"
                f"{self._infra.format_container_report(containers)}"
            )

    # ── 공통 전송 ─────────────────────────────────────────────────────────────

    async def _send(self, message: str) -> None:
        channel = self._bot.get_channel(config.INFRA_CHANNEL_ID)
        if not channel:
            return
        if len(message) <= 2000:
            await channel.send(message)
        else:
            for chunk in [message[i:i + 2000] for i in range(0, len(message), 2000)]:
                await channel.send(chunk)
