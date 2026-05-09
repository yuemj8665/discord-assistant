import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

from src.handlers.text_handler import TextHandler
from src.scheduler.infra_scheduler import InfraScheduler
from src.scheduler.news_scheduler import NewsScheduler
from src.scheduler.notification_scheduler import NotificationScheduler
from src.scheduler.session_scheduler import SessionScheduler
from src.services import git_service
from src.services.mail_service import MailService
from src.services.session_manager import SessionManager

KST = timezone(timedelta(hours=9))
_WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

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
    session_scheduler = SessionScheduler(bot, session_manager)

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
    mail_service = MailService(_config.GMAIL_OAUTH_CREDENTIALS)

    @bot.command(name="reset"
, help="현재 채널의 Claude 대화 세션을 초기화합니다.")
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

    @bot.command(name="mail", help="Git 레포 변경사항을 요약해 메일로 전송합니다. 사용법: !mail <repo경로> [파일경로]")
    async def mail_cmd(ctx: commands.Context, repo_path: str, file_path: Optional[str] = None) -> None:
        if ctx.channel.id != _config.MAIL_CHANNEL_ID:
            await ctx.send("이 명령어는 메일 채널에서만 사용할 수 있습니다.")
            return

        if not mail_service.is_ready():
            await ctx.send(
                "❌ Gmail 인증이 필요합니다.\n"
                "`venv/bin/python3 scripts/gmail_auth.py` 를 먼저 실행하세요."
            )
            return

        recipient = _config.MAIL_RECIPIENT
        if not recipient:
            await ctx.send("❌ `.env`에 `MAIL_RECIPIENT`가 설정되지 않았습니다.")
            return

        if not Path(repo_path).is_dir():
            await ctx.send(f"❌ 경로를 찾을 수 없습니다: `{repo_path}`")
            return

        async with ctx.typing():
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None, _build_and_send_mail,
                    repo_path, file_path, recipient
                )
                await ctx.send(result)
            except Exception as e:
                logger.error("[mail] 오류: %s", e)
                await ctx.send(f"❌ 메일 전송 실패: {e}")

    def _build_and_send_mail(
        repo_path: str,
        file_path: Optional[str],
        recipient: str,
    ) -> str:
        repo_name = Path(repo_path).resolve().name

        last_commit = git_service.load_snapshot(repo_path)
        if last_commit is None:
            last_commit = git_service.get_initial_commit(repo_path)
            is_first = True
        else:
            is_first = False

        head_commit = git_service.get_head_commit(repo_path)

        if last_commit == head_commit and not is_first:
            return f"📭 `{repo_name}` — 마지막 전송 이후 변경 사항이 없습니다."

        diff = git_service.get_diff(repo_path, last_commit, file_path)
        if not diff:
            git_service.save_snapshot(repo_path, head_commit)
            return f"📭 `{repo_name}` — 변경된 내용이 없습니다."

        changed_files = (
            [file_path] if file_path
            else git_service.get_changed_files(repo_path, last_commit)
        )

        now = datetime.now(KST)
        now_str = f"{now.strftime('%Y-%m-%d')} ({_WEEKDAYS[now.weekday()]}) {now.strftime('%H:%M')}"

        llm_prompt = (
            f"다음은 Git 레포지토리 `{repo_name}`의 변경 사항이야.\n"
            f"이메일 본문에 들어갈 내용을 한국어로 작성해줘.\n\n"
            f"1. **변경 요약**: 무엇이 어떻게 바뀌었는지 2~3줄로 핵심만 요약\n"
            f"2. **추가된 내용 설명**: 새로 추가되거나 수정된 코드/내용의 목적과 동작을 설명\n\n"
            f"[Diff]\n```\n{diff[:3000]}\n```\n\n"
            f"마크다운 없이 순수 텍스트로 작성해줘."
        )
        llm_summary = general_llm.ask(llm_prompt)

        file_sections = []
        for f in changed_files[:5]:
            content = git_service.get_file_content(repo_path, f)
            file_sections.append(
                f"{'='*60}\n파일: {f}\n{'='*60}\n{content}"
            )

        email_body = "\n".join([
            f"Git 변경 리포트 — {repo_name}",
            f"날짜: {now_str}",
            f"비교: {last_commit[:8]}..{head_commit[:8]}",
            f"변경 파일: {', '.join(changed_files[:5])}" + (f" 외 {len(changed_files)-5}개" if len(changed_files) > 5 else ""),
            "",
            "=" * 60,
            "변경 요약 및 설명",
            "=" * 60,
            llm_summary,
            "",
            "=" * 60,
            "변경 사항 (Diff)",
            "=" * 60,
            diff,
            "",
            "=" * 60,
            "파일 전체 내용",
            "=" * 60,
            "\n\n".join(file_sections),
        ])

        subject = f"[Git 변경 리포트] {repo_name} ({now.strftime('%Y-%m-%d')})"
        mail_service.send(recipient, subject, email_body)
        git_service.save_snapshot(repo_path, head_commit)

        label = "(첫 전송)" if is_first else f"{last_commit[:8]}..{head_commit[:8]}"
        return (
            f"✅ 메일 전송 완료\n"
            f"수신: `{recipient}`\n"
            f"레포: `{repo_name}` ({label})\n"
            f"변경 파일: {len(changed_files)}개"
        )

