"""
可灵 Kling 视频延长 (Video Extend) 接口测试脚本

测试流程：
1. 先生成一个基础视频（文生视频）
2. 使用视频延长接口延长该视频
3. 查询任务状态直到完成

参考文档: web/src/pages/Documentation/content/kling-video-extend.md
"""

import requests
import time
import os

# 配置信息
BASE_URL = os.getenv("KLING_BASE_URL", "https://www.ezmodel.cloud")
API_KEY = os.getenv("EZMODEL_API_KEY", "YOUR_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def wait_for_video_generation(task_id: str, endpoint: str = "text2video", 
                               max_retries: int = 60, interval: int = 10):
    """通用的视频任务等待函数"""
    url = f"{BASE_URL}/kling/v1/videos/{endpoint}/{task_id}"
    print(f"查询地址: GET {url}")
    
    for i in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS)
            
            if response.status_code != 200:
                print(f"查询失败: {response.text}")
                return None, None
            
            data = response.json()
            
            if data.get("code") == "success":
                unified_data = data.get("data", {})
                status = unified_data.get("status")
                progress = unified_data.get("progress", "0%")
                
                print(f"[{i+1}/{max_retries}] 状态: {status}, 进度: {progress}")
                
                if status == "SUCCESS":
                    kling_wrapper = unified_data.get("data", {})
                    if kling_wrapper.get("code") == 0:
                        kling_data = kling_wrapper.get("data", {})
                        task_result = kling_data.get("task_result", {})
                        videos = task_result.get("videos", [])
                        if videos:
                            video_id = videos[0].get("id")
                            video_url = videos[0].get("url")
                            video_duration = videos[0].get("duration")
                            return video_id, video_url
                    return None, None
                    
                elif status == "FAILURE":
                    print(f"任务失败: {unified_data}")
                    return None, None
                    
        except Exception as e:
            print(f"查询异常: {e}")
        
        time.sleep(interval)
    
    print(f"超过最大重试次数 ({max_retries})")
    return None, None


def step1_generate_base_video():
    """
    步骤1: 生成基础视频（文生视频）
    用于后续的视频延长测试
    """
    url = f"{BASE_URL}/kling/v1/videos/text2video"
    print(f"\n[步骤 1] 生成基础视频")
    print(f"请求地址: POST {url}")
    
    payload = {
        "model": "kling-v1-6",
        "prompt": "A beautiful sunset over the ocean, waves gently rolling onto the beach, cinematic style.",
        "mode": "std",
        "duration": "5"
    }
    
    print(f"请求参数: {payload}")
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"请求失败: {response.text}")
            return None
        
        data = response.json()
        task_id = data.get("id")
        print(f"✓ 任务提交成功，task_id: {task_id}")
        
        # 等待视频生成完成
        print("\n等待基础视频生成...")
        video_id, video_url = wait_for_video_generation(task_id, "text2video")
        
        if video_id:
            print(f"✓ 基础视频生成完成")
            print(f"  - video_id: {video_id}")
            print(f"  - video_url: {video_url}")
            return video_id
        else:
            print("✗ 基础视频生成失败")
            return None
            
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def step2_create_video_extend_task(video_id: str, prompt: str = None, 
                                    negative_prompt: str = None,
                                    cfg_scale: float = 0.5):
    """
    步骤2: 创建视频延长任务
    
    接口: POST /kling/v1/videos/video-extend
    参数:
        - video_id: 视频ID (必须) - 需要延长的原始视频ID
        - prompt: 正向文本提示词 (可选) - 不超过2500字符
        - negative_prompt: 负向文本提示词 (可选) - 不超过2500字符
        - cfg_scale: 提示词参考强度 (可选) - 范围[0,1]，默认0.5
        - callback_url: 回调地址 (可选)
    返回:
        - task_id: 任务ID
    """
    url = f"{BASE_URL}/kling/v1/videos/video-extend"
    print(f"\n[步骤 2] 创建视频延长任务")
    print(f"请求地址: POST {url}")
    
    payload = {
        "video_id": video_id,
        "cfg_scale": cfg_scale
    }
    
    if prompt:
        payload["prompt"] = prompt
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    
    print(f"请求参数: {payload}")
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"请求失败: {response.text}")
            return None
        
        data = response.json()
        print(f"响应数据: {data}")
        
        task_id = data.get("id") or data.get("data", {}).get("task_id")
        
        if task_id:
            print(f"✓ 视频延长任务创建成功，task_id: {task_id}")
        else:
            print(f"未能获取 task_id: {data}")
        
        return task_id
        
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def step3_query_video_extend_task(task_id: str, max_retries: int = 60, interval: int = 10):
    """
    步骤3: 查询视频延长任务状态
    
    接口: GET /kling/v1/videos/video-extend/:task_id
    响应:
        - code: 错误码 (0 表示成功)
        - data.task_id: 任务ID
        - data.task_status: 任务状态 (submitted/processing/succeed/failed)
        - data.task_status_msg: 任务状态信息
        - data.task_result.videos[]: 生成的视频列表
            - id: 视频ID
            - url: 视频URL（30天后清理）
            - duration: 视频时长（秒）
        - data.created_at: 任务创建时间（毫秒）
        - data.updated_at: 任务更新时间（毫秒）
    """
    url = f"{BASE_URL}/kling/v1/videos/video-extend/{task_id}"
    print(f"\n[步骤 3] 查询视频延长任务状态")
    print(f"请求地址: GET {url}")
    
    for i in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS)
            
            if response.status_code != 200:
                print(f"查询失败: {response.text}")
                return None
            
            data = response.json()
            
            if data.get("code") == "success":
                unified_data = data.get("data", {})
                status = unified_data.get("status")
                progress = unified_data.get("progress", "0%")
                
                print(f"[{i+1}/{max_retries}] 状态: {status}, 进度: {progress}")
                
                if status == "SUCCESS":
                    kling_wrapper = unified_data.get("data", {})
                    if kling_wrapper.get("code") == 0:
                        kling_data = kling_wrapper.get("data", {})
                        videos = kling_data.get("task_result", {}).get("videos", [])
                        if videos:
                            video = videos[0]
                            print(f"✓ 视频延长完成！")
                            print(f"  - 视频ID: {video.get('id')}")
                            print(f"  - 视频URL: {video.get('url')}")
                            print(f"  - 视频时长: {video.get('duration')}秒")
                            return video.get("url")
                    return None
                    
                elif status == "FAILURE":
                    print(f"✗ 任务失败: {unified_data}")
                    return None
            else:
                print(f"响应异常: {data}")
                
        except Exception as e:
            print(f"查询异常: {e}")
        
        time.sleep(interval)
    
    print(f"✗ 超过最大重试次数 ({max_retries})")
    return None


def test_video_extend_full_flow():
    """完整测试流程：生成基础视频 -> 延长视频"""
    print("=" * 60)
    print("可灵 Kling 视频延长 (Video Extend) 接口测试")
    print("=" * 60)
    
    # 步骤1: 生成基础视频
    video_id = step1_generate_base_video()
    
    if not video_id:
        print("\n基础视频生成失败，测试终止。")
        return
    
    # 步骤2: 创建视频延长任务
    task_id = step2_create_video_extend_task(
        video_id=video_id,
        prompt="继续展现日落的美景，镜头缓缓拉远，天空逐渐变暗",
        negative_prompt="模糊, 抖动, 画面跳跃",
        cfg_scale=0.5
    )
    
    if not task_id:
        print("\n视频延长任务创建失败，测试终止。")
        return
    
    # 步骤3: 查询任务状态
    extended_video_url = step3_query_video_extend_task(task_id)
    
    if extended_video_url:
        print("\n" + "=" * 60)
        print("测试成功！")
        print(f"延长后的视频: {extended_video_url}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("测试失败！")
        print("=" * 60)


def test_video_extend_with_existing_video(video_id: str):
    """使用已有的视频ID测试视频延长"""
    print("=" * 60)
    print("视频延长测试（使用已有视频）")
    print("=" * 60)
    print(f"输入视频ID: {video_id}")
    
    # 创建视频延长任务
    task_id = step2_create_video_extend_task(
        video_id=video_id,
        prompt="继续展现场景，保持画面风格一致",
        cfg_scale=0.5
    )
    
    if not task_id:
        print("\n视频延长任务创建失败。")
        return
    
    # 查询任务状态
    extended_video_url = step3_query_video_extend_task(task_id)
    
    if extended_video_url:
        print(f"\n✓ 延长后的视频: {extended_video_url}")
    else:
        print("\n✗ 视频延长失败")


if __name__ == "__main__":
    # 运行完整测试（先生成基础视频，再延长）
    test_video_extend_full_flow()
    
    # 或者使用已有的视频ID测试
    # test_video_extend_with_existing_video("your_video_id_here")
