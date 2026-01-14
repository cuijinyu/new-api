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
API_KEY = "YOUR_API_KEY"  # 替换为你的真实 API Key

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def wait_for_task(task_id):
    """循环轮询任务状态，直到成功或失败"""
    url = f"{BASE_URL}/v1/video/generations/{task_id}"
    print(f"正在查询任务状态: {url}")
    
    while True:
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code != 200:
                print(f"查询失败: {response.text}")
                return None
            
            data = response.json()            
            # 从返回的数据结构中提取信息
            task_data = data.get("data", {})
            status = task_data.get("status")
            print(f"任务状态: {status}")
            
            if status == "SUCCESS":  # 注意：返回的是大写的 "SUCCESS"
                # 视频URL在 data.data.task_result.videos[0].url
                task_result = task_data.get("data", {}).get("data", {}).get("task_result", {})
                videos = task_result.get("videos", [])
                if videos and len(videos) > 0:
                    print(f"获取到视频URL: {videos[0].get('url')}")
                    return videos[0].get("url")
                return None
            elif status == "FAILED":
                print(f"任务失败: {task_data}")
                return None
        except Exception as e:
            print(f"请求发生异常: {e}")
            return None
        
        time.sleep(10)  # 每 10 秒查询一次

def test_kling_flow():
    # # --- 步骤 1: 生成一个普通视频 (Text2Video) ---
    print("\n[步骤 1] 正在提交文生视频请求...")
    t2v_payload = {
        "model": "kling-v2-6",
        "prompt": "A cute cat running in the garden, cinematic style.",
        "mode": "pro",
        "duration": "5"
    }
    
    t2v_res = requests.post(f"{BASE_URL}/kling/v1/videos/text2video", headers=HEADERS, json=t2v_payload)
    if t2v_res.status_code != 200:
        print(f"提交文生视频失败: {t2v_res.text}")
        return

    t2v_task_id = t2v_res.json().get("id")
    print(f"文生视频任务提交成功，Task ID: {t2v_task_id}")

    # 等待视频生成完成
    video_url = wait_for_task(t2v_task_id)
    if not video_url:
        print("未能获取到生成的视频 URL，流程终止。")
        return
    
    print(f"视频生成成功！URL: {video_url}")

    # --- 步骤 2: 使用 Motion Control 控制动作 ---
    Motion Control 需要一个角色图片 (image_url) 和一个动作参考视频 (video_url)
    # 这里我们将上一步生成的视频作为动作参考
    print("\n[步骤 2] 正在提交 Motion Control 动作控制请求...")
    video_url="https://v15-kling-fdl.klingai.com/bs2/upload-ylab-stunt-sgp/muse/825207651386261536/VIDEO/20251216/2b8486395cc9bf73d20d34c51fa76d1f-276f2255-f249-4ff3-9cce-d509bcf64071.mp4?cacheKey=ChtzZWN1cml0eS5rbGluZy5tZXRhX2VuY3J5cHQSsAFXShOAmi4-XzRxnjrmORQj8Nj5SP8_0liuj0x2NPZ6fzsWfX0S4OBXU-nLsMCu1_-_UrAl-3ndkFo5y7Zlp7VZzXLvZnF5Wcl49vB_QfLTds6FpdTAxAQImpCr3ykxJpZo9yDjI5U-BwJ6rxTozdmatXF9vDrTHa2LhAVmYtaU677Kaxij5V0y6G74XUv2HNbRmoHylgjpTVtvE1m068ugDSKWOQjp9-WngZYBAk-zdhoSnEyggwjlEmAabESg8cJCaRyFIiDO3uoutCdyZTZSyitqXx4WiSocGQjyKiICKwyKPM733ygFMAE&x-kcdn-pid=112781&Expires=1768489077&Signature=GlQp~PIshY~mAYd~Yn6VBELVfyp18VTo-krp6WJnK2nYql0Ixlxy1JxG~8SX-IM~KFnmbc0Z1HVTJmkbbLCP5SBuUXzvc~c4UHlURVCUAed0CNtWTy9d660IEgH9DxRMkGCftSmJUHF0aI7YpIaxTlMIZ2SfpkKJ125QAWpqE~49XZmW9GXdBM6AAXl3-UdiDRKWZzt6R3-FR2pnLcDYBUO-Joif7qOPkImH-6MzrRtsATq0eFX8TlXOl630k-E75XwoBZzI-FyXOEepq9mmqbivGbjV23fhcVbDJ28ugVBiiwENmbtYZyygi-KtS8jo2hDGOYNjNZUIiq1hOiTP4g&Key-Pair-Id=K1FG4T7LWJK0FU"
    motion_payload = {
        "model": "kling-v2-6",
        "mode": "std",
        "prompt": "The character follows the movement of the reference video.",
        "image_url": "https://p2-kling.klingai.com/bs2/upload-ylab-stunt/special-effect/output/HB1_PROD_ai_web_299690834263822_-4012665849171309178/-7957711300647229468/tempwyvwb.png?x-kcdn-pid=112452&x-oss-process=image%2Fresize%2Cw_1440%2Ch_1851%2Cm_mfit%2Fformat%2Cwebp",
        "video_url": video_url, # 使用刚才生成的视频作为动作参考
        "character_orientation": "image" # 角色朝向，可选 image 或 video
    }
    
    mc_res = requests.post(f"{BASE_URL}/kling/v1/videos/motion-control", headers=HEADERS, json=motion_payload)
    if mc_res.status_code != 200:
        print(f"提交 Motion Control 失败: {mc_res.text}")
        return

    mc_task_id = mc_res.json().get("id")
    print(f"Motion Control 任务提交成功，Task ID: {mc_task_id}")

    # 等待最终结果
    final_video_url = wait_for_task(mc_task_id)
    if final_video_url:
        print(f"\n恭喜！最终动作控制视频已生成: {final_video_url}")

if __name__ == "__main__":
    test_kling_flow()

