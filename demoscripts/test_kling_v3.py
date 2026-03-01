"""
Kling V3 新特性测试脚本
覆盖：文生视频、图生视频、多镜头叙事(multi_prompt)、视频编辑(refer_type=base)、原生音频(sound)

用法:
  python test_kling_v3.py                          # 仅提交所有任务
  python test_kling_v3.py --wait                   # 提交并轮询等待
  python test_kling_v3.py --only multi_shot        # 仅运行多镜头测试
  python test_kling_v3.py --only multi_shot,video_edit --wait
  python test_kling_v3.py --only video_edit --video-url "https://..."
  python test_kling_v3.py --poll 857027474373345290 # 仅轮询已有任务

可用测试名: t2v_std, t2v_pro_15s, i2v_first, multi_shot, video_edit, video_feature
"""

import requests
import time
import os
import sys
import json
import io
import argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

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


def poll_task(task_id, timeout=600, interval=10):
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
# 测试用例注册表
# ---------------------------------------------------------------------------

ALL_TESTS = {}

def register(name):
    def decorator(fn):
        ALL_TESTS[name] = fn
        return fn
    return decorator


@register("t2v_std")
def test_text2video_std(**_):
    """V3 文生视频 - Std 模式, 10s, 含音频"""
    return submit_task(
        {
            "model": "kling-v3-omni",
            "prompt": "一只橘猫在阳光下的花园里追蝴蝶，电影质感，浅景深",
            "mode": "std",
            "duration": "10",
            "aspect_ratio": "16:9",
            "sound": "on",
        },
        label="V3 文生视频 (Std, 10s, sound=on)",
    )


@register("t2v_pro_15s")
def test_text2video_pro_15s(**_):
    """V3 文生视频 - Pro 模式, 15s (V3 新增上限)"""
    return submit_task(
        {
            "model": "kling-v3-omni",
            "prompt": "城市夜景延时摄影，车流光轨从繁忙到寂静，4K电影感",
            "mode": "pro",
            "duration": "15",
            "aspect_ratio": "16:9",
        },
        label="V3 文生视频 (Pro, 15s)",
    )


@register("i2v_first")
def test_image2video_first_frame(**_):
    """V3 图生视频 - 首帧模式"""
    return submit_task(
        {
            "model": "kling-v3-omni",
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


@register("multi_shot")
def test_multi_shot(**_):
    """V3 多镜头叙事 (multi_prompt) - 3个分镜, 总计13s"""
    return submit_task(
        {
            "model": "kling-v3-omni",
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


@register("video_edit")
def test_video_edit(video_url=None, **_):
    """V3 视频编辑 (refer_type=base)"""
    if not video_url:
        print("\n  ⚠️ 跳过视频编辑测试：需要 --video-url 或 TEST_VIDEO_URL")
        return None
    return submit_task(
        {
            "model": "kling-v3-omni",
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


@register("video_feature")
def test_video_feature_ref(video_url=None, **_):
    """V3 视频特征参考 (refer_type=feature)"""
    if not video_url:
        print("\n  ⚠️ 跳过视频特征参考测试：需要 --video-url 或 TEST_VIDEO_URL")
        return None
    return submit_task(
        {
            "model": "kling-v3-omni",
            "prompt": "同样的运镜风格，拍摄一只金毛犬在草地上奔跑",
            "video_list": [
                {
                    "video_url": video_url,
                    "refer_type": "feature",
                }
            ],
            "duration": "5",
            "mode": "std",
        },
        label="V3 视频特征参考 (refer_type=feature)",
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Kling V3 测试脚本")
    p.add_argument("--wait", action="store_true", help="提交后轮询等待完成")
    p.add_argument("--only", type=str, default="",
                   help="仅运行指定测试，逗号分隔。可选: " + ",".join(ALL_TESTS))
    p.add_argument("--poll", type=str, default="",
                   help="仅轮询已有 task_id（逗号分隔多个）")
    p.add_argument("--video-url", type=str, default="",
                   help="用于 video_edit/video_feature 的视频 URL")
    p.add_argument("--timeout", type=int, default=600,
                   help="轮询超时秒数 (默认 600)")
    return p.parse_args()


def main():
    args = parse_args()

    if API_KEY == "YOUR_API_KEY":
        print("请先设置环境变量 EZMODEL_API_KEY")
        sys.exit(1)

    # --poll 模式：仅轮询已有任务
    if args.poll:
        print(f"[轮询模式] 超时: {args.timeout}s")
        for tid in args.poll.split(","):
            tid = tid.strip()
            print(f"\n--- Task {tid} ---")
            poll_task(tid, timeout=args.timeout)
        return

    video_url = args.video_url or os.getenv("TEST_VIDEO_URL")

    # 确定要运行的测试
    if args.only:
        selected = [s.strip() for s in args.only.split(",")]
        unknown = [s for s in selected if s not in ALL_TESTS]
        if unknown:
            print(f"未知测试名: {unknown}")
            print(f"可选: {list(ALL_TESTS.keys())}")
            sys.exit(1)
    else:
        selected = list(ALL_TESTS.keys())

    print(f"Base URL: {BASE_URL}")
    print(f"等待模式: {'开启' if args.wait else '关闭'}")
    print(f"运行测试: {selected}")
    if video_url:
        print(f"视频 URL: {video_url[:80]}...")
    print("=" * 60)

    # 提交任务
    tasks = {}
    for name in selected:
        fn = ALL_TESTS[name]
        tasks[name] = fn(video_url=video_url)

    # 汇总
    print(f"\n{'='*60}")
    print("[汇总] 任务提交结果:")
    for name, tid in tasks.items():
        status = f"Task ID: {tid}" if tid else "未提交/失败"
        print(f"  {name:20s} -> {status}")

    # 轮询
    if args.wait:
        print(f"\n{'='*60}")
        print(f"[轮询] 等待任务完成 (超时 {args.timeout}s)...")
        for name, tid in tasks.items():
            if tid:
                print(f"\n--- {name} ---")
                result = poll_task(tid, timeout=args.timeout)
                if result and name in ("t2v_std", "i2v_first") and not video_url:
                    video_url = result
                    print(f"  (已保存视频 URL 供后续测试使用)")

    print("\n✅ 测试脚本执行完毕")


if __name__ == "__main__":
    main()
