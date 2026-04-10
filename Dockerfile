FROM python:3.11-slim

# ffmpeg 설치
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1-mesa-glx \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements 먼저 설치 (캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# 필요 폴더 생성
RUN mkdir -p /tmp/shorts_work outputs channels temp assets/fonts assets/characters

# 한국어 폰트 확인
RUN fc-list | grep -i noto | head -5 || true

EXPOSE $PORT

CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 2
