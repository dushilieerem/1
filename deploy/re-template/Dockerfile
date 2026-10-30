# ResearchEngine 镜像模板（复制到 RE 仓库根目录后按实际入口调整）
# 构建：docker build -t research-engine:local .
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt

COPY app /app/app
RUN mkdir -p /app/output /data/marketdata

EXPOSE 9527

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=10 \
    CMD curl -fsS http://127.0.0.1:9527/api/health || exit 1

# 入口需按 RE 实际模块调整：先用 grep -rn "FastAPI(" app/ 确认
CMD ["python", "-m", "uvicorn", "app.api.app:app", "--host", "0.0.0.0", "--port", "9527"]
