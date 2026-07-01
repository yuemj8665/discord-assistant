"""KST 시간 공용 유틸.

KST 타임존과 요일명 배열이 스케줄러·핸들러 5곳 이상에 복붙되어 있던 것을
한곳으로 모은다.
"""
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def now_kst() -> datetime:
    return datetime.now(KST)


def now_kst_str() -> str:
    """'2026-07-02 (수요일) 08:30' 형식의 현재 시각 문자열."""
    now = now_kst()
    return f"{now.strftime('%Y-%m-%d')} ({WEEKDAYS[now.weekday()]}) {now.strftime('%H:%M')}"
