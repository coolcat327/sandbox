from loguru import logger
import sys
from config import settings

# 配置 loguru
logger.remove()  # 移除默认的 handler

# 添加控制台输出，使用配置的颜色和格式
logger.add(
    sys.stderr,
    level=settings.LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True
)

# 如果需要文件日志，可以取消下面的注释
# logger.add(
#     "logs/app_{time}.log",
#     rotation="1 day",
#     retention="7 days",
#     level="DEBUG",
#     encoding="utf-8"
# )

__all__ = ['logger']
