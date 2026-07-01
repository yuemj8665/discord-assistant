import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.parent


class Config:
    # Discord
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!")

    # LLM (Claude CLI)
    CLAUDE_OUTPUT_FORMAT: str = "text"

    # 파일 접근 허용 폴더 (공백 구분)
    ALLOWED_DIRS: list[str] = [
        d for d in os.getenv("ALLOWED_DIRS", "").split(",") if d.strip()
    ]

    # 채널 → 세션 매핑
    GENERAL_CHANNEL_ID: int = int(os.getenv("GENERAL_CHANNEL_ID", "0"))
    CALENDAR_CHANNEL_ID: int = int(os.getenv("CALENDAR_CHANNEL_ID", "0"))
    SESSION_CHANNEL_ID: int = int(os.getenv("SESSION_CHANNEL_ID", "0"))

    # 알림 설정
    NOTIFY_CHANNEL_ID: int = int(os.getenv("NOTIFY_CHANNEL_ID", "0"))
    DISCORD_USER_ID: int = int(os.getenv("DISCORD_USER_ID", "0"))
    NOTIFY_MINUTES_BEFORE: int = int(os.getenv("NOTIFY_MINUTES_BEFORE", "30"))

    # IT 뉴스
    NEWS_CHANNEL_ID: int = int(os.getenv("NEWS_CHANNEL_ID", "0"))
    NEWS_HOUR: int = int(os.getenv("NEWS_HOUR", "8"))
    NEWS_MAX_ITEMS: int = int(os.getenv("NEWS_MAX_ITEMS", "10"))

    # 인프라 모니터링
    INFRA_CHANNEL_ID: int = int(os.getenv("INFRA_CHANNEL_ID", "0"))
    INFRA_CPU_THRESHOLD: int = int(os.getenv("INFRA_CPU_THRESHOLD", "80"))
    INFRA_MEMORY_THRESHOLD: int = int(os.getenv("INFRA_MEMORY_THRESHOLD", "85"))
    INFRA_DISK_THRESHOLD: int = int(os.getenv("INFRA_DISK_THRESHOLD", "90"))
    INFRA_CHECK_INTERVAL: int = int(os.getenv("INFRA_CHECK_INTERVAL", "300"))
    INFRA_DAILY_REPORT_HOUR: int = int(os.getenv("INFRA_DAILY_REPORT_HOUR", "6"))
    INFRA_DAILY_REPORT_MINUTE: int = int(os.getenv("INFRA_DAILY_REPORT_MINUTE", "15"))

    # 업무 프로젝트
    WORK_CHANNEL_ID: int = int(os.getenv("WORK_CHANNEL_ID", "0"))
    WORK_PROJECT_DIR: str = os.getenv("WORK_PROJECT_DIR", "")

    # 메일 발송
    MAIL_CHANNEL_ID: int = int(os.getenv("MAIL_CHANNEL_ID", "0"))
    MAIL_RECIPIENT: str = os.getenv("MAIL_RECIPIENT", "")
    GMAIL_OAUTH_CREDENTIALS: str = os.getenv(
        "GMAIL_OAUTH_CREDENTIALS",
        str(PROJECT_ROOT / "gmail_credentials.json")
    )

    # Google Calendar 카테고리 ID
    CALENDAR_ID_DEFAULT: str = os.getenv("CALENDAR_ID_DEFAULT", "primary")
    CALENDAR_ID_PERSONAL: str = os.getenv("CALENDAR_ID_PERSONAL", "primary")
    CALENDAR_ID_WORK: str = os.getenv("CALENDAR_ID_WORK", "primary")
    CALENDAR_ID_EXERCISE: str = os.getenv("CALENDAR_ID_EXERCISE", "primary")

    # MCP
    MCP_CONFIG_PATH: str = str(PROJECT_ROOT / "mcp_config.json")
    GOOGLE_OAUTH_CREDENTIALS: str = os.getenv(
        "GOOGLE_OAUTH_CREDENTIALS",
        str(PROJECT_ROOT / "credentials.json")
    )
    GOOGLE_CALENDAR_MCP_BIN: str = os.getenv(
        "GOOGLE_CALENDAR_MCP_BIN", "/opt/homebrew/bin/google-calendar-mcp"
    )
    VENV_PYTHON: str = os.getenv(
        "VENV_PYTHON", str(PROJECT_ROOT / "venv/bin/python3")
    )

    # claude CLI 인증
    # launchd(백그라운드)로 띄운 봇은 macOS Keychain의 claude 자격증명을 못 읽어
    # 401(Invalid authentication credentials)이 난다. 환경변수로 토큰을 직접 주입해 우회한다.
    # 우선순위: .env의 CLAUDE_CODE_OAUTH_TOKEN(권장: `claude setup-token` 장기 토큰)
    #          → 없으면 ~/.claude/.credentials.json의 accessToken을 런타임에 읽어 사용.
    CLAUDE_CODE_OAUTH_TOKEN: str = os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "")
    CLAUDE_CREDENTIALS_PATH: str = os.getenv(
        "CLAUDE_CREDENTIALS_PATH",
        str(Path.home() / ".claude" / ".credentials.json"),
    )

    @classmethod
    def validate(cls) -> None:
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")

    @classmethod
    def generate_mcp_config(cls) -> None:
        """mcp_config.json을 .env 설정값 기반으로 자동 생성한다."""
        config_data = {
            "mcpServers": {
                "google-calendar": {
                    "command": cls.GOOGLE_CALENDAR_MCP_BIN,
                    "env": {
                        "GOOGLE_OAUTH_CREDENTIALS": cls.GOOGLE_OAUTH_CREDENTIALS
                    }
                },
                "infra": {
                    "command": cls.VENV_PYTHON,
                    "args": [str(PROJECT_ROOT / "src/mcp/infra_server.py")]
                },
                "mail": {
                    "command": cls.VENV_PYTHON,
                    "args": [str(PROJECT_ROOT / "src/mcp/mail_server.py")],
                    "env": {
                        "GMAIL_OAUTH_CREDENTIALS": cls.GMAIL_OAUTH_CREDENTIALS,
                        "MAIL_RECIPIENT": cls.MAIL_RECIPIENT,
                        # 첨부파일은 봇이 접근 가능한 디렉토리 안의 파일만 허용
                        "MAIL_ATTACHMENT_ALLOWED_DIRS": ",".join(
                            d for d in [*cls.ALLOWED_DIRS, cls.WORK_PROJECT_DIR] if d
                        ),
                    }
                }
            }
        }
        Path(cls.MCP_CONFIG_PATH).write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False)
        )


config = Config()
