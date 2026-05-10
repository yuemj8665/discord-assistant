# 변경 이력 (Changelog)

---

## [2026-05-10] work 채널 추가 — 업무 프로젝트 전담 세션

### 추가
- `src/core/config.py` — `WORK_CHANNEL_ID`, `WORK_PROJECT_DIR` 설정 추가
- `src/services/llm_service.py` — `ROLE_CONFIGS["work"]` 추가
  - system_prompt: 파일 접근·코드 작성·분석 전담 비서
  - `extra_dirs` 필드: 역할별 추가 디렉토리 지정 지원
  - allowed_tools: WebSearch, WebFetch
- `src/services/llm_service.py` — `_build_command()`에 `extra_dirs` 처리 추가
- `src/services/session_manager.py` — `WORK_CHANNEL_ID` 채널 등록
- `.env` — `WORK_CHANNEL_ID=<WORK_CHANNEL_ID>`, `WORK_PROJECT_DIR=...` 추가
- `.env.example` — 업무 프로젝트 섹션 추가

### 채널 통합
- `WORK_CHANNEL_ID`와 `MAIL_CHANNEL_ID`를 동일 채널(<WORK_CHANNEL_ID>)로 운영
  - 일반 메시지 → work 세션 LLM 응답
  - `!mail` 커맨드 → 기존대로 동작 (채널 ID 동일)

### 담당 프로젝트
- 경로: `<WORK_PROJECT_DIR>`
- Claude가 해당 디렉토리에 직접 접근하여 코드 작성·분석·디버깅 수행

---

## [2026-05-10] work 역할 system_prompt — 프로젝트 디렉토리 경로 명시

### 수정
- `src/services/llm_service.py` — work 역할 system_prompt에 `WORK_PROJECT_DIR` 경로 직접 명시
  - 기존: "현재 담당 프로젝트 디렉토리에 직접 접근하여..."
  - 변경: "담당 프로젝트 디렉토리는 {경로} 입니다. 이 디렉토리에 직접 접근하여..."
- 경로 미명시 시 Claude가 discord-assistant 디렉토리를 메인으로 오인하는 문제 해결

---

## [2026-05-10] mail_service.py — expiry datetime 버그 수정

### 수정
- `src/services/mail_service.py` — `expiry` 로드 시 `.replace(tzinfo=timezone.utc)` 제거
  - google-auth 내부는 naive datetime(UTC, tzinfo 없음)으로 비교하므로 aware datetime 전달 시 TypeError
- `from datetime import timezone` import 제거

---

## [2026-05-10] work 채널 — 프로젝트 claude.md 자동 반영

### 변경
- `src/services/llm_service.py` — work 역할 system_prompt에 아래 지시 추가:
  > 세션 시작 시 `{WORK_PROJECT_DIR}/claude.md` 파일이 존재하면 반드시 읽어 해당 파일에 정의된 정책과 규칙을 최우선으로 따르세요.

### 동작
- `20260424_HNix_Trap/claude.md`가 없으면 무시하고 기본 동작
- 파일이 생성되면 다음 세션부터 즉시 반영 (재시작 불필요)
- 프로젝트별 작업 규칙·컨벤션·페르소나를 claude.md에 정의하면 Claude가 자동 준수

---

## [2026-05-09] !mail 커맨드 추가 — Git 변경사항 메일 전송

### 추가
- `src/services/git_service.py` — git diff/파일 내용 추출, 스냅샷 저장/로드
  - `get_diff()`, `get_changed_files()`, `get_file_content()`, `get_head_commit()`
  - 마지막 전송 커밋을 `data/mail_snapshots/{repo_name}.json`에 저장
- `src/services/mail_service.py` — Gmail API 송신 래퍼
  - `data/gmail_token.json` 기반 OAuth, 만료 시 자동 갱신
- `scripts/gmail_auth.py` — Gmail OAuth 초기 인증 스크립트 (최초 1회 실행)
- `src/core/config.py` — `MAIL_RECIPIENT` 설정 추가
- `.env` / `.env.example` — `MAIL_RECIPIENT` 추가

### 수정
- `src/bot/events.py` — `!mail` 커맨드 추가
  - 사용법: `!mail <repo경로> [파일경로]`
  - 마지막 전송 이후 변경 사항만 포함 (첫 전송 시 초기 커밋 기준)
  - LLM이 diff를 분석해 변경 요약 + 추가 내용 설명 생성
  - 이메일 본문: LLM 요약 + diff 원문 + 변경 파일 전체 내용

### 동작 흐름
```
!mail /path/to/repo [파일]
    → data/mail_snapshots/{repo}.json 에서 마지막 전송 커밋 로드
    → git diff {last}..HEAD 실행
    → LLM: 변경 요약 + 추가 내용 설명 생성
    → Gmail API로 메일 전송
    → 현재 HEAD 커밋을 스냅샷으로 저장
```

### 최초 설정 방법
1. Google Cloud Console에서 Gmail API 활성화
2. Gmail OAuth 클라이언트 JSON 다운로드 → `gmail_credentials.json`으로 저장
3. `venv/bin/python3 scripts/gmail_auth.py` 실행 → 브라우저 인증
4. `.env`에 `MAIL_RECIPIENT`, `GMAIL_OAUTH_CREDENTIALS` 설정
5. 봇 재시작 후 `!mail /path/to/repo` 사용

---

## [2026-05-10] Gmail credentials 분리 — Calendar API 인증 오류 수정

### 배경
Gmail API 연동을 위해 새 OAuth credentials를 기존 `credentials.json`에 덮어쓰면서
Calendar MCP 토큰이 무효화되어 `unauthorized_client` 오류가 1분마다 반복 발생.

### 변경
- `gmail_credentials.json` 신규 추가 — Gmail API 전용 OAuth 클라이언트
- `credentials.json` 복원 — Calendar API 전용 (기존 OAuth 클라이언트)
- `src/core/config.py` — `GMAIL_OAUTH_CREDENTIALS` 설정 추가
- `src/bot/events.py` — `MailService` 초기화 시 `GMAIL_OAUTH_CREDENTIALS` 사용
- `.env` / `.env.example` — `GMAIL_OAUTH_CREDENTIALS` 항목 추가
- Calendar MCP 재인증 (`~/.config/google-calendar-mcp/tokens.json` 재발급)

---

---

## [2026-05-05] 대화 메모리 누적 시스템 추가

### 추가
- `src/services/llm_service.py` — `log_conversation()` 메서드 추가: 대화마다 `data/sessions/{role}/daily/YYYY-MM-DD.md`에 원문 로그 누적
- `src/services/llm_service.py` — `daily_dir` 프로퍼티 추가
- `src/scheduler/session_scheduler.py` — 세션 종료 15분 전 요약 트리거 추가 (`_on_summary()`)
  - Line 1: 06:15, Line 2: 11:45, Line 3: 17:45
  - LLM이 daily 파일 읽고 상세 요약 업데이트 + memory.md에 명재 정보 추가

### 변경
- `src/services/llm_service.py` — general 역할 시스템 프롬프트에 세션 시작 시 memory.md + 오늘 daily 파일 읽기 지시 추가
- `src/handlers/text_handler.py` — 대화 후 `log_conversation()` 호출 추가
- `src/bot/events.py` — `SessionScheduler`에 `session_manager` 주입
- `src/scheduler/session_scheduler.py` — `session_manager` 파라미터 추가, `_notified`에 summary 키 추가

### 데이터 구조
```
data/sessions/{role}/
├── memory.md       ← 핵심 요약 (항상 읽음)
├── daily/
│   └── YYYY-MM-DD.md  ← 날짜별 원문 + 상세 요약
└── session.json
```

---

## [2026-04-14] 알림 스케줄러 다중 캘린더 조회 추가

### 변경
- `src/services/calendar_service.py` — `get_upcoming_events()`가 primary 외 업무, 개인 캘린더도 함께 조회

---

## [2026-04-12] Google Calendar 카테고리 분류 기능 추가

### 추가
- `.env` — `CALENDAR_ID_DEFAULT`, `CALENDAR_ID_PERSONAL`, `CALENDAR_ID_WORK`, `CALENDAR_ID_EXERCISE` 추가
- `src/core/config.py` — 위 4개 캘린더 ID 설정값 추가

### 변경
- `src/services/llm_service.py` — calendar 역할 시스템 프롬프트에 카테고리별 calendarId 명시
  - 일정 등록 시 내용에 따라 업무/운동/개인/기본 캘린더 자동 분류
- 가족 캘린더 제거 (개인 캘린더로 통합) — `.env`, `config.py`, `llm_service.py` 모두 반영

### 변경 배경
기존에는 모든 일정이 primary 캘린더 하나에 등록되었으나, Google Calendar 카테고리 캘린더(업무/운동/개인)를 신규 생성하고 LLM이 내용 기반으로 자동 분류하도록 개선.

---

## [2026-04-08] 스케줄러 시각 조정 및 Google OAuth 토큰 갱신 로직 추가

### 변경
- `src/bot/events.py` — `InfraScheduler.start()` 비활성화 → 재활성화 (일일 리포트 시각 09:15로 변경 후 재개)
- `.env` — `NEWS_HOUR=6` → `NEWS_HOUR=9` (뉴스 브리핑 09:00으로 변경)
- `.env` — `INFRA_DAILY_REPORT_HOUR=6` → `INFRA_DAILY_REPORT_HOUR=9` (인프라 리포트 09:15로 변경)
- `src/services/calendar_service.py` — `google.auth.transport.requests.Request`를 이용한 access_token 자동 갱신 로직 추가

### 변경 배경
- Session Line 1 기준 5시간 창 불일치 문제 조사 중 06:00 뉴스/06:15 인프라 스케줄이 Session Line 2 시작(07:00) 이후로 이동 필요 판단
- Google OAuth `invalid_grant` 에러가 1분 간격으로 반복 발생 → `CalendarService`에 토큰 만료 시 자동 refresh 처리 추가
- MCP `google-calendar-mcp` refresh_token revoke 확인 → 수동 재인증으로 해결

---

## [2026-03-20] 초기 프로젝트 구조 구성

### 추가
- `src/core/config.py` — `.env` 기반 설정값 관리 (Config 클래스)
- `src/bot/client.py` — Discord 봇 인스턴스 생성 (Intents 설정 포함)
- `src/bot/events.py` — Discord 이벤트 핸들러 (`on_ready`, `on_message`, `!join`, `!leave`, `!reset`)
- `src/handlers/text_handler.py` — 텍스트 메시지 처리 (2000자 분할 포함)
- `src/handlers/voice_handler.py` — 음성 캡처 + STT/LLM/TTS 파이프라인
- `src/services/llm_service.py` — Claude CLI subprocess 래퍼 (세션 관리)
- `src/services/stt_service.py` — faster-whisper STT 래퍼
- `src/services/tts_service.py` — edge-tts TTS 래퍼 (async)
- `main.py` — 진입점 (서비스 초기화 + 봇 실행)
- `requirements.txt` — 의존성 목록
- `.env.example` — 환경변수 템플릿
- `.gitignore`
- `pytest.ini` — asyncio_mode = auto 설정
- `tests/test_llm.py`, `tests/test_stt.py`, `tests/test_tts.py` — 단위 테스트 (9개)
- `venv/` — Python 3.12.1 가상환경

### 테스트
- 단위 테스트 9/9 통과 (상세: `docs/test_results/test_20260320_1200.md`)

---

## [2026-03-21] 실제 구동 및 Docker 배포

### 수정
- `requirements.txt` — `webrtcvad` → `webrtcvad-wheels` 교체 (Python 3.12 호환)
- `requirements.txt` — `discord-ext-voice-recv` 추가 (discord.sinks 대체)
- `src/handlers/voice_handler.py` — 전면 재작성
  - `discord.sinks.WaveSink` → `discord-ext-voice-recv` 기반 커스텀 `AudioSink` 클래스
  - VAD + 48kHz stereo → 16kHz mono 다운샘플링 직접 구현
  - `VoiceHandler`에 `text_channel` 파라미터 추가
- `src/bot/events.py` — `VoiceRecvClient` 사용 (`channel.connect(cls=voice_recv.VoiceRecvClient)`)
- `src/bot/events.py` — `on_voice_state_update` 이벤트 추가 (음성채널 혼자 남으면 자동 퇴장)
- `src/services/llm_service.py` — `--output-format json` 으로 변경, `session_id` 파싱 및 `--resume` 연동

### 추가
- `Dockerfile` — Python 3.12-slim + ffmpeg + Node.js + Claude CLI(npm) + Python 의존성
- `docker-compose.yml` — discord-assistant + Dozzle (로그 뷰어, 포트 9999)
- `.dockerignore`

### 확인된 동작
- Discord 텍스트 채팅 → Claude 응답 정상
- `!join` / `!leave` / `!reset` 커맨드 정상
- 음성 채널 자동 퇴장 (혼자 남으면) 정상
- Claude 세션 유지 (`session_id` 파싱 후 `--resume` 재사용)
- Docker 컨테이너 정상 구동 (`~/.claude` 볼륨 마운트)
- Dozzle 로그 뷰어 정상 (ngrok + `X-Accel-Buffering:no` 헤더로 외부 접근)

---

## [2026-03-21] 음성 파이프라인 디버깅 및 DAVE E2EE 보류

### 수정
- `src/handlers/voice_handler.py`
  - VAD 프레임 크기: `VAD_FRAME_MS = 0.03` → `0.02` (30ms → 20ms, Discord 다운샘플 결과 640bytes와 일치)
  - 침묵 감지 방식 변경: 프레임 카운트 → 타이머 기반 `_silence_monitor()` 코루틴 (100ms 주기)
  - asyncio 스레드 안전성 수정: `asyncio.create_task()` → `asyncio.run_coroutine_threadsafe(coro, loop)`
  - `AudioSink.__init__`에 `loop: asyncio.AbstractEventLoop` 파라미터 추가
  - `_last_speech_time: dict[int, float]` 상태 추가
  - TTS cleanup 보장: `try/finally`로 `self._tts.cleanup(tts_path)` 감싸기
  - TTS 재생: `PCMVolumeTransformer(source, volume=1.0)` 추가
  - OpusError 패치: `_safe_decode()` 로 DAVE 암호화 패킷 → 침묵(zeros)으로 대체
  - 디버그 로그 추가: `[VAD] 발화 시작/종료`, `[TTS] 재생 시작/완료`
- `src/services/stt_service.py`
  - `vad_filter=False` — 외부 VAD(webrtcvad)가 이미 처리하므로 Whisper 내부 VAD 비활성화
  - `no_speech_threshold=0.9` — 무음 판정 완화 (기본 0.6)
- `src/bot/events.py`
  - `!join` 커맨드, `on_voice_state_update` 이벤트: 스테이지 채널 진입 시 스피커 요청 코드 추가

### 시스템
- `brew install ffmpeg` — `discord.FFmpegPCMAudio` 의존성 설치

### 확인된 동작
- VAD 발화 시작/종료 감지 정상 (`[VAD] 발화 시작`, `[VAD] 발화 종료 감지` 로그 확인)
- STT 호출 정상 (DAVE 노이즈로 환각 텍스트 출력되나 파이프라인 자체는 동작)
- LLM 응답 생성 정상
- TTS 음성 파일 생성 및 재생 정상 (ffmpeg 재생 후 자동 삭제 확인)
- 음성 채널 자동 입장/퇴장 정상

### 미해결 (DAVE E2EE)
- 수신 오디오: DAVE 암호화 → 복호화 불가 → STT 환각 텍스트
- 송신 오디오: 일반 PCM → 클라이언트 DAVE 기대 → 무음
- Discord 정책상 DAVE 비활성화 불가 → 음성 기능 보류 결정
- 테스트 결과: `docs/test_results/test_20260321_1200.md`

---

## [2026-03-21] launchd를 이용한 로컬 상시 구동 설정

### 추가
- `~/Library/LaunchAgents/com.<username>.discord-assistant.plist` — macOS launchd 서비스 설정
  - venv 파이썬으로 `main.py` 직접 실행 (로컬 파일 전체 접근 가능)
  - `KeepAlive: true` — 크래시 시 10초 후 자동 재시작
  - `RunAtLoad: true` — 맥 로그인 시 자동 시작
  - 로그 출력: `logs/bot.log`
- `logs/` 디렉토리 생성

### 배경
Docker 대신 로컬 launchd 선택 이유:
- Docker는 로컬 파일 접근에 볼륨 마운트 설정 필요 (MCP 연동 등 향후 기능 확장 시 불편)
- launchd는 macOS 기본 제공, 별도 설치 없이 venv 파이썬을 직접 실행

### 운영 명령어
```bash
# 서비스 등록 + 시작
launchctl load ~/Library/LaunchAgents/com.<username>.discord-assistant.plist

# 중지 및 등록 해제
launchctl unload ~/Library/LaunchAgents/com.<username>.discord-assistant.plist

# 재시작
launchctl kickstart -k gui/$(id -u)/com.<username>.discord-assistant

# 상태 확인
launchctl list | grep discord-assistant

# 로그 실시간 확인
tail -f logs/bot.log
```

---

## [2026-03-22] Google Calendar MCP 연동 + 알림 스케줄러

### 추가
- `mcp_config.json` — Google Calendar MCP 서버 설정 (`@cocal/google-calendar-mcp` v2.6.1)
- `src/services/calendar_service.py` — Google Calendar API 직접 조회 (MCP 토큰 재활용)
- `src/scheduler/notification_scheduler.py` — 1분 주기 캘린더 체크, 30분 전 알림
- `src/scheduler/__init__.py`
- `credentials.json` — Google OAuth 2.0 클라이언트 (데스크톱 앱, gitignore)
- `~/.config/google-calendar-mcp/tokens.json` — OAuth 토큰 (MCP 서버 자동 관리)

### 수정
- `src/services/llm_service.py`
  - `--mcp-config mcp_config.json` 플래그 추가
  - `--allowedTools`에 Google Calendar 6종 + `WebSearch` + `WebFetch` 추가
  - subprocess 실행 시 `GOOGLE_OAUTH_CREDENTIALS` 환경변수 주입
  - `import os` 추가
- `src/bot/events.py` — `on_ready`에서 `NotificationScheduler.start()` 호출
- `src/core/config.py` — `NOTIFY_CHANNEL_ID`, `DISCORD_USER_ID`, `NOTIFY_MINUTES_BEFORE`, `MCP_CONFIG_PATH`, `GOOGLE_OAUTH_CREDENTIALS` 추가
- `.env` — `NOTIFY_CHANNEL_ID`, `DISCORD_USER_ID`, `NOTIFY_MINUTES_BEFORE`, `GOOGLE_OAUTH_CREDENTIALS` 추가
- `.gitignore` — `credentials.json`, `token.json` 추가
- `requirements.txt` — `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2` 추가

### 확인된 동작
- "오늘 일정 알려줘" → MCP로 Google Calendar 직접 조회 후 응답 ✅
- 일정 등록/수정/삭제 자연어 명령 ✅
- 30분 전 자동 알림 → 지정 채널에 `@멘션` 포함 전송 ✅
- 웹 검색 후 캘린더 등록 (예: 정보처리기사 일정 검색 → 등록) ✅

### 수정 (당일 추가 버그픽스)
- `src/services/llm_service.py`
  - `--system-prompt` 추가 — Claude가 도구 사용 전 확인 요청하는 습관 제거
- `src/scheduler/notification_scheduler.py`
  - DM 전송 제거 — 채널 `@멘션`으로 충분하다는 판단

### 시스템
- `npm install -g @cocal/google-calendar-mcp` 설치
- Google Cloud Console: 프로젝트 생성 + Calendar API 활성화 + OAuth 클라이언트 발급
- OAuth 인증: 서버 화면에서 직접 브라우저 로그인 (외부 SSH에서는 localhost 콜백 불가)

---

## [2026-03-22] 멀티 세션 아키텍처 + InfraScheduler LLM 연동

### 추가
- `src/services/session_manager.py` — 채널 ID별 LLMService 라우팅 (general / calendar / infra 분리)
- `src/services/infra_service.py` — psutil CPU/MEM/DISK + docker ps 래퍼
- `src/scheduler/infra_scheduler.py` — 5분 주기 리소스 경보 + 09:00 KST 일일 리포트 (LLM 분석 포함)
- `src/scheduler/notification_scheduler.py` — 30분 전 캘린더 알림 (calendar 채널 @멘션)
- `src/mcp/infra_server.py` — psutil/docker를 MCP 도구로 노출하는 로컬 MCP 서버
- `mcp_config.json` — infra MCP 서버 추가

### 수정
- `src/services/llm_service.py`
  - `ROLE_CONFIGS` 도입: general / infra / calendar 역할별 system_prompt, mcp 여부, allowedTools 분리
  - `_build_command()` 리팩토링: role_cfg 기반으로 MCP 플래그 조건 적용
  - infra 역할 system_prompt: Discord 최적화 형식 (코드블록 표, **굵은글씨** + 이모지) 명시
- `src/services/session_manager.py` — infra LLM 별도 인스턴스 관리
- `src/bot/events.py`
  - `!infra` 커맨드 추가 — infra 채널에서 즉시 LLM 분석 리포트 요청
  - InfraScheduler에 infra_llm 전달
- `src/scheduler/infra_scheduler.py`
  - `send_report_now()` 메서드 추가 — `!infra` 수동 트리거용
  - `_send()` 2000자 분할 처리 추가
- `.env`
  - `NOTIFY_CHANNEL_ID` → calendar 채널로 변경
  - `INFRA_CHANNEL_ID`, `INFRA_CPU_THRESHOLD`, `INFRA_MEMORY_THRESHOLD`, `INFRA_DISK_THRESHOLD`, `INFRA_CHECK_INTERVAL` 추가
- `requirements.txt` — `mcp`, `psutil`, `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2` 추가

### 채널 → 세션 매핑
| 채널 | 역할 | 도구 |
|------|------|------|
| general 채널 | general | WebSearch, WebFetch |
| calendar 채널 | calendar | Google Calendar MCP, WebSearch, WebFetch |
| infra 채널 (알림 전용) | infra | mcp__infra__get_server_resources, mcp__infra__get_docker_containers |

### 확인된 동작
- `!infra` → LLM이 MCP로 서버 데이터 수집 후 코드블록 표 형식으로 Discord 전송 ✅
- 5분 주기 임계값 초과 시 infra 채널 경보 ✅
- 09:00 KST 일일 리포트 ✅

---

## [2026-03-23] IT 뉴스 브리핑 + 캘린더 인증 오류 수정

### 추가
- `src/scheduler/news_scheduler.py` — 매일 08:00 KST IT 뉴스 수집 + LLM 요약 전송
  - GeekNews (`feeds.feedburner.com`), Hacker News, 요즘IT RSS 파싱
  - 사이트별 최대 10개 수집 후 news LLM 세션에 요약 요청
  - `send_now()` 메서드 — `!news` 수동 트리거용
- `ROLE_CONFIGS["news"]` — IT 뉴스 큐레이터 역할 세션 추가 (Discord 최적화 형식 지시)
- `SessionManager` — news LLM 추가, 뉴스 채널 등록
- `events.py` — `!news` 커맨드 추가 (뉴스 채널 전용)
- `.env` — `NEWS_CHANNEL_ID`, `NEWS_HOUR`, `NEWS_MAX_ITEMS` 추가
- `config.py` — 뉴스 설정값 추가
- `requirements.txt` — `feedparser>=6.0.0` 추가

### 수정
- `src/services/calendar_service.py`
  - `Credentials` 생성 시 `client_id`, `client_secret` 누락 버그 수정
  - `credentials.json`에서 `client_id`, `client_secret` 읽어와 주입
  - `config` import 추가

### 확인된 동작
- `!news` → GeekNews/HackerNews/요즘IT 각 10개 수집 → LLM 요약 → Discord 전송 ✅
- 뉴스 채널에서 대화 가능 (세션 기억 기반 질문 응답) ✅
- 캘린더 알림 스케줄러 인증 오류 해결 (자동 토큰 갱신 정상화) ✅

### 채널 → 세션 매핑 (현재)
| 채널 | 역할 | 도구 |
|------|------|------|
| general 채널 | general | WebSearch, WebFetch |
| calendar 채널 | calendar | Google Calendar MCP, WebSearch, WebFetch |
| infra 채널 (알림 전용) | infra | MCP infra 도구 |
| news 채널 | news | WebFetch |

---

## [2026-03-23] 날짜/요일 정확도 개선

### 수정
- `src/scheduler/news_scheduler.py`
  - 프롬프트에 요일 명시: `2026-03-23 (월요일) 14:25` 형식으로 변경
  - Claude가 자체 요일 계산 시 오류 방지
- `src/scheduler/notification_scheduler.py`
  - 일정 알림 프롬프트에 현재 시각 + 요일 추가
  - `현재 시각은 2026-03-23 (월요일) 14:51이야.` 형태로 명시
  - 일정 시간 계산 정확도 향상

### 배경
Claude LLM이 날짜 문자열(`2026-03-23`)만으로 요일을 역산할 때 부정확한 경우가 있음.
일정 관리는 시간 계산이 핵심이므로 프롬프트에 요일을 직접 명시하여 혼동 방지.

---

## [2026-03-25] 음성인식 기능 제거 + Git 배포 준비

### 제거
- `src/handlers/voice_handler.py` — 음성 캡처 + VAD + STT 파이프라인 전체 제거
- `src/services/stt_service.py` — faster-whisper STT 래퍼 제거
- `src/services/tts_service.py` — edge-tts TTS 래퍼 제거
- `tests/test_stt.py`, `tests/test_tts.py` — 음성 관련 단위 테스트 제거
- `requirements.txt` — 음성 관련 패키지 제거
  - `faster-whisper`, `webrtcvad-wheels`, `discord-ext-voice-recv`, `edge-tts`, `pydub`, `ffmpeg-python`
  - `discord.py[voice]` → `discord.py` (voice 옵션 불필요)
- `src/bot/events.py` — `!join`, `!leave` 커맨드, `on_voice_state_update` 이벤트, STT/TTS 임포트 제거
- `main.py` — `STTService`, `TTSService` 임포트 및 인스턴스화 제거
- `src/core/config.py` — `WHISPER_MODEL`, `WHISPER_LANGUAGE`, `TTS_VOICE`, `TTS_OUTPUT_DIR`, `VAD_*` 설정값 제거
- `.env.example` — STT / TTS / VAD 섹션 제거

### 배경
Discord DAVE E2EE(종단간 암호화) 정책으로 음성 수신/송신이 모두 불가능한 상황.
사용 불가 기능을 유지하는 것은 코드 복잡도만 늘리므로 완전 제거.

### 수정 (Git 배포 준비)
- `.gitignore`
  - `mcp_config.json` 추가 — 봇 시작 시 `.env` 기반으로 자동 생성
  - `data/`, `logs/`, `.claude/`, `memory/` 추가
- `.env.example` — 현재 사용하는 모든 환경변수 목록으로 완전 갱신
- `src/core/config.py` — `generate_mcp_config()` 클래스메서드 추가
  - `.env` 값을 읽어 `mcp_config.json` 자동 생성
  - `GOOGLE_CALENDAR_MCP_BIN`, `VENV_PYTHON` 환경변수 추가
- `main.py` — 봇 시작 시 `config.generate_mcp_config()` 자동 호출

### 결과
- 민감정보(토큰, OAuth 자격증명, 채널 ID)가 모두 `.env`에만 존재하며 git 추적 제외
- `mcp_config.json`은 절대경로를 포함하므로 git 제외 후 실행 시 자동 생성

---

## [2026-03-25] 모든 LLM 프롬프트 KST 시각 통일

### 수정
- `src/handlers/text_handler.py`
  - 모든 사용자 메시지 앞에 현재 KST 시각 + 요일 자동 prepend
  - 형식: `[현재 시각: 2026-03-25 (화요일) 14:32]\n{user_input}`
- `src/scheduler/infra_scheduler.py`
  - 모듈 상단 상수(`ANALYSIS_PROMPT`, `ALERT_PROMPT`)를 함수(`_analysis_prompt()`, `_alert_prompt()`)로 변경
  - 호출 시점의 KST 시각 + 요일 동적 포함

### 이미 적용되어 있던 파일 (유지)
- `notification_scheduler.py` — 라인 55에서 KST 선언, 프롬프트에 요일 포함
- `news_scheduler.py` — 라인 13에서 KST 선언, 프롬프트에 요일 포함

### 전체 적용 현황
| 파일 | 상태 |
|------|------|
| text_handler.py | ✅ 추가됨 |
| infra_scheduler.py | ✅ 추가됨 |
| notification_scheduler.py | ✅ 기존 유지 |
| news_scheduler.py | ✅ 기존 유지 |

---

## [2026-03-25] GitHub Private 레포지토리 배포

### 배포 완료
- 레포지토리: `https://github.com/yuemj8665/discord-assistant` (private)
- 민감정보 검사 후 커밋: 토큰, OAuth 자격증명, 채널 ID 전혀 없음 확인
- `docs/changelog.md`에 남아있던 Discord 채널 ID 4개 제거 후 배포

### .gitignore 최종 목록
```
__pycache__/, *.pyc
.env
mcp_config.json    # 봇 시작 시 .env 기반 자동 생성
data/
logs/
.claude/
memory/
```

---

## [2026-04-01] !claude 기능 제거 + 이중 응답 버그 수정

### 제거
- `src/services/claude_usage_service.py` — Claude Code 토큰 사용량 파싱 서비스 전체 삭제
- `src/bot/events.py` — `!claude` 커맨드 + `asyncio`/`claude_usage_service` import 제거
- `src/core/config.py` — `CLAUDE_SESSION_LIMIT`, `CLAUDE_WEEKLY_LIMIT` 제거
- `src/mcp/infra_server.py` — `get_claude_usage` MCP 도구 및 관련 import 제거
- `src/scheduler/infra_scheduler.py` — `_check_claude_usage` 메서드 및 상태 변수 제거
- `src/services/llm_service.py` — infra 역할 allowed_tools에서 `mcp__infra__get_claude_usage` 제거
- `.env.example` — `CLAUDE_SESSION_LIMIT`, `CLAUDE_WEEKLY_LIMIT` 섹션 제거

### 수정
- `src/services/llm_service.py` — `_build_command()`에 `--dangerously-skip-permissions` 플래그 추가 (자동화 환경에서 권한 확인 생략)

### 버그 수정
- 이중 응답 현상 수정: launchd 외부에서 수동 실행된 구 프로세스(PID 38060)와 launchd 관리 프로세스(PID 76419)가 동시에 실행되어 모든 메시지에 응답이 2회씩 발송되던 문제 해결 (수동 프로세스 강제 종료)

---

## [2026-04-01] Claude Code 세션 스케줄링 도입

### 추가
- `src/scheduler/session_scheduler.py` — Claude Code 세션 라인 시작/종료 자동 관리
  - Session Line 1: 01:30 시작 (만료 06:30)
  - Session Line 2: 07:00 시작 (만료 12:00)
  - Session Line 3: 13:00 시작 (만료 18:00)
  - 시작 시: `claude -p "ping"` subprocess 직접 호출로 세션 워밍업 + 세션 채널에 시작 알림
  - 종료 시: 세션 채널에 만료 알림
- `src/core/config.py` — `SESSION_CHANNEL_ID` 추가
- `.env` / `.env.example` — `SESSION_CHANNEL_ID` 추가

### 수정
- `src/bot/events.py` — `SessionScheduler` 등록
- `src/services/session_manager.py` — session 채널 등록
- `src/scheduler/infra_scheduler.py` — 기존 워밍업 로직(`_session_warmup_loop`, `_start_warmup_session`) 전체 제거 → `SessionScheduler`로 이관
- `__init__` 시그니처에서 `general_llm` 파라미터 제거

### 이관 배경
- 세션 관리 책임을 `InfraScheduler`에서 `SessionScheduler`로 분리
- 전용 LLM 역할 없이 순수 스케줄링 + subprocess 직접 호출로 간소화

---

## [2026-04-01] 모닝 스케줄 시각 변경 (Session Line 1 안으로 이동)

### 수정
- IT 뉴스 브리핑: 08:00 → **06:00** KST
- 인프라 일일 리포트: 09:00 (하드코딩) → **06:15** KST (환경변수로 분리)
- `src/core/config.py` — `INFRA_DAILY_REPORT_HOUR`, `INFRA_DAILY_REPORT_MINUTE` 추가
- `src/scheduler/infra_scheduler.py` — `if now.hour == 9` 하드코딩 제거, config 값 참조로 변경
- `.env` — `NEWS_HOUR=6`, `INFRA_DAILY_REPORT_HOUR=6`, `INFRA_DAILY_REPORT_MINUTE=15` 반영
- `.env.example` — 동일하게 갱신

### 변경 배경
Session Line 1 (01:30~06:30) 내에서 모닝 스케줄이 완료되도록 배치.
Session Line 2 시작(07:00) 전 IT 뉴스와 서버 리포트 수신 완료 목적.

---

## 알려진 개선 필요 사항 (현재 하드코딩)

| 항목 | 위치 | 내용 | 우선도 |
|------|------|------|--------|
| 09:00 일일 리포트 시간 | infra_scheduler.py | `if now.hour == 9` | 높음 |
| 60초 캘린더 체크 주기 | notification_scheduler.py | `await asyncio.sleep(60)` | 중간 |
| RSS 피드 URL 3개 | news_scheduler.py | `RSS_FEEDS` 딕셔너리 | 중간 |
| "primary" 캘린더 ID | calendar_service.py | `calendarId="primary"` | 낮음 |
