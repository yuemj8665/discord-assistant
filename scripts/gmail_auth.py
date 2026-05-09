"""Gmail OAuth 초기 인증 스크립트.

최초 1회만 실행하면 data/gmail_token.json이 생성됩니다.
이후 봇이 자동으로 토큰을 갱신합니다.

사용법:
    venv/bin/python3 scripts/gmail_auth.py
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_PATH = "credentials.json"
TOKEN_PATH = "data/gmail_token.json"


def main() -> None:
    if not Path(CREDENTIALS_PATH).exists():
        print(f"❌ {CREDENTIALS_PATH} 파일이 없습니다.")
        print("Google Cloud Console → API 및 서비스 → 사용자 인증 정보에서")
        print("OAuth 2.0 클라이언트 ID를 다운로드하세요.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    Path(TOKEN_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(TOKEN_PATH).write_text(json.dumps({
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
    }))
    print(f"✅ 인증 완료. 토큰 저장: {TOKEN_PATH}")


if __name__ == "__main__":
    main()
