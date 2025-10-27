from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API认证配置
    API_KEY: str = "aioai-sandbox"
    
    # 并发控制配置
    MAX_REQUESTS: int = 100
    MAX_WORKERS: int = 30
    
    # 执行器配置
    WORKER_TIMEOUT: float = 60
    # 进程池重启计划
    POOL_RESTART_CRON: str = "0 0 * * *"
    # 使用内存限制 MB
    MAX_MEMORY_THRESHOLD: int = 2048

    # 日志
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# 创建全局配置实例
settings = Settings()
