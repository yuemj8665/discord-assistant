#!/usr/bin/env python3
"""Gmail 메일 발송을 MCP 도구로 노출하는 로컬 MCP 서버."""
import asyncio
import base64
import json
import os
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("mail")

GMAIL_TOKEN_PATH = Path(__file__).parent.parent.parent / "data" / "gmail_token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
GMAIL_CREDENTIALS_PATH = os.getenv(
    "GMAIL_OAUTH_CREDENTIALS",
    str(Path(__file__).parent.parent.parent / "gmail_credentials.json"),
)
DEFAULT_RECIPIENT = os.getenv("MAIL_RECIPIENT", "")


def _get_service():
    token_data = json.loads(GMAIL_TOKEN_PATH.read_text())
    cred_data = json.loads(Path(GMAIL_CREDENTIALS_PATH).read_text())
    client_info = cred_data.get("installed") or cred_data.get("web", {})

    expiry_str = token_data.get("expiry")
    expiry = datetime.fromisoformat(expiry_str) if expiry_str else None

    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client_info["client_id"],
        client_secret=client_info["client_secret"],
        scopes=GMAIL_SCOPES,
        expiry=expiry,
    )
    if not creds.valid:
        creds.refresh(Request())
        GMAIL_TOKEN_PATH.write_text(json.dumps({
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }))
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


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
                },
                "required": ["subject", "body"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "send_email":
        try:
            service = _get_service()
            recipient = arguments.get("to") or DEFAULT_RECIPIENT
            subject = arguments["subject"]
            body = arguments["body"]

            msg = MIMEMultipart()
            msg["To"] = recipient
            msg["From"] = "me"
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()

            return [TextContent(type="text", text=f"메일 전송 완료: {subject} → {recipient}")]
        except Exception as e:
            return [TextContent(type="text", text=f"메일 전송 실패: {e}")]

    return [TextContent(type="text", text=f"알 수 없는 도구: {name}")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
