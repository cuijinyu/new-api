import requests
import time
import json

# 配置信息
BASE_URL = "https://www.ezmodel.cloud"
import os
API_KEY = os.getenv("EZMODEL_API_KEY")  # 请在环境变量中设置 EZMODEL_API_KEY
import time
import json

# 配置信息
BASE_URL = "https://www.ezmodel.cloud"
API_KEY = "你的_API_KEY_在这里"  # 替换为你的真实 API Key

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def wait_for_task(endpoint, task_id):
    """循环轮询任务状态，直到成功或失败"""
    url = f"{BASE_URL}/kling/v1/videos/{endpoint}/{task_id}"
    print(f"正在查询任务状态: {url}")
    
    while True:
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code != 200:
                print(f"查询失败: {response.text}")
                return None
            
            data = response.json()
            status = data.get("status")
            print(f"任务状态: {status}")
            
            if status == "succeed":
                # 这里的字段名根据 OpenAI Video 格式，通常在 metadata 里的 url
                return data.get("metadata", {}).get("url")
            elif status == "failed":
                print(f"任务失败: {data}")
                return None
        except Exception as e:
            print(f"请求发生异常: {e}")
            return None
        
        time.sleep(10)  # 每 10 秒查询一次

def test_kling_flow():
    # --- 步骤 1: 生成一个普通视频 (Text2Video) ---
    print("\n[步骤 1] 正在提交文生视频请求...")
    t2v_payload = {
        "model": "kling-v2-6",
        "prompt": "A cute cat running in the garden, cinematic style.",
        "mode": "pro",
        "duration": 5
    }
    
    t2v_res = requests.post(f"{BASE_URL}/kling/v1/videos/text2video", headers=HEADERS, json=t2v_payload)
    if t2v_res.status_code != 200:
        print(f"提交文生视频失败: {t2v_res.text}")
        return

    t2v_task_id = t2v_res.json().get("id")
    print(f"文生视频任务提交成功，Task ID: {t2v_task_id}")

    # 等待视频生成完成
    video_url = wait_for_task("text2video", t2v_task_id)
    if not video_url:
        print("未能获取到生成的视频 URL，流程终止。")
        return
    
    print(f"视频生成成功！URL: {video_url}")

    # --- 步骤 2: 使用 Motion Control 控制动作 ---
    # Motion Control 需要一个角色图片 (image_url) 和一个动作参考视频 (video_url)
    # 这里我们将上一步生成的视频作为动作参考
    print("\n[步骤 2] 正在提交 Motion Control 动作控制请求...")
    
    motion_payload = {
        "model": "kling-v2-6",
        "mode": "pro",
        "metadata": {
            "prompt": "The character follows the movement of the reference video.",
            # "image_url": "https://example.com/your_character_image.jpg", # 替换为你自己的角色图片
            "video_url": video_url, # 使用刚才生成的视频作为动作参考
            "character_orientation": "image" # 角色朝向，可选 image 或 video
        }
    }
    
    mc_res = requests.post(f"{BASE_URL}/kling/v1/videos/motion-control", headers=HEADERS, json=motion_payload)
    if mc_res.status_code != 200:
        print(f"提交 Motion Control 失败: {mc_res.text}")
        return

    mc_task_id = mc_res.json().get("id")
    print(f"Motion Control 任务提交成功，Task ID: {mc_task_id}")

    # 等待最终结果
    final_video_url = wait_for_task("motion-control", mc_task_id)
    if final_video_url:
        print(f"\n恭喜！最终动作控制视频已生成: {final_video_url}")

if __name__ == "__main__":
    test_kling_flow()



HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def wait_for_task(endpoint, task_id):
    """循环轮询任务状态，直到成功或失败"""
    url = f"{BASE_URL}/kling/v1/videos/{endpoint}/{task_id}"
    print(f"正在查询任务状态: {url}")
    
    while True:
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code != 200:
                print(f"查询失败: {response.text}")
                return None
            
            data = response.json()
            status = data.get("status")
            print(f"任务状态: {status}")
            
            if status == "succeed":
                # 这里的字段名根据 OpenAI Video 格式，通常在 metadata 里的 url
                return data.get("metadata", {}).get("url")
            elif status == "failed":
                print(f"任务失败: {data}")
                return None
        except Exception as e:
            print(f"请求发生异常: {e}")
            return None
        
        time.sleep(10)  # 每 10 秒查询一次

def test_kling_flow():
    # --- 步骤 1: 生成一个普通视频 (Text2Video) ---
    print("\n[步骤 1] 正在提交文生视频请求...")
    t2v_payload = {
        "model": "kling-v2-6",
        "prompt": "A cute cat running in the garden, cinematic style.",
        "mode": "pro",
        "duration": 5
    }
    
    t2v_res = requests.post(f"{BASE_URL}/kling/v1/videos/text2video", headers=HEADERS, json=t2v_payload)
    if t2v_res.status_code != 200:
        print(f"提交文生视频失败: {t2v_res.text}")
        return

    t2v_task_id = t2v_res.json().get("id")
    print(f"文生视频任务提交成功，Task ID: {t2v_task_id}")

    # 等待视频生成完成
    video_url = wait_for_task("text2video", t2v_task_id)
    if not video_url:
        print("未能获取到生成的视频 URL，流程终止。")
        return
    
    print(f"视频生成成功！URL: {video_url}")

    # --- 步骤 2: 使用 Motion Control 控制动作 ---
    # Motion Control 需要一个角色图片 (image_url) 和一个动作参考视频 (video_url)
    # 这里我们将上一步生成的视频作为动作参考
    print("\n[步骤 2] 正在提交 Motion Control 动作控制请求...")
    
    motion_payload = {
        "model": "kling-v2-6",
        "mode": "std",
        "metadata": {
            "prompt": "The character follows the movement of the reference video.",
            # "image_url": "https://example.com/your_character_image.jpg", # 替换为你自己的角色图片
            "video_url": video_url, # 使用刚才生成的视频作为动作参考
            "character_orientation": "image" # 角色朝向，可选 image 或 video
        }
    }
    
    mc_res = requests.post(f"{BASE_URL}/kling/v1/videos/motion-control", headers=HEADERS, json=motion_payload)
    if mc_res.status_code != 200:
        print(f"提交 Motion Control 失败: {mc_res.text}")
        return

    mc_task_id = mc_res.json().get("id")
    print(f"Motion Control 任务提交成功，Task ID: {mc_task_id}")

    # 等待最终结果
    final_video_url = wait_for_task("motion-control", mc_task_id)
    if final_video_url:
        print(f"\n恭喜！最终动作控制视频已生成: {final_video_url}")

if __name__ == "__main__":
    test_kling_flow()

