"""
智谱 x 文生文 API 调用示例

模型: x

API 兼容 OpenAI Chat Completions 格式
"""

import os
import json
import requests

# 配置信息
BASE_URL = "https://www.ezmodel.cloud"  # 替换为你的 API 地址
API_KEY = os.getenv("EZMODEL_API_KEY", "YOUR_API_KEY")  # 请在环境变量中设置 EZMODEL_API_KEY

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


def test_chat_model(model_name, prompt="你好，请介绍一下你自己", stream=False):
    """测试指定的聊天模型"""
    print(f"\n=== 测试模型: {model_name} ===")

    url = f"{BASE_URL}/v1/chat/completions"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": stream,
        "max_tokens": 1024
    }

    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")

    if stream:
        # 流式响应
        response = requests.post(url, headers=HEADERS, json=payload, stream=True)
        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            print("流式响应内容:")
            full_content = ""
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        data_str = line_str[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    print(content, end="", flush=True)
                                    full_content += content
                        except json.JSONDecodeError:
                            pass
            print("\n")
            return {"content": full_content}
        else:
            print(f"请求失败!")
            print(f"错误信息: {response.text}")
            return None
    else:
        # 非流式响应
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"生成成功!")
            print(f"完整响应: {json.dumps(result, ensure_ascii=False, indent=2)}")

            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0].get("message", {}).get("content", "")
                print(f"\n回复内容:\n{content}")

            # 打印 token 使用情况
            if "usage" in result:
                usage = result["usage"]
                print(f"\nToken 使用:")
                print(f"  - prompt_tokens: {usage.get('prompt_tokens', 'N/A')}")
                print(f"  - completion_tokens: {usage.get('completion_tokens', 'N/A')}")
                print(f"  - total_tokens: {usage.get('total_tokens', 'N/A')}")

            return result
        else:
            print(f"请求失败!")
            print(f"错误信息: {response.text}")
            return None


def test_basic_chat():
    """测试基本聊天（非流式）"""
    print("\n" + "=" * 60)
    print("测试 x 基本聊天")
    print("=" * 60)

    prompt = "你好，请用一句话介绍一下你自己"
    return test_chat_model("x", prompt, stream=False)


def test_stream_mode():
    """测试流式输出模式"""
    print("\n" + "=" * 60)
    print("测试 x 流式输出模式")
    print("=" * 60)

    prompt = "请写一首关于春天的短诗"
    return test_chat_model("x", prompt, stream=True)


def test_system_prompt():
    """测试系统提示词"""
    print("\n" + "=" * 60)
    print("测试 x 系统提示词")
    print("=" * 60)

    model = "x"
    url = f"{BASE_URL}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一位古代诗人，请用文言文回答问题。"},
            {"role": "user", "content": "今天天气如何？"}
        ],
        "max_tokens": 1024
    }

    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    response = requests.post(url, headers=HEADERS, json=payload)
    print(f"响应状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        print(f"回复内容:\n{content}")
        return result
    else:
        print(f"请求失败: {response.text}")
        return None


def test_multi_turn_conversation():
    """测试多轮对话"""
    print("\n" + "=" * 60)
    print("测试 x 多轮对话")
    print("=" * 60)

    model = "x"
    url = f"{BASE_URL}/v1/chat/completions"

    messages = [
        {"role": "user", "content": "我想学习机器学习，应该从哪里开始？"},
    ]

    print(f"=== 第一轮对话 ===")
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 512
    }

    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    response = requests.post(url, headers=HEADERS, json=payload)

    if response.status_code == 200:
        result = response.json()
        assistant_reply = result["choices"][0]["message"]["content"]
        print(f"助手回复: {assistant_reply[:200]}...")

        # 打印 token 使用情况
        if "usage" in result:
            usage = result["usage"]
            print(f"Token 使用: prompt={usage.get('prompt_tokens', 'N/A')}, "
                  f"completion={usage.get('completion_tokens', 'N/A')}, "
                  f"total={usage.get('total_tokens', 'N/A')}")

        # 添加助手回复到消息历史
        messages.append({"role": "assistant", "content": assistant_reply})

        # 第二轮对话
        print(f"\n=== 第二轮对话 ===")
        messages.append({"role": "user", "content": "请详细展开第一个建议。"})

        payload["messages"] = messages
        print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")

        response2 = requests.post(url, headers=HEADERS, json=payload)
        if response2.status_code == 200:
            result2 = response2.json()
            assistant_reply2 = result2["choices"][0]["message"]["content"]
            print(f"助手回复: {assistant_reply2[:200]}...")

            if "usage" in result2:
                usage2 = result2["usage"]
                print(f"Token 使用: prompt={usage2.get('prompt_tokens', 'N/A')}, "
                      f"completion={usage2.get('completion_tokens', 'N/A')}, "
                      f"total={usage2.get('total_tokens', 'N/A')}")
            return result2
    else:
        print(f"请求失败: {response.text}")

    return None


def test_temperature():
    """测试温度参数对比"""
    print("\n" + "=" * 60)
    print("测试 x 温度参数对比")
    print("=" * 60)

    model = "x"
    url = f"{BASE_URL}/v1/chat/completions"
    prompt = "用一个词描述大海。"

    for temp in [0.0, 1.0]:
        print(f"\n--- 温度: {temp} ---")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 50,
            "temperature": temp
        }

        response = requests.post(url, headers=HEADERS, json=payload)
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            print(f"回复: {content}")
        else:
            print(f"请求失败: {response.text}")


if __name__ == "__main__":
    print("=" * 60)
    print("智谱 x 文生文 API 调用示例")
    print("=" * 60)

    # 检查 API Key
    if API_KEY == "YOUR_API_KEY":
        print("\n[WARN] 请设置环境变量 EZMODEL_API_KEY 或在代码中替换 API_KEY")
        print("示例: export EZMODEL_API_KEY=sk-your-api-key")
        exit(1)

    # 基本聊天测试
    test_basic_chat()

    # 流式输出测试
    test_stream_mode()

    # 系统提示词测试
    test_system_prompt()

    # 多轮对话测试
    test_multi_turn_conversation()

    # 温度参数测试
    test_temperature()

    print("\n" + "=" * 60)
    print("示例运行完成!")
    print("=" * 60)
