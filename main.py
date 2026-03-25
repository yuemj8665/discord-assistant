import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from src.bot.client import create_bot
from src.bot.events import register_events
from src.core.config import config
from src.services.session_manager import SessionManager

Path("logs").mkdir(exist_ok=True)

_file_handler = TimedRotatingFileHandler(
    "logs/bot.log",
    when="midnight",
    backupCount=3,
    encoding="utf-8",
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        _file_handler,
    ],
)

logger = logging.getLogger(__name__)


def main() -> None:
    config.validate()
    config.generate_mcp_config()
    logger.info("mcp_config.json 생성 완료")

    logger.info("서비스 초기화 중...")
    session_manager = SessionManager()

    bot = create_bot()
    register_events(bot, session_manager)

    logger.info("Discord 봇 시작...")
    bot.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
