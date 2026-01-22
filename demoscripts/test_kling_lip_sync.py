"""
可灵 Kling 对口型 (Lip Sync) 接口测试脚本

测试流程：
1. 人脸识别 - 识别视频中的人脸，获取 session_id 和 face_id
2. 创建对口型任务 - 使用 session_id 和音频创建对口型任务
3. 查询任务状态 - 轮询直到任务完成

参考文档: web/src/pages/Documentation/content/kling-lip-sync.md
"""

import requests
import time
import os

# 配置信息
BASE_URL = os.getenv("KLING_BASE_URL", "https://www.ezmodel.cloud")
API_KEY = os.getenv("EZMODEL_API_KEY", "YOUR_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 测试用的视频和音频 URL（请替换为实际可用的 URL）
TEST_VIDEO_URL = "https://example.com/test_video.mp4"
TEST_AUDIO_URL = "https://example.com/test_audio.mp3"


def step1_identify_face(video_url: str = None, video_id: str = None):
    """
    步骤1: 人脸识别
    
    接口: POST /kling/v1/videos/identify-face
    参数:
        - video_id: 可灵AI生成的视频ID (与 video_url 二选一)
        - video_url: 视频的获取URL (与 video_id 二选一)
    返回:
        - session_id: 会话ID，有效期24小时
        - face_data: 人脸数据列表
    """
    url = f"{BASE_URL}/kling/v1/videos/identify-face"
    print(f"\n[步骤 1] 人脸识别")
    print(f"请求地址: POST {url}")
    
    payload = {}
    if video_id:
        payload["video_id"] = video_id
    elif video_url:
        payload["video_url"] = video_url
    else:
        print("错误: video_id 和 video_url 必须提供其一")
        return None, None
    
    print(f"请求参数: {payload}")
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"请求失败: {response.text}")
            return None, None
        
        data = response.json()
        print(f"响应数据: {data}")
        
        # 解析响应
        if data.get("code") != 0:
            print(f"业务错误: {data.get('message')}")
            return None, None
        
        session_id = data.get("data", {}).get("session_id")
        face_data = data.get("data", {}).get("face_data", [])
        
        print(f"✓ 获取 session_id: {session_id}")
        print(f"✓ 识别到 {len(face_data)} 个人脸:")
        for i, face in enumerate(face_data):
            print(f"  - 人脸 {i+1}: face_id={face.get('face_id')}, "
                  f"时间区间=[{face.get('start_time')}ms, {face.get('end_time')}ms]")
        
        return session_id, face_data
        
    except Exception as e:
        print(f"请求异常: {e}")
        return None, None


def step2_create_lip_sync_task(session_id: str, face_id: str, 
                                audio_url: str = None, audio_id: str = None,
                                sound_start_time: int = 0, 
                                sound_end_time: int = 5000,
                                sound_insert_time: int = 0):
    """
    步骤2: 创建对口型任务
    
    接口: POST /kling/v1/videos/advanced-lip-sync
    参数:
        - session_id: 会话ID (必须)
        - face_choose: 人脸选择配置数组 (必须)
            - face_id: 人脸ID (必须)
            - audio_id / sound_file: 音频来源 (二选一)
            - sound_start_time: 音频裁剪起点时间，毫秒 (必须)
            - sound_end_time: 音频裁剪终点时间，毫秒 (必须)
            - sound_insert_time: 裁剪后音频插入时间，毫秒 (必须)
            - sound_volume: 音频音量 [0,2]，默认1 (可选)
            - original_audio_volume: 原视频音量 [0,2]，默认1 (可选)
    返回:
        - task_id: 任务ID
    """
    url = f"{BASE_URL}/kling/v1/videos/advanced-lip-sync"
    print(f"\n[步骤 2] 创建对口型任务")
    print(f"请求地址: POST {url}")
    
    face_config = {
        "face_id": face_id,
        "sound_start_time": sound_start_time,
        "sound_end_time": sound_end_time,
        "sound_insert_time": sound_insert_time,
        "sound_volume": 1.0,
        "original_audio_volume": 0.5
    }
    
    if audio_id:
        face_config["audio_id"] = audio_id
    elif audio_url:
        face_config["sound_file"] = audio_url
    else:
        print("错误: audio_id 和 sound_file(audio_url) 必须提供其一")
        return None
    
    payload = {
        "session_id": session_id,
        "face_choose": [face_config]
    }
    
    print(f"请求参数: {payload}")
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"请求失败: {response.text}")
            return None
        
        data = response.json()
        print(f"响应数据: {data}")
        
        # 解析 OpenAI Video 格式的响应
        task_id = data.get("id") or data.get("data", {}).get("task_id")
        
        if task_id:
            print(f"✓ 任务创建成功，task_id: {task_id}")
        else:
            print(f"未能获取 task_id: {data}")
        
        return task_id
        
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def step3_query_task(task_id: str, max_retries: int = 60, interval: int = 10):
    """
    步骤3: 查询对口型任务状态
    
    接口: GET /kling/v1/videos/advanced-lip-sync/:task_id
    响应:
        - code: 错误码 (0 表示成功)
        - data.task_id: 任务ID
        - data.task_status: 任务状态 (submitted/processing/succeed/failed)
        - data.task_status_msg: 任务状态信息
        - data.task_result.videos[]: 生成的视频列表
        - data.created_at: 任务创建时间 (毫秒)
        - data.updated_at: 任务更新时间 (毫秒)
    """
    url = f"{BASE_URL}/kling/v1/videos/advanced-lip-sync/{task_id}"
    print(f"\n[步骤 3] 查询任务状态")
    print(f"请求地址: GET {url}")
    
    for i in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS)
            
            if response.status_code != 200:
                print(f"查询失败: {response.text}")
                return None
            
            data = response.json()
            
            # 解析统一响应格式
            if data.get("code") == "success":
                unified_data = data.get("data", {})
                status = unified_data.get("status")
                progress = unified_data.get("progress", "0%")
                
                print(f"[{i+1}/{max_retries}] 状态: {status}, 进度: {progress}")
                
                if status == "SUCCESS":
                    # 获取 Kling 原始数据
                    kling_wrapper = unified_data.get("data", {})
                    if kling_wrapper.get("code") == 0:
                        kling_data = kling_wrapper.get("data", {})
                        videos = kling_data.get("task_result", {}).get("videos", [])
                        if videos:
                            video_url = videos[0].get("url")
                            video_duration = videos[0].get("duration")
                            print(f"✓ 任务完成！")
                            print(f"  - 视频URL: {video_url}")
                            print(f"  - 视频时长: {video_duration}秒")
                            return video_url
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


def test_lip_sync_full_flow():
    """完整测试流程"""
    print("=" * 60)
    print("可灵 Kling 对口型 (Lip Sync) 接口测试")
    print("=" * 60)
    
    # 步骤1: 人脸识别
    session_id, face_data = step1_identify_face(video_url=TEST_VIDEO_URL)
    
    if not session_id or not face_data:
        print("\n人脸识别失败，测试终止。")
        return
    
    # 获取第一个人脸的 ID
    face_id = face_data[0].get("face_id")
    start_time = face_data[0].get("start_time", 0)
    end_time = face_data[0].get("end_time", 5000)
    
    # 步骤2: 创建对口型任务
    task_id = step2_create_lip_sync_task(
        session_id=session_id,
        face_id=face_id,
        audio_url=TEST_AUDIO_URL,
        sound_start_time=0,
        sound_end_time=min(5000, end_time - start_time),  # 音频时长不超过人脸可用时长
        sound_insert_time=start_time
    )
    
    if not task_id:
        print("\n创建对口型任务失败，测试终止。")
        return
    
    # 步骤3: 查询任务状态
    video_url = step3_query_task(task_id)
    
    if video_url:
        print("\n" + "=" * 60)
        print("测试成功！")
        print(f"生成的对口型视频: {video_url}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("测试失败！")
        print("=" * 60)


def test_identify_face_only():
    """仅测试人脸识别接口"""
    print("=" * 60)
    print("测试人脸识别接口")
    print("=" * 60)
    
    session_id, face_data = step1_identify_face(video_url=TEST_VIDEO_URL)
    
    if session_id:
        print(f"\n✓ 人脸识别成功")
        print(f"  session_id: {session_id}")
        print(f"  识别到 {len(face_data)} 个人脸")
    else:
        print("\n✗ 人脸识别失败")


if __name__ == "__main__":
    # 运行完整测试
    test_lip_sync_full_flow()
    
    # 或者仅测试人脸识别
    # test_identify_face_only()
