# Discord 개인 비서 봇

> **프로젝트 시작일**: 2026-03-20
> **최종 업데이트**: 2026-03-25

## 5-1. 프로젝트 개요

Discord 텍스트 채널을 통해 Claude AI와 실시간으로 대화할 수 있는 개인 비서 봇.
GPU 없는 로컬 홈서버(macOS Mac Mini)에서 24시간 상시 구동.

**주요 기능:**
- 텍스트 채팅: Discord 채널에서 Claude에게 질문하고 응답 수신
- 멀티 세션: 채널별 역할 분리 (general / calendar / infra / news)
- Google Calendar 연동: 자연어로 일정 조회/등록/수정/삭제
- 일정 자동 알림: 30분 전 Discord 채널에 `@멘션`으로 선제적 알림
- 홈서버 모니터링: 리소스 경보 + 09:00 일일 리포트 (`!infra`로 즉시 조회)
- IT 뉴스 브리핑: 매일 08:00 GeekNews/HackerNews/요즘IT 요약 + 트렌드 분석 (`!news`로 즉시 수신)
- 웹 검색: 실시간 정보 검색 후 응답 또는 캘린더 등록
- 세션 유지: 재시작 후에도 대화 흐름 이어짐 (`!reset`으로 초기화)

---

## 5-2. 프로젝트 구조

```
discord-assistant/
├── main.py                       # 진입점 (로깅 설정 + mcp_config 생성 + 서비스 초기화 + 봇 실행)
├── requirements.txt              # Python 의존성
├── pytest.ini                    # 테스트 설정 (asyncio_mode = auto)
├── .env                          # 환경변수 (gitignore)
├── .env.example                  # 환경변수 템플릿
├── .gitignore
│
├── src/
│   ├── core/
│   │   └── config.py             # .env 기반 설정값 관리 + mcp_config.json 자동 생성
│   ├── bot/
│   │   ├── client.py             # Discord Bot 인스턴스 생성 (Intents 설정)
│   │   └── events.py             # 이벤트 핸들러 + 커맨드(!reset/!infra/!news) + 스케줄러 시작
│   ├── handlers/
│   │   └── text_handler.py       # 텍스트 메시지 처리 (채널별 세션 라우팅)
│   ├── mcp/
│   │   └── infra_server.py       # 로컬 MCP 서버 (psutil/docker → Claude 도구로 노출)
│   ├── services/
│   │   ├── llm_service.py        # Claude CLI subprocess (ROLE_CONFIGS + 세션 관리)
│   │   ├── session_manager.py    # 채널 ID별 LLMService 라우팅
│   │   ├── infra_service.py      # psutil 리소스 + docker ps 래퍼
│   │   └── calendar_service.py   # Google Calendar API 직접 조회 (스케줄러용)
│   └── scheduler/
│       ├── notification_scheduler.py  # 1분 주기 일정 감지 + 채널 @멘션 알림
│       ├── infra_scheduler.py         # 5분 주기 리소스 경보 + 09:00 일일 리포트 (LLM 분석)
│       └── news_scheduler.py          # 매일 08:00 IT 뉴스 수집 + LLM 요약 + 트렌드 분석
│
├── data/                         # 세션 데이터 (gitignore)
│   └── sessions/
│       ├── general/
│       ├── calendar/
│       ├── infra/
│       └── news/
│
├── logs/                         # 로그 파일 (gitignore)
│   └── bot.log                   # 3일치 자동 로테이션
│
├── tests/
│   └── test_llm.py
│
└── docs/
    ├── changelog.md
    ├── errors.md
    └── test_results/
```

---

## 5-3. 데이터베이스 구조

해당 없음. 상태는 메모리(세션 ID)에만 보관하며, 재시작 시 초기화된다.

---

## 5-4. 사용 기술 및 선택 이유

### Discord 봇 프레임워크

| 기술 | 버전 | 역할 | 선택 이유 |
|------|------|------|----------|
| `discord.py` | 2.x | Discord 봇 코어 | Python Discord 봇 표준 라이브러리 |

### LLM (Claude CLI)

| 기술 | 역할 | 선택 이유 |
|------|------|----------|
| `claude` CLI | AI 응답 생성 | 별도 API 키 관리 없이 기존 Claude CLI 세션 재사용. `subprocess.run()`으로 호출 |
| `--resume session_id` | 세션 유지 | 이전 대화 맥락을 이어가는 Claude CLI 플래그. `data/session.json`에 ID 저장 후 재활용 |
| `--mcp-config` | 외부 도구 연결 | MCP 서버를 Claude CLI에 연결. Google Calendar 등 외부 서비스를 자연어로 제어 |
| `--allowedTools` | 도구 권한 설정 | 비대화형 모드에서 특정 도구 사용을 명시적으로 허용 |
| `--system-prompt` | 행동 지침 | Claude 역할과 응답 형식(Discord 최적화) 사전 지시 |
| `--output-format json` | 응답 파싱 | `session_id`, `result` 등 구조화된 데이터 추출 용이 |

### Google Calendar 연동

| 기술 | 역할 | 선택 이유 |
|------|------|----------|
| `@cocal/google-calendar-mcp` v2.6.1 | MCP 서버 | Claude CLI와 Google Calendar를 연결하는 Node.js MCP 서버. 6종 도구 제공 |
| `google-api-python-client` | 캘린더 직접 조회 | 스케줄러가 1분마다 체크할 때 Claude CLI 없이 빠르게 조회. MCP 토큰 재활용 |
| `google-auth-oauthlib` | OAuth 2.0 인증 | Google Calendar API 접근용 OAuth 토큰 관리 |
| Google OAuth 2.0 | 인증 방식 | 데스크톱 앱 유형 클라이언트. 최초 1회 브라우저 로그인 후 refresh_token으로 자동 갱신 |

### IT 뉴스 브리핑

| 기술 | 역할 | 선택 이유 |
|------|------|----------|
| `feedparser` | RSS 파싱 | GeekNews/HackerNews/요즘IT RSS 피드 수집. 경량, 단순 |
| `WebFetch` (Claude 내장) | 뉴스 내용 조회 | 피드 URL 내용을 직접 읽어 요약 품질 향상 |

### 홈서버 모니터링

| 기술 | 역할 | 선택 이유 |
|------|------|----------|
| `psutil` | 리소스 수집 | CPU/메모리/디스크 사용률 조회. 경량, 크로스플랫폼 |
| `mcp` (Python) | 로컬 MCP 서버 | psutil/docker 데이터를 Claude가 호출 가능한 도구로 노출 |
| `docker ps -a` subprocess | 컨테이너 조회 | 별도 Docker SDK 없이 CLI로 직접 조회 |

### 인프라 및 운영

| 기술 | 역할 | 선택 이유 |
|------|------|----------|
| `macOS launchd` | 프로세스 관리 | macOS 기본 제공 서비스 관리자. 재부팅 자동 시작, 크래시 자동 재시작. Docker 대비 로컬 파일 접근 자유로움 |
| `TimedRotatingFileHandler` | 로그 관리 | Python 표준 라이브러리. 매일 자정 로그 교체, 3일치 자동 보관 |
| `python-dotenv` | 설정 관리 | `.env` 파일 기반 환경변수 분리. 민감 정보 git 미포함 |
| `asyncio.run_in_executor` | 비동기 처리 | Claude CLI `subprocess.run()` (동기)을 asyncio 이벤트 루프 블로킹 없이 실행 |

---

## 5-5. 설치 및 실행 방법

### 사전 요구사항

- Python 3.10+
- Claude CLI 설치 및 로그인 완료
- Node.js (google-calendar-mcp용): `npm install -g @cocal/google-calendar-mcp`
- Google OAuth 자격증명: `credentials.json` 발급 후 프로젝트 루트에 배치

### 로컬 venv로 실행

```bash
# 1. 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 설정
cp .env.example .env
# .env 파일에서 필요한 값 입력

# 4. Google Calendar OAuth 인증 (최초 1회)
GOOGLE_OAUTH_CREDENTIALS=/path/to/credentials.json google-calendar-mcp auth

# 5. 실행 (mcp_config.json 자동 생성됨)
python main.py
```

### macOS launchd로 상시 구동

```bash
# 서비스 등록 + 시작
launchctl load ~/Library/LaunchAgents/com.mamyeongjae.discord-assistant.plist

# 중지 및 등록 해제
launchctl unload ~/Library/LaunchAgents/com.mamyeongjae.discord-assistant.plist

# 재시작
launchctl kickstart -k gui/$(id -u)/com.mamyeongjae.discord-assistant

# 로그 실시간 확인
tail -f logs/bot.log
```

### 테스트

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

### 채널 → 세션 매핑

| 채널 | 역할 | 사용 가능 도구 |
|------|------|--------------|
| general 채널 | 일반 대화 비서 | WebSearch, WebFetch |
| calendar 채널 | 일정 관리 + 30분 전 알림 수신 | Google Calendar MCP, WebSearch, WebFetch |
| infra 채널 | 서버 모니터링 알림 수신 | MCP infra (psutil, docker) |
| news 채널 | IT 뉴스 브리핑 + 대화 | WebFetch |

### Discord 봇 커맨드

| 커맨드 | 채널 | 설명 |
|--------|------|------|
| (일반 메시지) | general / calendar / news | Claude에게 텍스트로 질문 |
| `!infra` | infra | 홈서버 리소스 현황 즉시 분석 |
| `!news` | news | IT 뉴스 브리핑 즉시 수신 |
| `!reset` | 모든 채널 | 해당 채널 대화 세션 초기화 |

---

## 5-6. 에러 모음

상세 내용: [`docs/errors.md`](docs/errors.md)

| 날짜 | 에러 | 해결 |
|------|------|------|
| 2026-03-20 | pytest async 테스트 미인식 | `pytest.ini`에 `asyncio_mode = auto` 추가 |
| 2026-03-21 | `discord.sinks` 없음 | `discord-ext-voice-recv`로 교체 후 음성 기능 전체 제거 |
| 2026-03-21 | Discord DAVE E2EE — 음성 파이프라인 무력화 | 음성 기능 제거 결정 |
| 2026-03-22 | InfraScheduler 메시지 2000자 초과 | `_send()`에 2000자 분할 처리 추가 |
| 2026-03-23 | OrbStack 재부팅 후 미시작 → Docker 오프 | OrbStack "Launch at Login" 활성화 |
| 2026-03-23 | CalendarService OAuth 토큰 자동 갱신 실패 | `credentials.json`에서 `client_id`, `client_secret` 주입 |
| 2026-03-23 | LLM 요일 계산 오류 | 프롬프트에 요일 직접 명시 (`2026-03-23 (월요일) 14:51`) |

### 현재 상태 (2026-03-25)

| 기능 | 상태 |
|------|------|
| 텍스트 채팅 → Claude 응답 (general) | ✅ 정상 |
| Google Calendar 조회/등록/수정/삭제 (calendar) | ✅ 정상 |
| 30분 전 자동 알림 (@멘션, calendar 채널) | ✅ 정상 |
| 웹 검색 + 캘린더 등록 | ✅ 정상 |
| 세션 유지 (재시작 후 복원) | ✅ 정상 |
| `!infra` 즉시 서버 분석 리포트 | ✅ 정상 |
| 5분 주기 리소스 경보 | ✅ 정상 |
| 09:00 KST 일일 서버 리포트 | ✅ 정상 |
| `!news` IT 뉴스 브리핑 | ✅ 정상 |
| 08:00 KST 자동 뉴스 브리핑 | ✅ 정상 |
| 뉴스 세션 대화 (내용 기억 기반 Q&A) | ✅ 정상 |
| 음성 대화 | ❌ 제거됨 (Discord DAVE E2EE 정책) |
