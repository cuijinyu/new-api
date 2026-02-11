"""
Vidu 视频生成完整测试脚本

支持 5 种生成模式:
  1. text2video          - 文生视频 (无图片, 16:9 720p)
  2. img2video           - 图生视频 (1 张图片)
  3. start-end           - 首尾帧生视频 (2 张图片)
  4. reference           - 参考图生视频 (3+ 张图片, 仅 viduq2)
  5. text2video-vertical - 文生视频 竖屏 (无图片, 9:16 1080p)

用法:
  python test_vidu.py                    # 运行所有测试
  python test_vidu.py text2video         # 仅测试文生视频
  python test_vidu.py img2video          # 仅测试图生视频
  python test_vidu.py start-end          # 仅测试首尾帧生视频
  python test_vidu.py reference          # 仅测试参考图生视频
  python test_vidu.py text2video-vertical # 仅测试竖屏文生视频

环境变量:
  EZMODEL_API_KEY  - API Key (必须设置)
  EZMODEL_BASE_URL - 基础 URL (默认 https://www.ezmodel.cloud)
"""

import requests
import time
import sys
import os
import json

# ============================
# 配置
# ============================

BASE_URL = os.getenv("EZMODEL_BASE_URL", "https://www.ezmodel.cloud")
API_KEY = os.getenv("EZMODEL_API_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# 示例图片 URL（使用 picsum.photos 稳定公开图片服务，固定 ID 保证每次返回相同图片）
# picsum.photos/id/{id}/{width}/{height} 会返回指定尺寸的 JPEG 图片，URL 稳定可靠
SAMPLE_IMAGES = [
    # id=1005: 人物肖像（男性侧脸，黑白风格）
    "https://picsum.photos/id/1005/1024/1024",
    # id=1015: 航拍自然风景（河流穿越森林）
    "https://picsum.photos/id/1015/1024/1024",
    # id=1039: 瀑布森林风景（绿色森林环绕瀑布）
    "https://picsum.photos/id/1039/1024/1024",
]

# 轮询配置
POLL_INTERVAL = 10  # 每次轮询间隔（秒）
MAX_POLL_RETRIES = 60  # 最大轮询次数（总等待 ~10 分钟）

# ============================
# 测试用例定义
# ============================

TEST_CASES = {
    "text2video": {
        "name": "文生视频 (Text to Video)",
        "description": "无图片输入，纯文本生成视频",
        "data": {
            "model": "viduq2",
            "prompt": "In an ultra-realistic fashion photography style featuring light blue and pale amber tones, "
                      "an astronaut in a spacesuit walks through the fog. The background consists of enchanting "
                      "white and golden lights, creating a minimalist still life and an impressive panoramic scene.",
            "size": "720p",       # resolution: viduq2 可选 540p, 720p, 1080p
            "duration": 5,
            "metadata": {
                "aspect_ratio": "16:9",  # 宽高比: 16:9 / 9:16 / 3:4 / 4:3 / 1:1 (3:4 & 4:3 仅 q2/q3)
            },
        },
    },
    "img2video": {
        "name": "图生视频 (Image to Video)",
        "description": "1 张图片输入，图片驱动生成视频",
        "data": {
            "model": "viduq2-pro",  # 图生视频不支持 viduq2 基础模型，需要带 pro/turbo 后缀
            "prompt": "The man in the portrait slowly turns his head towards the camera, "
                      "a subtle smile forming on his face, with soft cinematic lighting.",
            "images": SAMPLE_IMAGES[:1],  # 1 张图片（人物肖像）
            "size": "720p",
            "duration": 5,
            "metadata": {
                "aspect_ratio": "16:9",
            },
        },
    },
    "start-end": {
        "name": "首尾帧生视频 (Start-End Frame to Video)",
        "description": "2 张图片输入，分别作为首帧和尾帧",
        "data": {
            "model": "viduq2-pro",  # 首尾帧生视频不支持 viduq2 基础模型
            "prompt": "A cinematic aerial shot smoothly transitions from a portrait scene "
                      "to a breathtaking river flowing through a lush green forest.",
            "images": SAMPLE_IMAGES[:2],  # 2 张图片（人物肖像 → 航拍河流）
            "size": "720p",
            "duration": 5,
            "metadata": {
                "aspect_ratio": "16:9",
            },
        },
    },
    "reference": {
        "name": "参考图生视频 (Reference Images to Video)",
        "description": "3+ 张图片输入，参考图生成视频（仅支持 viduq2 基础模型）",
        "data": {
            "model": "viduq2",  # 参考图生视频仅支持 viduq2，不能带 pro/turbo 后缀
            "prompt": "A cinematic nature documentary scene: a river winds through a dense forest "
                      "towards a majestic waterfall, with mist rising and sunlight filtering through the trees.",
            "images": SAMPLE_IMAGES[:3],  # 3 张图片（人物 + 河流 + 瀑布）
            "size": "720p",
            "duration": 5,
            "metadata": {
                "aspect_ratio": "16:9",
            },
        },
    },
    "text2video-vertical": {
        "name": "文生视频 竖屏 1080p (Text to Video 9:16)",
        "description": "无图片输入，竖屏 9:16 + 1080p 分辨率生成视频",
        "data": {
            "model": "viduq2",
            "prompt": "A beautiful waterfall cascading down mossy rocks in a tropical forest, "
                      "cinematic vertical shot with mist and sunlight rays.",
            "size": "1080p",
            "duration": 5,
            "metadata": {
                "aspect_ratio": "9:16",
            },
        },
    },
}


# ============================
# 核心函数
# ============================

def submit_task(test_key):
    """提交视频生成任务"""
    case = TEST_CASES[test_key]
    url = f"{BASE_URL}/v1/video/generations"

    print(f"  请求 URL: {url}")
    print(f"  请求参数: {json.dumps(case['data'], indent=4, ensure_ascii=False)}")

    response = requests.post(url, headers=HEADERS, json=case["data"])

    if response.status_code != 200:
        print(f"  提交失败 (HTTP {response.status_code}): {response.text}")
        return None

    res_json = response.json()
    print(f"  提交响应: {json.dumps(res_json, indent=4, ensure_ascii=False)}")

    # 兼容不同返回格式: task_id 或 id
    task_id = res_json.get("task_id") or res_json.get("id")
    if not task_id:
        print(f"  未能获取 task_id: {res_json}")
        return None

    return task_id


def poll_task(task_id):
    """轮询任务状态，直到完成或失败

    实际返回格式:
    {
        "code": "success",
        "data": {
            "task_id": "...",
            "status": "IN_PROGRESS" / "SUCCESS" / "FAILURE",
            "progress": "30%",
            "fail_reason": "...",
            "data": {
                "state": "processing" / "success" / "failed",
                "creations": [{"url": "..."}],
                ...
            }
        }
    }
    """
    url = f"{BASE_URL}/v1/video/generations/{task_id}"
    print(f"  查询 URL: {url}")

    for i in range(MAX_POLL_RETRIES):
        time.sleep(POLL_INTERVAL)

        try:
            response = requests.get(url, headers=HEADERS)
        except Exception as e:
            print(f"  轮询 #{i + 1}: 请求异常 - {e}")
            continue

        if response.status_code != 200:
            print(f"  轮询 #{i + 1}: HTTP {response.status_code} - {response.text}")
            continue

        res_json = response.json()

        # 解析嵌套结构: data.status / data.progress / data.data.creations
        task_data = res_json.get("data", {})
        status = task_data.get("status", "unknown")
        progress = task_data.get("progress", "0%")

        print(f"  轮询 #{i + 1}: status={status}, progress={progress}")

        if status == "SUCCESS":
            # 从 data.data.creations 中提取视频 URL
            inner_data = task_data.get("data", {})
            creations = inner_data.get("creations", [])
            if creations and creations[0].get("url"):
                print(f"  任务成功!")
                print(f"  视频 URL: {creations[0]['url']}")
            else:
                # 也可能在 fail_reason 字段中（当前实现会把 url 放在这里）
                video_url = task_data.get("fail_reason", "")
                if video_url.startswith("http"):
                    print(f"  任务成功!")
                    print(f"  视频 URL: {video_url}")
                else:
                    print(f"  任务成功! (未提取到视频 URL)")
                    print(f"  完整响应: {json.dumps(res_json, indent=4, ensure_ascii=False)}")
            return True

        elif status == "FAILURE":
            fail_reason = task_data.get("fail_reason", "")
            inner_data = task_data.get("data", {})
            err_code = inner_data.get("err_code", "")
            print(f"  任务失败!")
            print(f"  失败原因: {fail_reason or err_code or '未知'}")
            return False

    print(f"  超时: 任务在 {MAX_POLL_RETRIES * POLL_INTERVAL} 秒内未完成。")
    return False


def run_test(test_key):
    """运行单个测试用例的完整流程"""
    case = TEST_CASES[test_key]

    print(f"\n{'=' * 60}")
    print(f"测试: {case['name']}")
    print(f"说明: {case['description']}")
    print(f"{'=' * 60}")

    # 步骤 1: 提交任务
    print(f"\n[步骤 1] 提交视频生成任务...")
    task_id = submit_task(test_key)
    if not task_id:
        print(f"\n结果: 提交失败，跳过此测试。")
        return False

    print(f"\n  Task ID: {task_id}")

    # 步骤 2: 轮询状态
    print(f"\n[步骤 2] 轮询任务状态 (间隔 {POLL_INTERVAL}s, 最多 {MAX_POLL_RETRIES} 次)...")
    success = poll_task(task_id)

    print(f"\n结果: {'通过' if success else '失败'}")
    return success


# ============================
# 主入口
# ============================

def main():
    if not API_KEY:
        print("错误: 请设置环境变量 EZMODEL_API_KEY")
        print("  export EZMODEL_API_KEY=sk-your-api-key")
        sys.exit(1)

    print(f"Vidu 视频生成测试脚本")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key:  {API_KEY[:8]}...{API_KEY[-4:]}" if len(API_KEY) > 12 else f"API Key: {API_KEY}")

    # 解析命令行参数，确定要运行的测试
    args = sys.argv[1:]
    if args:
        test_keys = []
        for arg in args:
            if arg in TEST_CASES:
                test_keys.append(arg)
            else:
                print(f"未知的测试模式: '{arg}'")
                print(f"可选模式: {', '.join(TEST_CASES.keys())}")
                sys.exit(1)
    else:
        test_keys = list(TEST_CASES.keys())

    print(f"将运行 {len(test_keys)} 个测试: {', '.join(test_keys)}")

    # 逐个运行测试
    results = {}
    for key in test_keys:
        results[key] = run_test(key)
        if key != test_keys[-1]:
            print(f"\n等待 3 秒后开始下一个测试...")
            time.sleep(3)

    # 汇总结果
    print(f"\n{'=' * 60}")
    print(f"测试汇总")
    print(f"{'=' * 60}")
    for key, success in results.items():
        case = TEST_CASES[key]
        status = "通过" if success else "失败"
        print(f"  [{status}] {case['name']}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n总计: {passed}/{total} 通过")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
