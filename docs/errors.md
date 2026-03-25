# 에러 이벤트 기록

---

## [2026-03-20] pytest async 테스트 실패

### 증상
```
FAILED tests/test_tts.py::TestTTSService::test_synthesize_creates_file
async def functions are not natively supported.
You need to install a suitable plugin for your async framework
```

### 원인
`test_synthesize_creates_file`이 `async def`로 작성되었으나, pytest가 async 함수를 자동으로 처리하지 않음.
`pytest-asyncio` 플러그인이 설치되어 있어도 `asyncio_mode` 설정이 없으면 동작하지 않음.

### 대처
`pytest.ini`에 아래 설정 추가:
```ini
[pytest]
asyncio_mode = auto
```
모든 async 테스트 함수를 자동으로 코루틴으로 실행.

### 교훈
- `pytest-asyncio` 설치만으로는 부족하고, `asyncio_mode = auto` 설정이 필요.
- 또는 각 테스트에 `@pytest.mark.asyncio` 마커를 개별 부착해도 동작함.

---

## [2026-03-21] webrtcvad import 실패 (pkg_resources 없음)

### 증상
```
ModuleNotFoundError: No module named 'pkg_resources'
```

### 원인
`webrtcvad 2.0.10`이 내부적으로 `pkg_resources`를 사용하는데, Python 3.12 + setuptools 최신 버전(82.x)에서 `pkg_resources`가 최상위 모듈로 노출되지 않음.

### 대처
`webrtcvad` → `webrtcvad-wheels`로 교체. Python 3.12 호환 빌드 버전.
```
pip uninstall webrtcvad
pip install webrtcvad-wheels
```
`requirements.txt`도 동일하게 변경.

---

## [2026-03-21] discord.sinks 없음

### 증상
```
AttributeError: module 'discord' has no attribute 'sinks'
```

### 원인
`discord.sinks`는 `py-cord` 포크의 기능이며, 공식 `discord.py 2.x`에는 존재하지 않음.

### 대처
`discord-ext-voice-recv` 라이브러리 설치 후 `AudioSink` 클래스를 상속해 커스텀 싱크 구현.
`channel.connect(cls=voice_recv.VoiceRecvClient)` 로 연결 방식 변경.

---

## [2026-03-21] VoiceClient.listen() 없음

### 증상
```
AttributeError: 'VoiceClient' object has no attribute 'listen'
```

### 원인
`discord-ext-voice-recv`의 `.listen()` 메서드는 기본 `VoiceClient`가 아닌 `VoiceRecvClient`에만 존재함.

### 대처
```python
# 변경 전
voice_client = await channel.connect()

# 변경 후
from discord.ext import voice_recv
voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
```

---

## [2026-03-21] VAD 프레임 크기 미스매치 (모든 프레임 드롭)

### 증상
VAD가 전혀 동작하지 않음. 로그에 아무 출력 없이 음성 처리 건너뜀.

### 원인
Discord 표준 프레임(3840 bytes, 48kHz stereo 16bit 20ms) → 16kHz mono 다운샘플 후 640 bytes.
코드가 `VAD_FRAME_MS = 0.03` (30ms = 960 bytes)을 요구 → `640 < 960` → 모든 프레임 조건 불통과로 드롭.

### 대처
```python
# 변경 전
VAD_FRAME_MS = 0.03  # 30ms = 960 bytes

# 변경 후
VAD_FRAME_MS = 0.02  # 20ms = 640 bytes (Discord 다운샘플 결과와 정확히 일치)
```

### 교훈
- webrtcvad는 10/20/30ms 프레임만 지원.
- Discord 48kHz stereo 20ms → 16kHz mono 변환 결과(640 bytes)에 맞춰 20ms로 설정해야 함.

---

## [2026-03-21] asyncio 스레드 충돌 (RuntimeError: no running event loop)

### 증상
```
RuntimeError: no running event loop
```

### 원인
`AudioSink.write()`는 `discord-ext-voice-recv`의 PacketRouter 데몬 스레드에서 호출됨.
이 스레드에는 asyncio 이벤트 루프가 없으므로 `asyncio.create_task()`가 실패함.

### 대처
`AudioSink.__init__`에서 이벤트 루프 레퍼런스를 저장하고, 코루틴 예약 시 `asyncio.run_coroutine_threadsafe()` 사용.
```python
# 변경 전
asyncio.create_task(self._on_speech_end(uid, audio_bytes))

# 변경 후
asyncio.run_coroutine_threadsafe(self._on_speech_end(uid, audio_bytes), self._loop)
```

### 교훈
- `asyncio.create_task()`는 반드시 이벤트 루프가 실행 중인 스레드에서만 호출 가능.
- 별도 스레드에서 코루틴을 예약할 때는 `asyncio.run_coroutine_threadsafe(coro, loop)` 사용.

---

## [2026-03-21] 발화 종료 미감지 (RTP 침묵 동작)

### 증상
말을 멈춰도 `[VAD] 발화 종료 감지` 로그가 찍히지 않음. STT가 호출되지 않음.

### 원인
Discord는 사용자가 침묵하면 RTP 패킷 전송 자체를 중단함.
`AudioSink.write()` 호출이 없으므로 침묵 프레임 카운트가 불가능.
기존 "SILENCE_FRAMES_THRESHOLD 이상 침묵 프레임 누적" 방식이 동작하지 않음.

### 대처
100ms 주기로 `last_speech_time`을 감시하는 백그라운드 타이머 코루틴 `_silence_monitor()` 도입.
```python
async def _silence_monitor(self) -> None:
    while self._monitor_running:
        await asyncio.sleep(0.1)
        now = time.time()
        for uid in list(self._is_speaking.keys()):
            if (self._is_speaking.get(uid)
                    and uid in self._last_speech_time
                    and now - self._last_speech_time[uid] > SILENCE_TIMEOUT):
                # 발화 종료 처리
```

### 교훈
- Discord RTP는 침묵 시 패킷을 보내지 않음. 프레임 카운트 기반 침묵 감지는 동작 불가.
- 반드시 wall-clock 타이머로 마지막 발화 시각 대비 경과 시간을 감시해야 함.

---

## [2026-03-21] Whisper 내부 VAD 필터 오디오 전량 제거

### 증상
```
VAD filter removed 00:00.900 of audio
```
STT 결과 없음 (빈 문자열).

### 원인
DAVE 암호화 노이즈나 OpusError 패치 데이터(zeros)가 오디오 버퍼 대부분을 차지.
faster-whisper 내부 VAD 필터가 전체 오디오를 무음으로 판정하고 제거.

### 대처
```python
segments, info = self._model.transcribe(
    str(tmp_path),
    vad_filter=False,       # 외부 VAD(webrtcvad)가 이미 처리함
    no_speech_threshold=0.9,  # 무음 판정 기준 완화 (기본 0.6)
)
```

### 교훈
- 외부 VAD로 발화 구간을 잘라낸 후 Whisper에 전달하는 경우 `vad_filter=False`가 적절.
- `no_speech_threshold`를 높이면 노이즈가 많은 오디오에서도 STT 결과를 얻을 수 있으나, DAVE 노이즈 문제의 근본 해결책은 아님.

---

## [2026-03-21] ffmpeg 미설치

### 증상
```
discord.errors.ClientException: ffmpeg was not found.
```

### 원인
`discord.FFmpegPCMAudio`가 시스템에 ffmpeg 바이너리를 요구하나 설치되지 않음.

### 대처
```bash
brew install ffmpeg
```

### 교훈
- `discord.py[voice]` 오디오 재생은 ffmpeg를 시스템 패키지로 별도 설치해야 함.
- Docker 배포 시 `Dockerfile`에도 `RUN apt-get install -y ffmpeg` 포함 필요.

---

## [2026-03-21] TTS mp3 파일 누적 (cleanup 미실행)

### 증상
`/tmp/` 아래 TTS mp3 파일이 삭제되지 않고 계속 쌓임.

### 원인
ffmpeg 에러 발생 시 `_play_audio()`에서 예외가 발생하여 그 아래 cleanup 코드가 실행되지 않음.

### 대처
```python
# 변경 전
await self._play_audio(tts_path)
self._tts.cleanup(tts_path)

# 변경 후
try:
    await self._play_audio(tts_path)
finally:
    self._tts.cleanup(tts_path)
```

### 교훈
- 파일 정리 코드는 반드시 `try/finally`로 감싸 예외 발생 여부와 무관하게 실행 보장.

---

## [2026-03-21] Discord DAVE E2EE로 음성 파이프라인 무력화 (근본 문제)

### 증상
1. STT: DAVE 암호화된 오디오가 수신 → 노이즈/환각 텍스트 출력 ("액하, 액하..." / "^^")
2. TTS 재생: 봇 말하는 표시는 활성화되나 사용자에게 소리 들리지 않음

### 원인
Discord가 2026년 3월부터 모든 음성채널에 DAVE(Dave Audio/Video Encryption, 종단간 암호화) 강제 적용.
- **수신 방향**: 봇이 받는 오디오가 DAVE 암호화됨 → `discord-ext-voice-recv`가 복호화 불가 → OpusError 또는 노이즈 → STT 인식 불가
- **송신 방향**: 봇이 보내는 오디오는 일반 PCM → 클라이언트가 DAVE 포맷 기대 → 복호화 실패 → 무음

### 대처 시도
1. `vad_filter=False`, `no_speech_threshold=0.9` — STT 결과 부분 개선되나 환각 텍스트 발생
2. 스테이지 채널 검토 — DAVE 미적용이나 커뮤니티 서버 설정(Community mode) 필요, 미보유

### 현재 상태
- DAVE는 Discord 정책상 서버 설정에서 해제 불가 (공식 FAQ 확인)
- 음성 기능 보류 결정

### 향후 방향
- `discord-ext-voice-recv`에서 DAVE 프로토콜 지원 추가 시 재도전
- 또는 커뮤니티 서버 전환 후 스테이지 채널 활용

---

## [2026-03-21] Dozzle + ngrok SSE 타임아웃

### 증상
```
Dozzle UI가 API 연결 중에 시간 초과되었습니다.
```

### 원인
Dozzle은 실시간 로그 스트리밍에 SSE(Server-Sent Events)를 사용함. ngrok이 장시간 연결을 끊거나 응답을 버퍼링해서 타임아웃 발생.

### 대처
ngrok 실행 시 응답 헤더 추가로 버퍼링 비활성화:
```bash
ngrok http 9999 \
  --response-header-add "X-Accel-Buffering:no" \
  --request-header-add "ngrok-skip-browser-warning:true"
```

---

## [2026-03-22] Google OAuth — access_denied (테스트 사용자 미등록)

### 증상
```
403 오류: access_denied
Discord-Assistant-Calender-API은(는) Google 인증 절차를 완료하지 않았습니다.
```

### 원인
OAuth 동의 화면이 테스트 모드인데 본인 계정이 테스트 사용자로 등록되지 않음.

### 대처
Google Cloud Console → API 및 서비스 → OAuth 동의 화면 → 테스트 사용자 탭 → 본인 Gmail 추가.

---

## [2026-03-22] OAuth 콜백 localhost 연결 거부 (외부 SSH 환경)

### 증상
```
사이트에 연결할 수 없음 — localhost에서 연결을 거부했습니다. ERR_CONNECTION_REFUSED
```

### 원인
외부 컴퓨터에서 SSH로 서버를 제어하던 중 브라우저로 OAuth 인증 URL을 열었을 때, Google이 인증 완료 후 `localhost:PORT`로 콜백을 보냄. 외부 컴퓨터의 localhost는 서버가 아니므로 연결 실패.

### 대처
서버 화면에서 직접 브라우저로 인증 진행. 또는 SSH 포트 포워딩(`ssh -L 8080:localhost:8080`) 사용.

---

## [2026-03-22] google-calendar-mcp auth 명령어 형식 오류

### 증상
```
Unknown command: /path/to/credentials.json
```

### 원인
`google-calendar-mcp --auth /path/to/credentials.json` 형식으로 실행. credentials 경로는 환경변수로 전달해야 함.

### 대처
```bash
# 잘못된 방법
google-calendar-mcp --auth /path/to/credentials.json

# 올바른 방법
GOOGLE_OAUTH_CREDENTIALS=/path/to/credentials.json google-calendar-mcp auth
```

---

## [2026-03-22] Discord 메시지 2000자 초과 에러 (InfraScheduler)

### 증상
```
discord.errors.HTTPException: 400 Bad Request (error code: 50035): Invalid Form Body
In content: Must be 2000 or fewer in length.
```
`!infra` 커맨드 실행 시 LLM 분석 결과가 2000자를 초과하여 전송 실패.

### 원인
`_send()` 메서드가 `channel.send(message)`를 단순 호출. Discord API는 메시지 1건당 최대 2000자 제한.

### 대처
```python
async def _send(self, message: str) -> None:
    channel = self._bot.get_channel(config.INFRA_CHANNEL_ID)
    if not channel:
        return
    if len(message) <= 2000:
        await channel.send(message)
    else:
        for chunk in [message[i:i + 2000] for i in range(0, len(message), 2000)]:
            await channel.send(chunk)
```

### 교훈
- LLM 응답은 길이 예측이 불가능하므로 Discord 전송 시 항상 2000자 분할 처리 필요.
- `TextHandler`에는 이미 `_split_message()`가 있었으나, 스케줄러 전송 로직에는 누락되어 있었음.

---

## [2026-03-23] OrbStack 자동 종료 → Docker 데몬 오프 → 컨테이너 목록 미출력

### 증상
`!infra` 실행 시 Docker 컨테이너 목록이 표시되지 않음.

### 원인
macOS 자동 소프트웨어 업데이트(macOS 26.3.1 RSR 보안 패치)가 새벽 1시 48분에 시스템을 재부팅시킴.
재부팅 후 OrbStack이 자동으로 시작되지 않아 Docker 데몬이 오프 상태 유지.
MCP 서버의 `docker ps -a` 호출이 실패하고, Claude가 컨테이너 없음으로 해석.

### 확인 방법
```bash
# 재부팅 이력 확인
last reboot

# 업데이트 로그 확인
tail /var/log/install.log | grep -i "update\|reboot"

# 전력 관리 이벤트 확인
pmset -g log | grep -E "Sleep|Wake|Shutdown|reboot"
```

### 대처
OrbStack 자동 시작 설정:
> OrbStack 메뉴바 아이콘 → Settings → General → **Launch at Login** 활성화

### 교훈
- Docker 데몬이 꺼지면 컨테이너도 전부 정지됨 (컨테이너는 데몬 위에서 동작)
- macOS 자동 업데이트는 재부팅을 유발할 수 있음 → 홈서버 서비스는 모두 "로그인 시 자동 시작" 설정 필요
- 다음 예약 업데이트: 2026-03-24 02:00 (RSR 추가 패치)

---

## [2026-03-23] CalendarService OAuth 토큰 자동 갱신 실패

### 증상
```
The credentials do not contain the necessary fields need to refresh the access token.
You must specify refresh_token, token_uri, client_id, and client_secret.
```
`notification_scheduler`가 1분마다 캘린더 체크 시 반복 발생.

### 원인
`CalendarService._build_service()`에서 `Credentials` 객체 생성 시 `client_id`, `client_secret` 누락.
access_token 만료 후 자동 갱신 시도 시 두 값이 없어 실패.

### 대처
`credentials.json`에서 `client_id`, `client_secret`을 읽어 `Credentials`에 주입.
```python
cred_data = json.loads(Path(config.GOOGLE_OAUTH_CREDENTIALS).read_text())
client_info = cred_data.get("installed") or cred_data.get("web", {})
creds = Credentials(
    token=token_data["access_token"],
    refresh_token=token_data["refresh_token"],
    token_uri=client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
    client_id=client_info["client_id"],
    client_secret=client_info["client_secret"],
    scopes=SCOPES,
)
```

### 교훈
- `google.oauth2.credentials.Credentials`는 token 갱신 시 `client_id`, `client_secret`이 반드시 필요.
- MCP 토큰 파일(`tokens.json`)에는 이 값들이 없으므로 `credentials.json`에서 별도로 읽어야 함.

---

## [2026-03-23] LLM 요일 계산 오류 (날짜만으로 요일 역산 실패)

### 증상
news 세션에서 "오늘 무슨 요일이야?" 질문 시 잘못된 요일 답변.
일정 알림에서도 날짜 기반 시간 계산이 부정확할 가능성.

### 원인
Claude LLM이 `2026-03-23` 같은 날짜 문자열만으로 요일을 계산할 때 오류 발생.
학습 데이터 기준 요일 매핑이 실제와 다를 수 있음.

### 대처
모든 LLM 프롬프트에 요일을 직접 명시.
```python
weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
now = datetime.now(KST)
now_str = f"{now.strftime('%Y-%m-%d')} ({weekdays[now.weekday()]}) {now.strftime('%H:%M')}"
# 결과: "2026-03-23 (월요일) 14:51"
```

### 교훈
- LLM에게 날짜를 전달할 때는 요일까지 명시해야 정확한 시간 계산이 가능.
- 특히 일정 관리 봇처럼 시간 계산이 중요한 경우 반드시 적용.
