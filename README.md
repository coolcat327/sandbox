# Sandbox 环境 API

## 项目概述
提供安全的代码沙箱执行环境，支持API鉴权、资源隔离和并发控制。核心特性包括：
- 🔐 API密钥认证
- 🚀 基于UVicorn的异步执行
- 🐳 Docker容器化部署
- ⚖️ 请求并发控制
- ⏱️ 超时自动终止与内存限制（已优化防逃逸防OOM）

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

### GitHub Actions自动构建镜像
项目已配置GitHub Actions工作流，当`release`分支有更新时会自动构建Docker镜像并保存为产物文件。

#### 工作流程说明：
- **触发条件**：推送或拉取请求到`release`分支时自动触发
- **镜像标签**：默认使用`sandbox:0.1.2`
- **构建平台**：linux/amd64
- **输出格式**：保存为压缩的tar文件（优先使用pigz/gzip压缩）
- **产物保留**：生成的镜像文件作为GitHub Actions artifact上传，保留30天

#### 触发构建方式：

**自动触发：**
1. 将代码推送到`release`分支
2. 或者创建一个指向`release`分支的Pull Request

**手动触发：**
1. 进入GitHub仓库的Actions页面
2. 选择"Build and Save Docker Image"工作流
3. 点击"Run workflow"按钮
4. 可选择输入自定义镜像标签（默认为0.1.2）
5. 点击运行后，在GitHub Actions页面查看构建进度和下载产物

**下载和使用镜像：**
- **从Artifacts下载**：适合临时使用，文件会被自动打包为zip格式，解压后使用
- **从Releases下载**（推荐）：当推送到release分支时，会自动创建Release并上传原始的tar.gz文件，可直接使用 `docker load -i <文件名>.tar.gz` 加载

## 环境变量
| 变量名 | 默认值 | 说明               |
|--------|--------|------------------|
| API_KEY | aioai-sandbox | API访问密钥          |
| MAX_REQUESTS | 100 | 最大并发请求数          |
| MAX_WORKERS | 30 | 最大并发执行代码进程数      |
| WORKER_TIMEOUT | 60 | 任务超时时间(秒)        |
| MAX_MEMORY_THRESHOLD | 128 | 单次代码执行最大可用内存(MB) |


## 注意事项
1. 请将.env.example复制为.env，并根据实际情况修改
2. 可通过以下两种方式更新容器镜像：
   - 使用`docker-build.sh`脚本进行本地构建
   - 通过GitHub Actions自动构建（推荐用于CI/CD流程），推送到release分支会自动触发。
3. 调试时可注释docker-compose中的uvicorn命令，使用tail -f /dev/null进入容器
4. 日志文件存储在/var/log/sandbox.log
5. GitHub Actions构建的镜像产物可在对应工作流的Artifacts部分下载

