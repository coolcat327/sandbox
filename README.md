# Sandbox 环境 API

## 项目概述
提供安全的代码沙箱执行环境，支持API鉴权、资源隔离和并发控制。核心特性包括：
- 🔐 API密钥认证
- 🚀 基于UVicorn的异步执行
- 🐳 Docker容器化部署
- ⚖️ 请求并发控制
- ⏱️ 超时自动终止（可以优化）

## 项目结构
```
.
├── app/
│   ├── __init__.py
│   ├── config.py      # 环境配置
│   ├── executor.py    # 代码执行器
│   └── main.py       # FastAPI入口
├── docker-compose.yml # 容器编排
├── Dockerfile         # 容器构建
├── pyproject.toml     # Poetry依赖
└── .env.example       # 环境变量模板
```

## 快速启动
### Docker部署
```bash
docker-compose up -d
```

### 本地运行（需Poetry）
```bash
poetry install
python app/main.py
```

## 环境变量
| 变量名 | 默认值 | 说明 |
|--------|--------|-----|
| API_KEY | aioai-sandbox | API访问密钥 |
| MAX_REQUESTS | 100 | 最大并发请求数 |
| MAX_WORKERS | 30 | 工作线程池大小 |
| WORKER_TIMEOUT | 60 | 任务超时时间(秒) |

## 使用示例
```bash
curl -X POST \
  -H "Authorization: Bearer aioai-sandbox" \
  -H "Content-Type: application/json" \
  -d '{"code":"print(\"Hello World\")"}' \
  http://localhost:8194/execute
```

## 注意事项
1. 请将.env.example复制为.env，并根据实际情况修改
2. 建议通过docker-build.sh更新容器镜像
3. 调试时可注释docker-compose中的uvicorn命令，使用tail -f /dev/null进入容器
4. 日志文件存储在/var/log/sandbox.log

