import logging

import discord
from discord.ext import commands

from src.handlers.text_handler import TextHandler
from src.scheduler.infra_scheduler import InfraScheduler
from src.scheduler.news_scheduler import NewsScheduler
from src.scheduler.notification_scheduler import NotificationScheduler
from src.scheduler.session_scheduler import SessionScheduler
from src.services.session_manager import SessionManager

logger = logging.getLogger(__name__)


def register_events(
    bot: commands.Bot,
    session_manager: SessionManager,
) -> None:
    """봇에 이벤트 핸들러와 커맨드를 등록한다."""

    text_handler = TextHandler(session_manager)
    general_llm = session_manager.get_by_role("general")
    infra_llm = session_manager.get_by_role("infra")
    news_llm = session_manager.get_by_role("news")
    scheduler = NotificationScheduler(bot, general_llm)
    infra_scheduler = InfraScheduler(bot, infra_llm)
    news_scheduler = NewsScheduler(bot, news_llm)
    session_scheduler = SessionScheduler(bot)

    @bot.event
    async def on_ready() -> None:
        logger.info("봇 준비 완료: %s (ID: %s)", bot.user, bot.user.id)
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="명령을 기다리는 중...",
            )
        )
        scheduler.start()
        infra_scheduler.start()
        news_scheduler.start()
        session_scheduler.start()

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return

        # 커맨드 처리 우선
        await bot.process_commands(message)

        # 일반 메시지는 텍스트 핸들러로
        if not message.content.startswith(bot.command_prefix):
            await text_handler.handle(message)

    from src.core.config import config as _config

    @bot.command(name="reset", help="현재 채널의 Claude 대화 세션을 초기화합니다.")
    async def reset(ctx: commands.Context) -> None:
        if session_manager.reset(ctx.channel.id):
            await ctx.send("이 채널의 대화 세션이 초기화되었습니다.")
        else:
            await ctx.send("이 채널은 등록된 세션이 없습니다.")

    @bot.command(name="infra", help="홈서버 리소스 현황을 즉시 분석합니다.")
    async def infra(ctx: commands.Context) -> None:
        if ctx.channel.id != _config.INFRA_CHANNEL_ID:
            await ctx.send("이 명령어는 인프라 채널에서만 사용할 수 있습니다.")
            return
        async with ctx.typing():
            await infra_scheduler.send_report_now()

    @bot.command(name="news", help="IT 뉴스 브리핑을 즉시 전송합니다.")
    async def news(ctx: commands.Context) -> None:
        if ctx.channel.id != _config.NEWS_CHANNEL_ID:
            await ctx.send("이 명령어는 뉴스 채널에서만 사용할 수 있습니다.")
            return
        async with ctx.typing():
            await news_scheduler.send_now()

