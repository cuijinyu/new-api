"""
豆包 Doubao Seedream 文生图 API 调用示例

支持的模型:
- doubao-seedream-4-5-251128 (最新版本)
- doubao-seedream-4-0-250828
- doubao-seedream-3-0-t2i-250415

API 文档参考: https://www.volcengine.com/docs/82379/1824718
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


def text_to_image_basic():
    """基础文生图示例"""
    print("\n=== 基础文生图示例 ===")
    
    url = f"{BASE_URL}/v1/images/generations"
    
    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": "一只可爱的橘猫坐在窗台上，阳光洒在身上，温馨治愈风格",
        "size": "1024x1024",
        "n": 1
    }
    
    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    response = requests.post(url, headers=HEADERS, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"生成成功!")
        if "data" in result and len(result["data"]) > 0:
            image_url = result["data"][0].get("url", "")
            # 处理 URL 中的转义字符
            image_url = image_url.replace("\\u0026", "&")
            print(f"图片 URL: {image_url}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def text_to_image_advanced():
    """高级文生图示例 - 使用更多参数"""
    print("\n=== 高级文生图示例 ===")
    
    url = f"{BASE_URL}/v1/images/generations"
    
    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": "星际穿越，巨大的黑洞，复古列车穿越星空，电影大片风格，史诗级画面",
        "size": "2048x2048",  # 高分辨率
        "n": 1,
        "seed": -1  # -1 表示随机种子
    }
    
    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    response = requests.post(url, headers=HEADERS, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"生成成功!")
        if "data" in result and len(result["data"]) > 0:
            image_url = result["data"][0].get("url", "")
            image_url = image_url.replace("\\u0026", "&")
            print(f"图片 URL: {image_url}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def text_to_image_portrait():
    """人像风格文生图示例"""
    print("\n=== 人像风格文生图示例 ===")
    
    url = f"{BASE_URL}/v1/images/generations"
    
    # 竖版尺寸适合人像
    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": "一位年轻女性，穿着白色连衣裙，站在樱花树下，微风吹过，花瓣飘落，日系清新风格，柔和光线",
        "size": "1024x1536",  # 竖版 2:3 比例
        "n": 1
    }
    
    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    response = requests.post(url, headers=HEADERS, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"生成成功!")
        if "data" in result and len(result["data"]) > 0:
            image_url = result["data"][0].get("url", "")
            image_url = image_url.replace("\\u0026", "&")
            print(f"图片 URL: {image_url}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def text_to_image_landscape():
    """风景横版文生图示例"""
    print("\n=== 风景横版文生图示例 ===")
    
    url = f"{BASE_URL}/v1/images/generations"
    
    # 横版尺寸适合风景
    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": "壮丽的山川风景，云雾缭绕，日出时分，金色阳光洒在山峰上，中国水墨画风格",
        "size": "1536x1024",  # 横版 3:2 比例
        "n": 1
    }
    
    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    response = requests.post(url, headers=HEADERS, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"生成成功!")
        if "data" in result and len(result["data"]) > 0:
            image_url = result["data"][0].get("url", "")
            image_url = image_url.replace("\\u0026", "&")
            print(f"图片 URL: {image_url}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def text_to_image_with_negative_prompt():
    """使用负面提示词的文生图示例"""
    print("\n=== 使用负面提示词的文生图示例 ===")
    
    url = f"{BASE_URL}/v1/images/generations"
    
    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": "高质量产品摄影，一杯咖啡，拿铁艺术，木质桌面，柔和自然光，商业摄影风格",
        "negative_prompt": "模糊, 低质量, 变形, 水印, 文字",  # 负面提示词
        "size": "1024x1024",
        "n": 1
    }
    
    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    response = requests.post(url, headers=HEADERS, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"生成成功!")
        if "data" in result and len(result["data"]) > 0:
            image_url = result["data"][0].get("url", "")
            image_url = image_url.replace("\\u0026", "&")
            print(f"图片 URL: {image_url}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def batch_generate_images():
    """批量生成多张图片示例"""
    print("\n=== 批量生成多张图片示例 ===")
    
    url = f"{BASE_URL}/v1/images/generations"
    
    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": "可爱的卡通小动物，圆润的造型，明亮的色彩，儿童插画风格",
        "size": "1024x1024",
        "n": 2  # 生成 2 张图片
    }
    
    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    response = requests.post(url, headers=HEADERS, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"生成成功!")
        if "data" in result:
            for i, item in enumerate(result["data"]):
                image_url = item.get("url", "")
                image_url = image_url.replace("\\u0026", "&")
                print(f"图片 {i + 1} URL: {image_url}")
        return result
    else:
        print(f"请求失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None


def test_model(model_name, prompt="一只可爱的橘猫坐在窗台上，阳光洒在身上，温馨治愈风格", size="1024x1024"):
    """测试指定模型"""
    print(f"\n=== 测试模型: {model_name} ===")
    
    url = f"{BASE_URL}/v1/images/generations"
    
    payload = {
        "model": model_name,
        "prompt": prompt,
        "size": size,
        "n": 1
    }
    
    print(f"请求 URL: {url}")
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    response = requests.post(url, headers=HEADERS, json=payload)
    
    print(f"响应状态码: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"生成成功!")
        print(f"完整响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
        if "data" in result and len(result["data"]) > 0:
            image_url = result["data"][0].get("url", "")
            image_url = image_url.replace("\\u0026", "&")
            print(f"图片 URL: {image_url}")
        return result
    else:
        print(f"请求失败!")
        print(f"错误信息: {response.text}")
        return None


def test_both_models():
    """测试 seedream-4-5 和 seedream-4-0 两个模型"""
    print("\n" + "=" * 60)
    print("开始测试 Seedream 4.5 和 4.0 两个模型")
    print("=" * 60)
    
    # 注意: seedream-4-5 要求图片尺寸至少 3686400 像素 (约 1920x1920)
    # 所以 4.5 使用 2048x2048，4.0 可以使用 1024x1024
    models_config = [
        {"model": "seedream-4-5-251128", "size": "2048x2048"},  # 4.5 需要更大尺寸
        {"model": "seedream-4-0-250828", "size": "1024x1024"},  # 4.0 支持较小尺寸
    ]
    
    prompt = "一只可爱的橘猫坐在窗台上，阳光洒在身上，温馨治愈风格"
    
    results = {}
    for config in models_config:
        print(f"\n{'=' * 40}")
        result = test_model(config["model"], prompt, config["size"])
        results[config["model"]] = result
        print(f"{'=' * 40}")
    
    # 打印测试结果汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for model, result in results.items():
        status = "成功 ✓" if result else "失败 ✗"
        print(f"  {model}: {status}")
    
    return results


def print_supported_sizes():
    """打印支持的图片尺寸"""
    print("\n=== 豆包 Seedream 支持的图片尺寸 ===")
    print("""
Seedream 4.0/4.5 推荐尺寸:
┌─────────────┬─────────────────┐
│   比例      │      尺寸       │
├─────────────┼─────────────────┤
│    1:1      │   2048x2048     │
│    1:1      │   1024x1024     │
│    4:3      │   2304x1728     │
│    3:4      │   1728x2304     │
│   16:9      │   2560x1440     │
│   9:16      │   1440x2560     │
│    3:2      │   1536x1024     │
│    2:3      │   1024x1536     │
└─────────────┴─────────────────┘

Seedream 3.0 推荐尺寸:
┌─────────────┬─────────────────┐
│   比例      │      尺寸       │
├─────────────┼─────────────────┤
│    1:1      │   1024x1024     │
│    4:3      │   1152x896      │
│    3:4      │   896x1152      │
│   16:9      │   1280x720      │
│   9:16      │   720x1280      │
└─────────────┴─────────────────┘
""")


def print_available_models():
    """打印可用的模型列表"""
    print("\n=== 豆包 Seedream 可用模型 ===")
    print("""
┌────────────────────────────────┬─────────────────────────────────────┐
│           模型名称              │              说明                   │
├────────────────────────────────┼─────────────────────────────────────┤
│ doubao-seedream-4-5-251128     │ 最新版本，效果最佳                   │
│ doubao-seedream-4-0-250828     │ 稳定版本，性价比高                   │
│ doubao-seedream-3-0-t2i-250415 │ 基础版本                            │
└────────────────────────────────┴─────────────────────────────────────┘
""")


if __name__ == "__main__":
    print("=" * 60)
    print("豆包 Doubao Seedream 文生图 API 调用示例")
    print("=" * 60)
    
    # 打印可用模型和尺寸信息
    print_available_models()
    print_supported_sizes()
    
    # 检查 API Key
    if API_KEY == "YOUR_API_KEY":
        print("\n⚠️  警告: 请设置环境变量 EZMODEL_API_KEY 或在代码中替换 API_KEY")
        print("示例: export EZMODEL_API_KEY=sk-your-api-key")
        exit(1)
    
    # 运行示例
    print("\n开始运行文生图示例...")
    
    # 测试两个模型
    test_both_models()
    
    # 其他示例（取消注释可运行）
    # text_to_image_basic()
    # text_to_image_advanced()
    # text_to_image_portrait()
    # text_to_image_landscape()
    # text_to_image_with_negative_prompt()
    # batch_generate_images()
    
    print("\n" + "=" * 60)
    print("示例运行完成!")
    print("=" * 60)
