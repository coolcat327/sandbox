from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API认证配置
    API_KEY: str = "aioai-sandbox"
    
    # 并发控制配置
    MAX_REQUESTS: int = 500
    MAX_WORKERS: int = 300
    
    # 执行器配置
    WORKER_TIMEOUT: float = 600
    # 使用内存限制 MB
    MAX_MEMORY_THRESHOLD: int = 1024

    # 日志
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# 创建全局配置实例
settings = Settings()
