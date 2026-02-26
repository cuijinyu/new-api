"""
Gemini 3.1 Flash Image Preview 文生图 API 调用示例

支持两种调用方式:
1. OpenAI 兼容 API: POST /v1/images/generations
2. Gemini 原生 API: POST /v1beta/models/{model}:generateContent

模型: gemini-3.1-flash-image-preview
"""

import os
import sys
import json
import base64
import requests
from datetime import datetime

BASE_URL = os.getenv("EZMODEL_BASE_URL", "https://www.ezmodel.cloud")
API_KEY = os.getenv("EZMODEL_API_KEY", "YOUR_API_KEY")
MODEL = "gemini-3.1-flash-image-preview"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def save_b64_image(b64_data, filename):
    """将 base64 图片数据保存到文件"""
    img_bytes = base64.b64decode(b64_data)
    with open(filename, "wb") as f:
        f.write(img_bytes)
    print(f"图片已保存: {filename} ({len(img_bytes)} bytes)")


def text_to_image_openai_api():
    """通过 OpenAI 兼容 API 进行文生图"""
    print("\n" + "=" * 60)
    print("方式一: OpenAI 兼容 API (/v1/images/generations)")
    print("=" * 60)

    url = f"{BASE_URL}/v1/images/generations"

    payload = {
        "model": MODEL,
        "prompt": "一只可爱的橘猫坐在窗台上，阳光洒在身上，温馨治愈的水彩画风格",
        "size": "1024x1024",
        "n": 1,
    }

    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")

    response = requests.post(url, headers=HEADERS, json=payload, timeout=600)

    print(f"响应状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("生成成功!")
        print(f"完整响应 (截断): {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")

        if "data" in result and len(result["data"]) > 0:
            item = result["data"][0]
            if item.get("b64_json"):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_b64_image(item["b64_json"], f"gemini31_openai_{ts}.png")
            elif item.get("url"):
                image_url = item["url"].replace("\\u0026", "&")
                print(f"图片 URL: {image_url}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def text_to_image_openai_api_landscape():
    """通过 OpenAI 兼容 API 生成横版图片"""
    print("\n" + "=" * 60)
    print("方式一 (横版): OpenAI 兼容 API - 横版风景图")
    print("=" * 60)

    url = f"{BASE_URL}/v1/images/generations"

    payload = {
        "model": MODEL,
        "prompt": "A breathtaking panoramic view of the Swiss Alps at sunset, "
        "golden light illuminating snow-capped peaks, a crystal clear lake "
        "in the foreground reflecting the mountains, photorealistic style",
        "size": "1536x1024",
        "n": 1,
    }

    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")

    response = requests.post(url, headers=HEADERS, json=payload, timeout=600)

    print(f"响应状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("生成成功!")
        if "data" in result and len(result["data"]) > 0:
            item = result["data"][0]
            if item.get("b64_json"):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_b64_image(item["b64_json"], f"gemini31_landscape_{ts}.png")
            elif item.get("url"):
                print(f"图片 URL: {item['url']}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def text_to_image_gemini_native_api():
    """通过 Gemini 原生 API 进行文生图"""
    print("\n" + "=" * 60)
    print("方式二: Gemini 原生 API (:generateContent)")
    print("=" * 60)

    url = f"{BASE_URL}/v1beta/models/{MODEL}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "Generate an image: a futuristic cyberpunk city at night, "
                        "neon lights reflecting on wet streets, flying cars in the sky, "
                        "highly detailed digital art"
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {
                "aspectRatio": "16:9",
            },
        },
    }

    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")

    response = requests.post(url, headers=HEADERS, json=payload, timeout=600)

    print(f"响应状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("生成成功!")

        candidates = result.get("candidates", [])
        for i, candidate in enumerate(candidates):
            parts = candidate.get("content", {}).get("parts", [])
            for j, part in enumerate(parts):
                if "text" in part:
                    print(f"文本响应: {part['text'][:200]}")
                if "inlineData" in part:
                    mime = part["inlineData"].get("mimeType", "")
                    data = part["inlineData"].get("data", "")
                    print(f"图片 [{i}-{j}]: mimeType={mime}, 数据长度={len(data)}")
                    if data:
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        save_b64_image(data, f"gemini31_native_{ts}_{i}_{j}.png")

        usage = result.get("usageMetadata", {})
        if usage:
            print(f"Token 用量: prompt={usage.get('promptTokenCount', 0)}, "
                  f"completion={usage.get('candidatesTokenCount', 0)}, "
                  f"total={usage.get('totalTokenCount', 0)}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def text_to_image_gemini_native_chinese():
    """通过 Gemini 原生 API 进行中文文生图"""
    print("\n" + "=" * 60)
    print("方式二 (中文): Gemini 原生 API - 中文提示词")
    print("=" * 60)

    url = f"{BASE_URL}/v1beta/models/{MODEL}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "请生成一张图片：中国风水墨山水画，远处有连绵的山峰，"
                        "近处有一叶扁舟在江面上，天空中有几只飞鸟，意境悠远"
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {
                "aspectRatio": "16:9",
            },
        },
    }

    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")

    response = requests.post(url, headers=HEADERS, json=payload, timeout=600)

    print(f"响应状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("生成成功!")

        candidates = result.get("candidates", [])
        for i, candidate in enumerate(candidates):
            parts = candidate.get("content", {}).get("parts", [])
            for j, part in enumerate(parts):
                if "text" in part:
                    print(f"文本响应: {part['text'][:200]}")
                if "inlineData" in part:
                    mime = part["inlineData"].get("mimeType", "")
                    data = part["inlineData"].get("data", "")
                    print(f"图片 [{i}-{j}]: mimeType={mime}, 数据长度={len(data)}")
                    if data:
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        save_b64_image(data, f"gemini31_chinese_{ts}_{i}_{j}.png")

        usage = result.get("usageMetadata", {})
        if usage:
            print(f"Token 用量: prompt={usage.get('promptTokenCount', 0)}, "
                  f"completion={usage.get('candidatesTokenCount', 0)}, "
                  f"total={usage.get('totalTokenCount', 0)}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def text_to_image_openai_sdk():
    """通过 OpenAI Python SDK 进行文生图"""
    print("\n" + "=" * 60)
    print("方式三: OpenAI Python SDK")
    print("=" * 60)

    try:
        from openai import OpenAI
    except ImportError:
        print("未安装 openai 库，跳过此测试")
        print("安装方式: pip install openai")
        return None

    client = OpenAI(
        api_key=API_KEY,
        base_url=f"{BASE_URL}/v1",
    )

    print(f"模型: {MODEL}")
    print("提示词: A cute robot cat sitting on a desk, digital art style")

    try:
        response = client.images.generate(
            model=MODEL,
            prompt="A cute robot cat sitting on a desk surrounded by tiny plants, "
            "warm lighting, cozy atmosphere, digital art illustration style",
            size="1024x1024",
            n=1,
        )

        print("生成成功!")
        for i, img in enumerate(response.data):
            if img.b64_json:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_b64_image(img.b64_json, f"gemini31_sdk_{ts}_{i}.png")
            elif img.url:
                print(f"图片 {i} URL: {img.url}")
            if img.revised_prompt:
                print(f"优化后提示词: {img.revised_prompt}")
        return response
    except Exception as e:
        print(f"请求失败: {e}")
        return None


if __name__ == "__main__":
    print("=" * 60)
    print(f"Gemini 3.1 Flash Image Preview 文生图测试")
    print(f"模型: {MODEL}")
    print(f"API 地址: {BASE_URL}")
    print("=" * 60)

    if API_KEY == "YOUR_API_KEY":
        print("\n⚠️  请设置环境变量 EZMODEL_API_KEY")
        print("示例: export EZMODEL_API_KEY=sk-your-api-key")
        sys.exit(1)

    results = {}

    tests = [
        ("openai_api", text_to_image_openai_api),
        ("openai_landscape", text_to_image_openai_api_landscape),
        ("native_api", text_to_image_gemini_native_api),
        ("native_chinese", text_to_image_gemini_native_chinese),
        ("openai_sdk", text_to_image_openai_sdk),
    ]

    for name, func in tests:
        try:
            results[name] = func()
        except requests.exceptions.Timeout:
            print(f"\n请求超时 (120s)，跳过")
            results[name] = None
        except Exception as e:
            print(f"\n异常: {type(e).__name__}: {e}")
            results[name] = None

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    labels = {
        "openai_api": "OpenAI 兼容 API (基础)",
        "openai_landscape": "OpenAI 兼容 API (横版)",
        "native_api": "Gemini 原生 API (英文)",
        "native_chinese": "Gemini 原生 API (中文)",
        "openai_sdk": "OpenAI Python SDK",
    }
    for key, result in results.items():
        status = "成功" if result else "失败"
        print(f"  {labels[key]}: {status}")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
