import asyncio
import logging

import feedparser
import discord

from src.core.config import config
from src.core.timeutil import now_kst_str
from src.scheduler.base_scheduler import BaseScheduler
from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)

RSS_FEEDS = {
    "GeekNews": "https://feeds.feedburner.com/geeknews-feed",
    "Hacker News": "https://news.ycombinator.com/rss",
    "요즘IT": "https://yozm.wishket.com/magazine/feed/",
}


class NewsScheduler(BaseScheduler):
    """매일 아침 IT 뉴스를 수집하고 LLM이 요약해서 Discord 채널에 전송한다."""

    def __init__(self, bot: discord.Client, news_llm: LLMService) -> None:
        super().__init__(bot)
        self._llm = news_llm

    def start(self) -> None:
        self._spawn_loop(self._daily_tick, 60)
        logger.info("[NewsScheduler] 시작 — 매일 %d시 KST 뉴스 전송", config.NEWS_HOUR)

    async def _daily_tick(self) -> None:
        if self._should_run_daily("news.daily", config.NEWS_HOUR, 0):
            await self._send_news()

    async def send_now(self) -> None:
        """즉시 뉴스를 수집하고 전송한다. !news 명령어용."""
        await self._send_news()

    async def _send_news(self) -> None:
        loop = asyncio.get_running_loop()
        now_str = now_kst_str()

        logger.info("[NewsScheduler] 뉴스 수집 시작")
        news_text = await loop.run_in_executor(None, self._fetch_all_feeds)

        if not news_text:
            logger.error("[NewsScheduler] 뉴스 수집 실패 — 전송 중단")
            await self._send("⚠️ 오늘 뉴스 수집에 실패했습니다. RSS 피드 상태를 확인해주세요.")
            return

        prompt = (
            f"다음은 오늘({now_str}) IT 뉴스 목록이야. "
            f"각 사이트별로 최대 {config.NEWS_MAX_ITEMS}개씩 한국어로 요약해줘.\n\n"
            f"{news_text}"
        )

        logger.info("[NewsScheduler] LLM 요약 요청")
        try:
            summary = await loop.run_in_executor(None, self._llm.ask, prompt)
            header = f"📰 **IT 뉴스 브리핑** ({now_str})\n\n"
            await self._send(header + summary)
            logger.info("[NewsScheduler] 뉴스 요약 전송 완료")

            # 트렌드 분석 + 유저 멘션
            trend_prompt = (
                "방금 요약한 오늘 뉴스들을 바탕으로, "
                "가장 중요한 흐름과 트렌드를 3가지 이내로 압축해서 최종 요약해줘. "
                "핵심만 간결하게, Discord에 어울리는 형식으로 작성해줘."
            )
            mention = f"<@{config.DISCORD_USER_ID}>"
            trend = await loop.run_in_executor(None, self._llm.ask, trend_prompt)
            await self._send(f"{mention} 🔥 **오늘의 핵심 트렌드**\n\n{trend}")
            logger.info("[NewsScheduler] 트렌드 분석 전송 완료")
        except Exception as e:
            logger.error("[NewsScheduler] LLM 요약 실패: %s", e)
            await self._send(f"⚠️ 뉴스 요약 생성에 실패했습니다: {e}")

    def _fetch_all_feeds(self) -> str:
        """모든 RSS 피드를 파싱해서 뉴스 목록 텍스트로 반환한다."""
        sections = []
        for source, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                items = feed.entries[:config.NEWS_MAX_ITEMS]
                if not items:
                    logger.warning("[NewsScheduler] %s: 항목 없음", source)
                    continue
                lines = [f"## {source}"]
                for i, entry in enumerate(items, 1):
                    title = entry.get("title", "(제목 없음)").strip()
                    link = entry.get("link", "").strip()
                    lines.append(f"{i}. {title}\n   {link}")
                sections.append("\n".join(lines))
                logger.info("[NewsScheduler] %s: %d개 수집", source, len(items))
            except Exception as e:
                logger.error("[NewsScheduler] %s 피드 오류: %s", source, e)

        return "\n\n".join(sections)

    async def _send(self, message: str) -> None:
        await self._send_to(config.NEWS_CHANNEL_ID, message)
