FROM python:3.12-slim

# 시스템 패키지 설치 (ffmpeg + Node.js 설치용 curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    g++ \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude CLI 설치 (npm)
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

# 의존성 먼저 복사 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY src/ ./src/
COPY main.py .

CMD ["python", "main.py"]
