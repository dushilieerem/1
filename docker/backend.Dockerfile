# SVQuant 后端镜像（FastAPI + KnowledgeHub API）
# 构建上下文必须是仓库根目录：docker build -f docker/backend.Dockerfile .
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先只拷贝依赖清单，让依赖层在源码变更时命中缓存
COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.txt

COPY backend /app/backend
COPY KnowledgeHub/backend /app/KnowledgeHub/backend

# 运行期写入目录（compose 里挂载命名卷，首次创建时从镜像内容初始化）
RUN mkdir -p /app/backend/output /app/KnowledgeHub/data

WORKDIR /app/backend

EXPOSE 8766

HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=12 \
    CMD curl -fsS http://127.0.0.1:8766/api/health || exit 1

CMD ["python", "-u", "api_server.py"]
