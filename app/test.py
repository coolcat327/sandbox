import requests
import json
import time
import concurrent.futures
from config import settings

# 配置
BASE_URL = "http://localhost:8194"
API_KEY = settings.API_KEY  # 正确的API密钥
INVALID_API_KEY = "invalid-key"  # 错误的API密钥


def print_result(test_name: str, response: requests.Response):
    """打印测试结果"""
    print(f"\n{'=' * 50}")
    print(f"测试: {test_name}")
    print(f"状态码: {response.status_code}")
    try:
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    except:
        print(f"响应: {response.text}")
    print(f"{'=' * 50}")


def test_normal_execution():
    """测试正常执行"""
    url = f"{BASE_URL}/v1/sandbox/run"
    headers = {"X-Api-Key": API_KEY}
    data = {
        "language": "python3",
        "code": "print('Hello World')",
        "preload": "",
        "enable_network": False
    }

    response = requests.post(url, json=data, headers=headers)
    print_result("正常执行Python代码", response)
    return response


def test_invalid_api_key():
    """测试无效的API密钥"""
    url = f"{BASE_URL}/v1/sandbox/run"
    headers = {"X-Api-Key": INVALID_API_KEY}
    data = {
        "language": "python3",
        "code": "print('Hello World')",
        "preload": "",
        "enable_network": False
    }

    response = requests.post(url, json=data, headers=headers)
    print_result("使用无效的API密钥", response)
    return response


def test_missing_api_key():
    """测试缺少API密钥"""
    url = f"{BASE_URL}/v1/sandbox/run"
    data = {
        "language": "python3",
        "code": "print('Hello World')",
        "preload": "",
        "enable_network": False
    }

    response = requests.post(url, json=data)  # 没有headers
    print_result("缺少API密钥", response)
    return response


def test_unsupported_language():
    """测试不支持的语言"""
    url = f"{BASE_URL}/v1/sandbox/run"
    headers = {"X-Api-Key": API_KEY}
    data = {
        "language": "java",  # 不支持的语言
        "code": "System.out.println('Hello')",
        "preload": "",
        "enable_network": False
    }

    response = requests.post(url, json=data, headers=headers)
    print_result("使用不支持的编程语言", response)
    return response


def test_empty_code():
    """测试空代码"""
    url = f"{BASE_URL}/v1/sandbox/run"
    headers = {"X-Api-Key": API_KEY}
    data = {
        "language": "python3",
        "code": "",
        "preload": "",
        "enable_network": False
    }

    response = requests.post(url, json=data, headers=headers)
    print_result("发送空代码", response)
    return response


def test_syntax_error_code():
    """测试语法错误代码"""
    url = f"{BASE_URL}/v1/sandbox/run"
    headers = {"X-Api-Key": API_KEY}
    data = {
        "language": "python3",
        "code": "print('unclosed string",  # 语法错误
        "preload": "",
        "enable_network": False
    }

    response = requests.post(url, json=data, headers=headers)
    print_result("发送有语法错误的代码", response)
    return response


def test_runtime_error_code():
    """测试运行时错误代码"""
    url = f"{BASE_URL}/v1/sandbox/run"
    headers = {"X-Api-Key": API_KEY}
    data = {
        "language": "python3",
        "code": "x = 1/0",  # 除以零错误
        "preload": "",
        "enable_network": False
    }

    response = requests.post(url, json=data, headers=headers)
    print_result("发送有运行时错误的代码", response)
    return response


def test_timeout_code():
    """测试超时代码"""
    url = f"{BASE_URL}/v1/sandbox/run"
    headers = {"X-Api-Key": API_KEY}
    data = {
        "language": "python3",
        "code": "import time\ntime.sleep(700)",  # 超过600秒超时
        "preload": "",
        "enable_network": False
    }

    response = requests.post(url, json=data, headers=headers)
    print_result("发送会超时的代码", response)
    return response


def test_health_check():
    """测试健康检查接口"""
    url = f"{BASE_URL}/health"
    response = requests.get(url)
    print_result("健康检查接口", response)
    return response


def test_concurrent_requests():
    """测试并发请求"""

    def make_request(request_id: int):
        url = f"{BASE_URL}/v1/sandbox/run"
        headers = {"X-Api-Key": API_KEY}
        data = {
            "language": "python3",
            "code": f"print('Request {request_id}')\nimport time\ntime.sleep(5)",
            "preload": "",
            "enable_network": False
        }

        start_time = time.time()
        response = requests.post(url, json=data, headers=headers)
        end_time = time.time()

        return {
            "request_id": request_id,
            "status_code": response.status_code,
            "duration": end_time - start_time,
            "response": response.json() if response.status_code == 200 else None
        }

    print("\n开始并发测试...")
    # 需要调整线程数和并发请求数，确保比config里的多，才能压
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(make_request, i) for i in range(20)]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    print(f"\n并发测试结果:")
    for result in results:
        print(f"请求 {result['request_id']}: 状态码={result['status_code']}, "
              f"耗时={result['duration']:.2f}s")

    return results


def test_nodejs_execution():
    """测试Node.js执行"""
    url = f"{BASE_URL}/v1/sandbox/run"
    headers = {"X-Api-Key": API_KEY}
    data = {
        "language": "nodejs",
        "code": "console.log('Hello from Node.js')",
        "preload": "",
        "enable_network": False
    }

    response = requests.post(url, json=data, headers=headers)
    print_result("执行Node.js代码", response)
    return response


if __name__ == "__main__":
    print("沙箱API异常测试开始...\n")

    # 基础功能测试
    test_health_check()
    test_normal_execution()
    test_nodejs_execution()

    # 认证相关测试
    test_invalid_api_key()
    test_missing_api_key()

    # 参数验证测试
    test_unsupported_language()
    test_empty_code()

    # 代码执行异常测试
    test_syntax_error_code()
    test_runtime_error_code()

    # 性能相关测试（可选，因为可能需要等待较长时间）
    test_timeout_code()
    test_concurrent_requests()

    print("\n所有测试完成!")
