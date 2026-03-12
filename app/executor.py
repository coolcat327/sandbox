import asyncio
import sys
import tempfile
import os
import subprocess
import logging
from typing import Dict, Any
from config import settings
import signal

# 尝试导入 resource 模块，用于 Unix/Linux/Mac 下的硬资源限制
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False

HAS_SETSID = hasattr(os, 'setsid')

# --- 全局限制配置 ---
MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 1MB 输出限制
MAX_MEMORY_MB = getattr(settings, 'MAX_MEMORY_THRESHOLD', 128) # 默认 128MB 限制

async def _read_stream_with_limit(stream: asyncio.StreamReader, limit_bytes: int) -> str:
    """按块读取流，超过限制尺寸则抛出异常"""
    output = bytearray()
    while True:
        try:
            # 每次读取 4096 字节
            chunk = await stream.read(4096)
        except ValueError:
            break
            
        if not chunk:
            break
            
        output.extend(chunk)
        if len(output) > limit_bytes:
            raise BufferError("输出超限")
            
    return output.decode('utf-8', errors='replace')

def _set_process_limits():
    """
    在子进程执行前调用的钩子函数（preexec_fn）。
    用于设置进程组以及操作系统的硬性资源限制。
    """
    # 1. 设置进程组组长，防止子孙进程逃逸 (适用于 Unix 体系)
    os.setsid()
    
    # 2. 操作系统级别的资源限制
    if HAS_RESOURCE:
        # 限制进程最大可用内存 (RLIMIT_AS 在某些 macOS 较新版本下可能不生效，但 Linux 下非常有效)
        max_bytes = MAX_MEMORY_MB * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
        except ValueError:
            pass # 某些系统可能不允许修改此限制
            
        # CPU 时间限制通过外部 asyncio 软超时控制即可，若需硬限制亦可在此增加：
        # resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds, timeout_seconds))

async def _run_code_async_safe(
        interpreter: str, 
        code: str, 
        timeout: int
) -> Dict[str, Any]:
    """
    【通用安全执行协程】
    使用 asyncio 子进程管理，支持进程组击杀、流式截断读取以及系统级资源限制。
    """
    temp_file_path = None
    if 'python' in interpreter.lower() or interpreter == sys.executable:
        suffix = ".py"
    elif 'node' in interpreter.lower():
        suffix = ".js"
    else:
        return {"success": False, "output": "", "error": f"不支持的解释器 {interpreter}"}

    try:
        # 1. 创建临时文件来存储代码
        # 显式指定 dir="/tmp" 确保沙箱里的 sandbox_user 有权限写入
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, dir='/tmp', delete=False) as temp_file:
            temp_file.write(code)
            temp_file_path = temp_file.name

        # 2. 使用 asyncio.create_subprocess_exec 执行代码
        kwargs = {
            'stdout': asyncio.subprocess.PIPE,
            'stderr': asyncio.subprocess.PIPE,
            'close_fds': True,
        }
        
        # 只有存在 os.setsid 时才启用进程组隔离功能 (Unix/Mac 环境)
        if HAS_SETSID:
            kwargs['preexec_fn'] = _set_process_limits

        process = await asyncio.create_subprocess_exec(
            interpreter, temp_file_path,
            **kwargs
        )

        stdout, stderr = "", ""

        try:
            # 3. 异步并发读取 stdout 和 stderr，各自受 MAX_OUTPUT_SIZE 限制
            # 使用 asyncio.wait_for 进行软超时控制
            read_tasks = asyncio.gather(
                _read_stream_with_limit(process.stdout, MAX_OUTPUT_SIZE),
                _read_stream_with_limit(process.stderr, MAX_OUTPUT_SIZE)
            )
            
            # 等待读取任务以及进程结束，并施加超时时间
            # 我们通过 process.wait() 保证进程退出
            await asyncio.wait_for(
                asyncio.gather(read_tasks, process.wait()), 
                timeout=timeout
            )
            
            # 拆包结果
            stdout, stderr = read_tasks.result()

            if process.returncode == 0:
                return {"success": True, "output": stdout, "error": None}
            else:
                return {"success": False, "output": stdout, "error": stderr}

        except (asyncio.TimeoutError, BufferError) as e:
            # --- 核心防御：处理超时与内存溢出 ---
            if isinstance(e, asyncio.TimeoutError):
                error_msg = f"代码执行超时 (>{timeout}秒)。进程已被强制终止。"
            else:
                error_msg = f"运行时错误: {str(e)}（限制: {MAX_OUTPUT_SIZE / 1024 / 1024:.1f}MB）"
            
            if HAS_SETSID:
                # 击杀整个进程组（防止恶意代码启动后台孙进程）
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass # 进程组可能已经不存在
                    
            # 兼容处理并让 asyncio 的内部状态收到 kill 信号
            try:
                process.kill()
            except ProcessLookupError:
                pass
            
            # 必须调用 communicate 强制读完管道残余数据并使 asyncio 底层正常关闭 transport
            try:
                await asyncio.wait_for(process.communicate(), timeout=1.0)
            except Exception:
                pass
            
            return {"success": False, "output": "", "error": error_msg}

    except Exception as e:
        return {"success": False, "output": "", "error": f"系统执行异常: {str(e)}"}
        
    finally:
        # 4. 删除临时文件
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logging.error(f"无法删除临时文件 {temp_file_path}: {e}")

# --- 辅助函数 ---
def check_nodejs_available():
    """使用 shutil.which 比 subprocess.run 性能更好，且无阻塞危险"""
    import shutil
    return shutil.which('node') is not None


# --- 主执行器类 ---
class CodeExecutor:
    def __init__(self, timeout: int = 30, max_workers: int = 10):
        # 初始化日志
        logging.basicConfig(
            level=getattr(settings, 'LOG_LEVEL', logging.INFO),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
        self.timeout = timeout
        
        # 注意：使用 Asyncio 模型后，max_workers 概念被弱化。
        # 如果你想严格限制同时执行的并发数，可以使用 asyncio.Semaphore(max_workers)
        self.semaphore = asyncio.Semaphore(max_workers)
        
        self.nodejs_available = check_nodejs_available()

    async def execute(self, code: str, language: str = "python3") -> Dict[str, Any]:
        """执行的主入口，移除了 ProcessPoolExecutor"""
        self.logger.debug(f"开始执行{language}代码，代码长度：{len(code)}字符, 超时限制: {self.timeout}秒")
        
        if language == "python3":
            interpreter = sys.executable
        elif language == "nodejs":
            if not self.nodejs_available:
                return {"success": False, "output": "", "error": "Node.js未安装或不可用"}
            interpreter = "node"
        else:
            return {"success": False, "output": "", "error": f"不支持的语言: {language}"}

        # 使用信号量控制并发数量，防止大量任务瞬间压垮系统
        async with self.semaphore:
            result = await _run_code_async_safe(interpreter, code, self.timeout)
            
        self.logger.debug(f"代码执行完成，结果：{result['success'] and '成功' or '失败'}")
        return result


# --- 示例用法 (仅供测试) ---
async def main_test():
    print("--- 启动 CodeExecutor (Async) ---")
    executor = CodeExecutor(timeout=3, max_workers=5)

    # 测试正常输出
    python_code_ok = "print('Hello from Python'); a = 1 + 2; print(f'Result: {a}')"
    print("\n[测试 1] Python 正常执行")
    res1 = await executor.execute(python_code_ok, "python3")
    print(res1)

    # 测试死循环和超时 (重点：是否会因 OOM 崩溃，进程是否被杀)
    python_code_timeout = "import time\nprint('Start')\nwhile True: pass"
    print("\n[测试 2] Python 死循环超时 (应被终止)")
    res2 = await executor.execute(python_code_timeout, "python3")
    print(res2)

    # 测试输出撑爆内存 (防 OOM 测试)
    python_code_bomb = "while True: print('A' * 100000)"
    print("\n[测试 3] Python 疯狂输出爆破内存 (应触发输出超限)")
    res3 = await executor.execute(python_code_bomb, "python3")
    print(res3)

    # 测试进程逃逸
    python_code_escape = """
import subprocess, time
subprocess.Popen(["python", "-c", "import time; time.sleep(100)"])
while True: pass
    """
    print(f"\n[测试 4] Python 衍生子进程逃逸 (测试进程组是否全杀)")
    # 注意：运行后可以通过 pstree 或 ps -ef 检查是否残留 sleep 进程
    res4 = await executor.execute(python_code_escape, "python3")
    print(res4)

    if executor.nodejs_available:
        print("\n[测试 5] Node.js 正常执行")
        js_code_ok = "console.log('Hello from Node.js'); const a = 2 + 3; console.log(`Result: ${a}`);"
        res5 = await executor.execute(js_code_ok, "nodejs")
        print(res5)

        print("\n[测试 6] Node.js 死循环超时 (应被终止)")
        js_code_timeout = "console.log('Start Node.js'); while(true) {}"
        res6 = await executor.execute(js_code_timeout, "nodejs")
        print(res6)
    else:
        print("\n[测试 5/6] Node.js 未安装，跳过测试")

    # 给 asyncio 一点时间做底层 socket 的清理，防止结束时报错
    await asyncio.sleep(0.5)

if __name__ == "__main__":
    if hasattr(settings, 'LOG_LEVEL'):
        settings.LOG_LEVEL = logging.DEBUG
    try:
        asyncio.run(main_test())
    except KeyboardInterrupt:
        print("\n程序中断")
