"""
Kling V3 新特性测试脚本
覆盖：文生视频、图生视频、多镜头叙事(multi_prompt)、视频编辑(refer_type=base)、原生音频(sound)
"""

import requests
import time
import os
import sys
import json
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_URL = os.getenv("EZMODEL_BASE_URL", "https://www.ezmodel.cloud")
API_KEY = os.getenv("EZMODEL_API_KEY", "YOUR_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

OMNI_URL = f"{BASE_URL}/kling/v1/videos/omni-video"
STATUS_URL = f"{BASE_URL}/v1/video/generations"


def submit_task(payload, label=""):
    print(f"\n{'='*60}")
    print(f"[提交] {label}")
    print(f"  Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    resp = requests.post(OMNI_URL, headers=HEADERS, json=payload)
    if resp.status_code != 200:
        print(f"  ❌ 提交失败 (HTTP {resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    task_id = data.get("id")
    print(f"  ✅ 提交成功, Task ID: {task_id}")
    return task_id


def poll_task(task_id, timeout=300, interval=10):
    """轮询任务状态，返回视频 URL 或 None"""
    url = f"{STATUS_URL}/{task_id}"
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(url, headers=HEADERS)
            if resp.status_code != 200:
                print(f"  查询失败 (HTTP {resp.status_code}): {resp.text}")
                return None
            task_data = resp.json().get("data", {})
            status = task_data.get("status")
            print(f"  状态: {status} (已等待 {int(time.time()-start)}s)")
            if status == "SUCCESS":
                videos = (
                    task_data.get("data", {})
                    .get("data", {})
                    .get("task_result", {})
                    .get("videos", [])
                )
                if videos:
                    video_url = videos[0].get("url")
                    print(f"  🎬 视频URL: {video_url[:120]}...")
                    return video_url
                print("  ⚠️ 成功但未找到视频URL")
                return None
            elif status == "FAILED":
                print(f"  ❌ 任务失败: {json.dumps(task_data, ensure_ascii=False)}")
                return None
        except Exception as e:
            print(f"  异常: {e}")
            return None
        time.sleep(interval)
    print(f"  ⏰ 超时 ({timeout}s)")
    return None


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_text2video_std():
    """V3 文生视频 - Std 模式, 10s, 含音频"""
    task_id = submit_task(
        {
            "model": "kling-v3",
            "prompt": "一只橘猫在阳光下的花园里追蝴蝶，电影质感，浅景深",
            "mode": "std",
            "duration": "10",
            "aspect_ratio": "16:9",
            "sound": "on",
        },
        label="V3 文生视频 (Std, 10s, sound=on)",
    )
    return task_id


def test_text2video_pro_15s():
    """V3 文生视频 - Pro 模式, 15s (V3 新增上限)"""
    task_id = submit_task(
        {
            "model": "kling-v3",
            "prompt": "城市夜景延时摄影，车流光轨从繁忙到寂静，4K电影感",
            "mode": "pro",
            "duration": "15",
            "aspect_ratio": "16:9",
        },
        label="V3 文生视频 (Pro, 15s)",
    )
    return task_id


def test_image2video_first_frame():
    """V3 图生视频 - 首帧模式"""
    task_id = submit_task(
        {
            "model": "kling-v3",
            "prompt": "人物缓缓转头微笑，头发随风飘动",
            "image_list": [
                {
                    "image_url": "https://p2-kling.klingai.com/bs2/upload-ylab-stunt/special-effect/output/HB1_PROD_ai_web_299690834263822_-4012665849171309178/-7957711300647229468/tempwyvwb.png",
                    "type": "first_frame",
                }
            ],
            "duration": "5",
            "mode": "pro",
        },
        label="V3 图生视频 (首帧, Pro, 5s)",
    )
    return task_id


def test_multi_shot():
    """V3 多镜头叙事 (multi_prompt) - 3个分镜, 总计13s"""
    task_id = submit_task(
        {
            "model": "kling-v3",
            "multi_prompt": [
                {
                    "prompt": "一个女孩推开咖啡店的玻璃门走进去，镜头跟随，暖色调",
                    "duration": "4",
                },
                {
                    "prompt": "女孩坐在窗边，打开笔记本电脑开始打字，特写镜头",
                    "duration": "4",
                },
                {
                    "prompt": "窗外下起了小雨，女孩端起咖啡微笑着看向窗外，中景",
                    "duration": "5",
                },
            ],
            "aspect_ratio": "16:9",
            "mode": "pro",
            "sound": "on",
        },
        label="V3 多镜头叙事 (3 shots, 4+4+5=13s, Pro, sound=on)",
    )
    return task_id


def test_video_edit(video_url=None):
    """V3 视频编辑 (refer_type=base) - 对已有视频进行文本指令编辑"""
    if not video_url:
        print("\n  ⚠️ 跳过视频编辑测试：需要一个已生成的视频 URL")
        print("  提示: 先运行其他测试获取视频 URL，或设置 TEST_VIDEO_URL 环境变量")
        return None
    task_id = submit_task(
        {
            "model": "kling-v3",
            "prompt": "将背景替换为日落时分的海边沙滩，保持人物动作不变",
            "video_list": [
                {
                    "video_url": video_url,
                    "refer_type": "base",
                    "keep_original_sound": "yes",
                }
            ],
        },
        label="V3 视频编辑 (refer_type=base)",
    )
    return task_id


def test_video_feature_ref(video_url=None):
    """V3 视频特征参考 (refer_type=feature) + 音频"""
    if not video_url:
        print("\n  ⚠️ 跳过视频特征参考测试：需要一个已生成的视频 URL")
        return None
    task_id = submit_task(
        {
            "model": "kling-v3",
            "prompt": "同样的运镜风格，拍摄一只金毛犬在草地上奔跑",
            "video_list": [
                {
                    "video_url": video_url,
                    "refer_type": "feature",
                }
            ],
            "duration": "5",
            "mode": "std",
            "sound": "on",
        },
        label="V3 视频特征参考 (refer_type=feature, sound=on)",
    )
    return task_id


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    if API_KEY == "YOUR_API_KEY":
        print("请先设置环境变量 EZMODEL_API_KEY")
        sys.exit(1)

    wait = "--wait" in sys.argv
    video_url_env = os.getenv("TEST_VIDEO_URL")

    print(f"Base URL: {BASE_URL}")
    print(f"等待模式: {'开启 (会轮询直到完成)' if wait else '关闭 (仅提交)'}")
    print("=" * 60)

    tasks = {}

    # 1) 文生视频 Std
    tasks["t2v_std"] = test_text2video_std()

    # 2) 文生视频 Pro 15s
    tasks["t2v_pro_15s"] = test_text2video_pro_15s()

    # 3) 图生视频 首帧
    tasks["i2v_first"] = test_image2video_first_frame()

    # 4) 多镜头叙事
    tasks["multi_shot"] = test_multi_shot()

    # 5) 视频编辑 & 特征参考 (需要已有视频URL)
    generated_video_url = None
    if wait and tasks["t2v_std"]:
        print(f"\n{'='*60}")
        print("[等待] 等待文生视频(Std)完成，用于后续视频编辑测试...")
        generated_video_url = poll_task(tasks["t2v_std"])

    ref_video = video_url_env or generated_video_url
    tasks["video_edit"] = test_video_edit(ref_video)
    tasks["video_feature"] = test_video_feature_ref(ref_video)

    # 汇总
    print(f"\n{'='*60}")
    print("[汇总] 所有任务提交结果:")
    for name, tid in tasks.items():
        status = f"Task ID: {tid}" if tid else "未提交/失败"
        print(f"  {name:20s} -> {status}")

    if wait:
        print(f"\n{'='*60}")
        print("[轮询] 等待所有剩余任务完成...")
        for name, tid in tasks.items():
            if tid and name != "t2v_std":
                print(f"\n--- {name} ---")
                poll_task(tid)

    print("\n✅ 测试脚本执行完毕")


if __name__ == "__main__":
    main()
