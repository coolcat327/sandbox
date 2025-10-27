import asyncio
import sys
import tempfile
import os
import subprocess
import logging
from typing import Dict, Any
from concurrent.futures import ProcessPoolExecutor
from config import settings
import psutil
from subprocess import TimeoutExpired

from apscheduler.schedulers.asyncio import AsyncIOScheduler


# --- 安全执行函数（在 ProcessPoolExecutor 中运行） ---

def _run_code_with_subprocess_safe(
        interpreter: str,
        code: str,
        timeout: int
) -> Dict[str, Any]:
    """
    【通用安全执行函数】
    在进程中执行代码的函数，使用subprocess并在内部实现超时和强制终止。
    """
    temp_file_path = None
    # 根据解释器判断文件后缀
    if 'python' in interpreter.lower() or interpreter == sys.executable:
        suffix = ".py"
    elif 'node' in interpreter.lower():
        suffix = ".js"
    else:
        # 不支持的解释器，应由外部execute处理
        return {
            "success": False,
            "output": "",
            "error": f"内部错误：不支持的解释器 {interpreter}"
        }

    try:
        # 1. 创建临时文件来存储代码
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as temp_file:
            temp_file.write(code)
            temp_file_path = temp_file.name

        # 2. 使用subprocess执行代码
        process = subprocess.Popen(
            [interpreter, temp_file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # 确保子进程不会继承不必要的句柄
            close_fds=True
        )

        stdout, stderr = "", ""

        try:
            # 3. 等待进程完成，并使用 timeout 参数进行计时
            stdout, stderr = process.communicate(timeout=timeout)

            # 4. 检查返回码
            if process.returncode == 0:
                return {
                    "success": True,
                    "output": stdout,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "output": stdout,
                    "error": stderr
                }

        except TimeoutExpired:
            # 进程超时，强制终止它

            # 先尝试优雅地终止（发送SIGTERM）
            process.terminate()
            try:
                # 给进程2秒时间来清理
                stdout_part, stderr_part = process.communicate(timeout=2)
                stdout += stdout_part
                stderr += stderr_part
            except TimeoutExpired:
                # 仍然不退出，强制杀死（发送SIGKILL）
                process.kill()
                stdout_part, stderr_part = process.communicate()
                stdout += stdout_part
                stderr += stderr_part

            return {
                "success": False,
                "output": stdout,
                "error": f"代码执行超时 (>{timeout}秒)。进程已被强制终止。"
            }

    except Exception as e:
        # 捕获其他如 FileNotFoundError (解释器不存在) 等错误
        return {
            "success": False,
            "output": "",
            "error": str(e)
        }
    finally:
        # 5. 删除临时文件
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                # 日志记录清理失败的情况，但不要影响主逻辑
                logging.error(f"无法删除临时文件 {temp_file_path}: {e}")


def _run_python_code_in_process_safe(code: str, timeout: int) -> Dict[str, Any]:
    """Python代码执行的封装函数"""
    return _run_code_with_subprocess_safe(sys.executable, code, timeout)


def _run_nodejs_code_in_process_safe(code: str, timeout: int) -> Dict[str, Any]:
    """Node.js代码执行的封装函数"""
    return _run_code_with_subprocess_safe('node', code, timeout)


# --- 辅助函数 ---

def check_nodejs_available():
    """检查Node.js是否可用"""
    try:
        subprocess.run(['node', '--version'],
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,
                       check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


# --- 主执行器类 ---

class CodeExecutor:
    def __init__(self, timeout: int = 30, max_workers: int = 10):
        # 配置日志系统
        logging.basicConfig(
            level=settings.LOG_LEVEL,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
        self.timeout = timeout
        self.max_workers = max_workers
        self.process_pool = ProcessPoolExecutor(max_workers=self.max_workers)
        self.nodejs_available = check_nodejs_available()

        self.scheduler = AsyncIOScheduler()
        # 每小时重启一次进程池 (原代码是每分钟)
        cron_expr = settings.POOL_RESTART_CRON
        self.logger.info(f"已设置进程池重启任务，cron表达式为：{cron_expr}")
        # 使用 cron 表达式添加任务
        self.scheduler.add_job(self._restart_pool, 'cron',
                               minute=cron_expr.split()[0],
                               hour=cron_expr.split()[1],
                               day=cron_expr.split()[2],
                               month=cron_expr.split()[3],
                               day_of_week=cron_expr.split()[4])
        # 添加内存检查任务
        # self.scheduler.add_job(self._check_and_restart, 'interval', minutes=5)
        self.scheduler.start()



    async def _restart_pool(self):
        """重启进程池"""
        try:
            self.logger.info("准备重启进程池...")
            old_pool = self.process_pool
            self.process_pool = ProcessPoolExecutor(max_workers=self.max_workers)
            # 关闭旧池
            # 使用 create_task 避免阻塞
            asyncio.create_task(self._shutdown(old_pool))
            self.logger.info("进程池已重启(切换完成)")
        except Exception as e:
            self.logger.error(f"重启进程池失败: {e}")

    async def _check_and_restart(self):
        """检查内存使用情况并决定是否重启"""
        try:
            process = psutil.Process(os.getpid())
            # rss: 实际物理内存使用
            memory_mb = process.memory_info().rss / 1024 / 1024

            if memory_mb > settings.MAX_MEMORY_THRESHOLD:
                self.logger.warning(
                    f"内存使用过高: {memory_mb:.2f}MB (阈值: {settings.MAX_MEMORY_THRESHOLD}MB), 触发进程池重启")
                await self._restart_pool()
            else:
                self.logger.debug(f"当前沙箱内存使用: {memory_mb:.2f}MB, 正常")
        except Exception as e:
            self.logger.error(f"内存检查失败: {e}")

    async def _shutdown(self, pool: ProcessPoolExecutor):
        """关闭进程池"""
        self.logger.info("正在关闭旧进程池...")
        # wait=True 会等待所有已提交但未完成的任务，但在 async context 中不推荐长时间阻塞
        # wait=False 立即返回，正在运行的任务继续，新任务被拒绝。
        # 这里使用 wait=True 确保旧池中的任务能完成，但由于它在一个 task 中，不会阻塞主循环
        await asyncio.to_thread(pool.shutdown, wait=True)
        self.logger.info("旧进程池已关闭。")

    async def execute(self, code: str, language: str = "python3") -> Dict[str, Any]:
        """
        执行代码的主入口点。
        - 移除外部 asyncio.wait_for。
        - 超时和进程终止由内部的 _run_code_with_subprocess_safe 函数负责。
        """
        self.logger.debug(f"开始执行{language}代码，代码长度：{len(code)}字符, 超时限制: {self.timeout}秒")
        try:
            loop = asyncio.get_event_loop()

            if language == "python3":
                executor_func = _run_python_code_in_process_safe
            elif language == "nodejs":
                if not self.nodejs_available:
                    return {
                        "success": False,
                        "output": "",
                        "error": "Node.js未安装或不可用"
                    }
                executor_func = _run_nodejs_code_in_process_safe
            else:
                return {
                    "success": False,
                    "output": "",
                    "error": f"不支持的语言: {language}"
                }

            # run_in_executor 负责等待同步的 executor_func 完成。
            # executor_func 内部已处理超时和进程终止。
            result = await loop.run_in_executor(
                self.process_pool,
                executor_func,
                code,
                self.timeout  # 将超时时间传递给执行函数
            )

            self.logger.debug(f"代码执行完成，结果：{result['success'] and '成功' or '失败'}")
            return result

        except Exception as e:
            # 捕获 ProcessPoolExecutor 内部抛出的异常或 run_in_executor 自身的异常
            self.logger.debug(f"执行过程中发生外部异常：{str(e)}", exc_info=True)
            return {
                "success": False,
                "output": "",
                "error": f"代码执行系统错误: {str(e)}"
            }


# --- 示例用法 (仅供测试) ---
async def main_test():
    print("--- 启动 CodeExecutor ---")
    # 设置一个短的超时时间，以便快速测试超时机制
    executor = CodeExecutor(timeout=5, max_workers=2)

    # 1. Python 成功执行
    python_code_ok = "print('Hello from Python'); a = 1 + 2; print(f'Result: {a}')"
    print("\n--- 测试 Python 成功 ---")
    result_py_ok = await executor.execute(python_code_ok, "python3")
    print(f"结果: {result_py_ok['success']}")
    print(f"输出:\n{result_py_ok['output']}")

    # 2. Python 超时执行 (强制终止)
    python_code_timeout = """
import time
print('Starting long task...')
time.sleep(10) # 超过 5 秒的限制
print('Task finished.')
"""
    print("\n--- 测试 Python 超时 (应被终止) ---")
    result_py_timeout = await executor.execute(python_code_timeout, "python3")
    print(f"结果: {result_py_timeout['success']}")
    print(f"输出:\n{result_py_timeout['output']}")
    print(f"错误:\n{result_py_timeout['error']}")

    # 3. Node.js 成功执行 (如果 Node.js 可用)
    if executor.nodejs_available:
        nodejs_code_ok = "console.log('Hello from Node.js'); let a = 1 + 2; console.log(`Result: ${a}`);"
        print("\n--- 测试 Node.js 成功 ---")
        result_js_ok = await executor.execute(nodejs_code_ok, "nodejs")
        print(f"结果: {result_js_ok['success']}")
        print(f"输出:\n{result_js_ok['output']}")

        # 4. Node.js 超时执行 (强制终止)
        nodejs_code_timeout = "console.log('Starting long task...'); while(true) {}"
        print("\n--- 测试 Node.js 超时 (应被终止) ---")
        result_js_timeout = await executor.execute(nodejs_code_timeout, "nodejs")
        print(f"结果: {result_js_timeout['success']}")
        print(f"输出:\n{result_js_timeout['output']}")
        print(f"错误:\n{result_js_timeout['error']}")
    else:
        print("\n--- Node.js 不可用，跳过测试 ---")

    # 简单等待，确保日志被刷新
    await asyncio.sleep(1)
    # 优雅关闭调度器
    executor.scheduler.shutdown()
    await executor._shutdown(executor.process_pool)


if __name__ == "__main__":
    # 启用 DEBUG 日志
    settings.LOG_LEVEL = logging.DEBUG
    # 运行测试
    try:
        asyncio.run(main_test())
    except KeyboardInterrupt:
        print("\n程序中断")
