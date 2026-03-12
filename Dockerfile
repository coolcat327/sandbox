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

# 使用清华镜像加速
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list \
    && sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list \
    && sed -i '/deb-src/s/^#//' /etc/apt/sources.list\
    && pip install --no-cache-dir poetry==${POETRY_VERSION} -i https://pypi.tuna.tsinghua.edu.cn/simple

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
COPY pyproject.toml poetry.lock ./
RUN --mount=type=cache,mode=0777,target=/root/.cache/pypoetry \
    poetry install --no-root --sync -vvvvvv 2>&1

# Final stage
FROM base AS final

# 设置时区
ENV TZ=Asia/Shanghai
# 设置Python环境
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 安装运行时依赖和常用工具和
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    default-mysql-client \
    curl \
    wget \
    vim \
    fontconfig \
    nodejs \
    npm \
    busybox \
    && rm -rf /var/lib/apt/lists/*


# **添加中文字体**
# 安装常用的中文字体包
# ttf-wqy-zenhei 是文泉驿正黑，效果不错
# ttf-wqy-microhei 是文泉驿微米黑，更小巧
# fonts-wqy-microhei 同ttf-wqy-microhei
# fonts-noto-cjk 包含思源黑体等
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ttf-wqy-zenhei \
    ttf-wqy-microhei \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv # 更新字体缓存

# 复制依赖
COPY --from=dependencies /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# 创建必要的目录
RUN mkdir -p logs

# 复制app下文件到容器/app目录
COPY app /app

# 为了安全：创建非 root 用户并限制权限，防止恶意代码删除项目文件
RUN useradd -m -u 1000 sandbox_user \
    && chown -R root:root /app \
    && chmod -R 555 /app \
    && chown -R sandbox_user:sandbox_user /app/logs \
    && chmod -R 755 /app/logs

# 注意：我们去掉了 `USER sandbox_user` 指令，让主进程(FastAPI)以 root 身份运行
# 这样主程序拥有挂载和改写等最高权限，而在 executor.py 执行具体子进程时再动态降权到 sandbox_user

# 添加健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8194/health || exit 1
