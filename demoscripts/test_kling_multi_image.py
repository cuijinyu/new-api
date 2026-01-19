import requests
import time
import json
import os

# 配置信息
BASE_URL = "http://localhost:3000"  # 替换为你的本地或服务器地址
API_KEY = os.getenv("EZMODEL_API_KEY") or "sk-your-key"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def wait_for_task(task_id):
    """循环轮询任务状态，直到成功或失败"""
    url = f"{BASE_URL}/kling/v1/videos/multi-image2video/{task_id}"
    print(f"正在查询任务状态: {url}")
    
    while True:
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code != 200:
                print(f"查询失败: {response.status_code} - {response.text}")
                return None
            
            data = response.json()            
            # 从返回的数据结构中提取信息 (OpenAI Video 格式)
            status = data.get("status")
            print(f"任务状态: {status}")
            
            if status == "SUCCESS":
                # 视频URL在 metadata.url 中
                video_url = data.get("metadata", {}).get("url")
                if video_url:
                    print(f"获取到视频URL: {video_url}")
                    return video_url
                return None
            elif status == "FAILED":
                print(f"任务失败: {data}")
                return None
        except Exception as e:
            print(f"请求发生异常: {e}")
            return None
        
        time.sleep(5)  # 每 5 秒查询一次

def test_kling_multi_image():
    print("\n[多图参考生视频] 正在提交请求...")
    
    # 测试数据：两张示例图片
    payload = {
        "model": "kling-v1-6",
        "prompt": "The two characters in the images are dancing together in a futuristic city.",
        "image_list": [
            {
                "image": "https://p2-kling.klingai.com/bs2/upload-ylab-stunt/special-effect/output/HB1_PROD_ai_web_299690834263822_-4012665849171309178/-7957711300647229468/tempwyvwb.png?x-kcdn-pid=112452&x-oss-process=image%2Fresize%2Cw_1440%2Ch_1851%2Cm_mfit%2Fformat%2Cwebp"
            },
            {
                "image": "https://p2-kling.klingai.com/bs2/upload-ylab-stunt/special-effect/output/HB1_PROD_ai_web_299690834263822_-4012665849171309178/-7957711300647229468/tempwyvwb.png?x-kcdn-pid=112452&x-oss-process=image%2Fresize%2Cw_1440%2Ch_1851%2Cm_mfit%2Fformat%2Cwebp"
            }
        ],
        "mode": "std",
        "duration": "5",
        "aspect_ratio": "16:9"
    }
    
    url = f"{BASE_URL}/kling/v1/videos/multi-image2video"
    res = requests.post(url, headers=HEADERS, json=payload)
    
    if res.status_code != 200:
        print(f"提交请求失败: {res.status_code} - {res.text}")
        return

    task_id = res.json().get("id")
    print(f"任务提交成功，Task ID: {task_id}")

    # 等待视频生成完成
    video_url = wait_for_task(task_id)
    if video_url:
        print(f"\n恭喜！多图参考生视频已生成: {video_url}")
    else:
        print("\n生成失败或超时。")

if __name__ == "__main__":
    test_kling_multi_image()
