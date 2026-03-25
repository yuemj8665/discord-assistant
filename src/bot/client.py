import logging

import discord
from discord.ext import commands

from src.core.config import config

logger = logging.getLogger(__name__)


def create_bot() -> commands.Bot:
    """Discord 봇 인스턴스를 생성하고 반환한다."""
    intents = discord.Intents.default()
    intents.message_content = True  # 텍스트 메시지 읽기 권한
    intents.voice_states = True     # 음성 상태 감지 권한

    bot = commands.Bot(
        command_prefix=config.COMMAND_PREFIX,
        intents=intents,
    )
    return bot
