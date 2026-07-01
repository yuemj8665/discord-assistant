#!/usr/bin/env python3
"""Gmail 메일 발송을 MCP 도구로 노출하는 로컬 MCP 서버."""
import asyncio
import base64
import os
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.services.gmail_client import build_gmail_service

app = Server("mail")

GMAIL_CREDENTIALS_PATH = os.getenv(
    "GMAIL_OAUTH_CREDENTIALS",
    str(PROJECT_ROOT / "gmail_credentials.json"),
)
DEFAULT_RECIPIENT = os.getenv("MAIL_RECIPIENT", "")

# 첨부파일은 허용 디렉토리 안의 파일만 발송 가능 (mcp_config.json env로 주입).
# LLM이 도구를 호출하므로, 프롬프트 인젝션으로 임의 파일(.env, 토큰 등)이
# 메일로 유출되는 것을 막는 안전장치다.
ATTACHMENT_ALLOWED_DIRS = [
    Path(d.strip()).resolve()
    for d in os.getenv("MAIL_ATTACHMENT_ALLOWED_DIRS", "").split(",")
    if d.strip()
]
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # Gmail 첨부 한도

# 허용 디렉토리 안에 있어도 자격증명류는 절대 첨부 금지
_SENSITIVE_NAME_PARTS = ("credential", "token", "secret", "private_key", ".env")


def _validate_attachment(path_str: str) -> tuple[Path | None, str | None]:
    """첨부 경로를 검증한다. (경로, 오류메시지) 중 하나만 채워 반환."""
    path = Path(path_str).resolve()
    if not path.is_file():
        return None, f"첨부 파일 없음: {path_str}"
    if path.name.startswith("."):
        return None, f"숨김 파일은 첨부할 수 없습니다: {path.name}"
    lowered = path.name.lower()
    if any(part in lowered for part in _SENSITIVE_NAME_PARTS):
        return None, f"자격증명·토큰류 파일은 첨부할 수 없습니다: {path.name}"
    if not ATTACHMENT_ALLOWED_DIRS:
        return None, "첨부 허용 디렉토리가 설정되지 않았습니다 (MAIL_ATTACHMENT_ALLOWED_DIRS)."
    if not any(path.is_relative_to(d) for d in ATTACHMENT_ALLOWED_DIRS):
        return None, f"허용된 디렉토리 밖의 파일은 첨부할 수 없습니다: {path_str}"
    if path.stat().st_size > MAX_ATTACHMENT_BYTES:
        return None, f"첨부 파일이 25MB를 초과합니다: {path.name}"
    return path, None


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="send_email",
            description=(
                "Gmail을 통해 메일을 발송합니다. "
                f"수신자를 지정하지 않으면 기본 수신자({DEFAULT_RECIPIENT})로 발송됩니다."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "메일 제목"},
                    "body": {"type": "string", "description": "메일 본문 (순수 텍스트)"},
                    "to": {
                        "type": "string",
                        "description": f"수신자 이메일 (생략 시 기본값: {DEFAULT_RECIPIENT})",
                    },
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "첨부할 파일의 절대 경로 목록 (예: [\"/path/to/file.pdf\"])",
                    },
                },
                "required": ["subject", "body"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "send_email":
        try:
            service = build_gmail_service(GMAIL_CREDENTIALS_PATH)
            recipient = arguments.get("to") or DEFAULT_RECIPIENT
            subject = arguments["subject"]
            body = arguments["body"]

            msg = MIMEMultipart()
            msg["To"] = recipient
            msg["From"] = "me"
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            attached_names = []
            for path_str in arguments.get("attachments") or []:
                path, error = _validate_attachment(path_str)
                if error:
                    return [TextContent(type="text", text=error)]
                with path.open("rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
                msg.attach(part)
                attached_names.append(path.name)

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()

            summary = f"메일 전송 완료: {subject} → {recipient}"
            if attached_names:
                summary += f" (첨부: {', '.join(attached_names)})"
            return [TextContent(type="text", text=summary)]
        except Exception as e:
            return [TextContent(type="text", text=f"메일 전송 실패: {e}")]

    return [TextContent(type="text", text=f"알 수 없는 도구: {name}")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
