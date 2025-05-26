# Base stage for common settings
FROM python:3.11.4-slim-bullseye AS base

WORKDIR /app

# Install Poetry
ENV POETRY_VERSION=2.1.2
ENV POETRY_HOME=/opt/poetry
ENV POETRY_CACHE_DIR=/tmp/poetry_cache
ENV POETRY_NO_INTERACTION=1
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV POETRY_VIRTUALENVS_CREATE=true
ENV POETRY_REQUESTS_TIMEOUT=30

# 使用阿里云镜像加速
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && pip install --no-cache-dir poetry==${POETRY_VERSION} -i https://mirrors.aliyun.com/pypi/simple/

# Dependencies stage
FROM base AS dependencies

# 安装编译依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libc-dev \
        libffi-dev \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 安装项目依赖
COPY pyproject.toml ./
# 执行命令poetry lock


RUN --mount=type=cache,target=/tmp/poetry_cache \
    poetry lock --no-update 2>&1 && poetry install --no-root

# Final stage
FROM base AS final

# 设置时区
ENV TZ=Asia/Shanghai
# 设置Python环境
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 安装运行时依赖和常用工具
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-mysql-client \
        curl \
        wget \
        vim \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖
COPY --from=dependencies /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# 创建必要的目录
RUN mkdir -p logs

# 复制app下文件到容器/app目录
COPY app /app