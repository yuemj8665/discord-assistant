import asyncio
import logging
from datetime import datetime, timezone, timedelta

import discord

from src.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
_WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def _now_str() -> str:
    now = datetime.now(KST)
    return f"{now.strftime('%Y-%m-%d')} ({_WEEKDAYS[now.weekday()]}) {now.strftime('%H:%M')}"


class TextHandler:
    """Discord 텍스트 메시지를 처리한다."""

    def __init__(self, session_manager: SessionManager) -> None:
        self._sm = session_manager

    async def handle(self, message: discord.Message) -> None:
        llm = self._sm.get(message.channel.id)
        if llm is None:
            return  # 등록되지 않은 채널은 무시

        user_input = message.content.strip()
        if not user_input:
            return

        logger.info("[텍스트:%d] %s: %s", message.channel.id, message.author.display_name, user_input)

        prompt = f"[현재 시각: {_now_str()}]\n{user_input}"

        async with message.channel.typing():
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, llm.ask, prompt)
            except RuntimeError as e:
                logger.error("LLM 오류: %s", e)
                await message.channel.send(f"오류가 발생했습니다: {e}")
                return

        if len(response) <= 2000:
            await message.channel.send(response)
        else:
            for chunk in self._split_message(response):
                await message.channel.send(chunk)

    @staticmethod
    def _split_message(text: str, limit: int = 2000) -> list[str]:
        return [text[i : i + limit] for i in range(0, len(text), limit)]
