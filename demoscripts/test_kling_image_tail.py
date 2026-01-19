import requests
import time
import json

# 配置信息
BASE_URL = "https://www.ezmodel.cloud"
API_KEY = "sk-" # 请替换为有效的 API Key

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def wait_for_task(task_id):
    """
    按照文档查询任务状态
    参考文档: web/src/pages/Documentation/content/kling-image-video-status.md
    """
    url = f"{BASE_URL}/kling/v1/videos/image2video/{task_id}"
    print(f"正在查询任务状态: {url}")
    
    while True:
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code != 200:
                print(f"查询请求失败: {response.status_code}")
                return None
            
            res_data = response.json()
            
            # 严格按照文档定义的嵌套结构解析
            if res_data.get("code") != "success":
                print(f"业务请求失败: {res_data}")
                return None
            
            # 获取统一状态层
            unified_data = res_data.get("data", {})
            unified_status = unified_data.get("status")
            print(f"统一任务状态: {unified_status}, 进度: {unified_data.get('progress')}")
            
            if unified_status == "SUCCESS":
                # 获取 Kling 原始响应层
                kling_raw_wrapper = unified_data.get("data", {}) # 这是后端 TaskDto.Data
                if kling_raw_wrapper.get("code") == 0:
                    kling_data = kling_raw_wrapper.get("data", {})
                    task_status = kling_data.get("task_status")
                    
                    if task_status == "succeed":
                        videos = kling_data.get("task_result", {}).get("videos", [])
                        if videos:
                            video_url = videos[0].get("url")
                            print(f"任务成功！视频 URL: {video_url}")
                            return video_url
                return None
            
            elif unified_status == "FAILURE":
                print(f"任务失败: {unified_data}")
                return None
                
            # 如果是 SUBMITTED 或 IN_PROGRESS，继续等待
            
        except Exception as e:
            print(f"轮询发生异常: {e}")
            return None
        
        time.sleep(10)

def test_kling_image_tail_flow():
    """
    首尾帧测试流程：提交任务 -> 轮询状态
    参考文档: 
    - 提交: web/src/pages/Documentation/content/kling-image-video.md
    - 查询: web/src/pages/Documentation/content/kling-image-video-status.md
    """
    print("\n[首尾帧图生视频] 1. 正在提交任务...")
    
    submit_url = f"{BASE_URL}/kling/v1/videos/image2video"
    payload = {
        "model": "kling-v2-6",
        "image": "https://p2-kling.klingai.com/bs2/upload-ylab-stunt/special-effect/output/HB1_PROD_ai_web_299690834263822_-4012665849171309178/-7957711300647229468/tempwyvwb.png?x-kcdn-pid=112452&x-oss-process=image%2Fresize%2Cw_1440%2Ch_1851%2Cm_mfit%2Fformat%2Cwebp",
        "image_tail": "https://p2-kling.klingai.com/bs2/upload-ylab-stunt/special-effect/output/HB1_PROD_ai_web_299690834263822_-4012665849171309178/-7957711300647229468/tempwyvwb.png?x-kcdn-pid=112452&x-oss-process=image%2Fresize%2Cw_1440%2Ch_1851%2Cm_mfit%2Fformat%2Cwebp",
        "prompt": "The characters in the images are dancing together in a futuristic city.",
        "duration": "5",
        "aspect_ratio": "16:9",
        "mode": "std"
    }
    
    try:
        res = requests.post(submit_url, headers=HEADERS, json=payload)
        if res.status_code != 200:
            print(f"提交失败: {res.status_code} - {res.text}")
            return
        
        submit_res = res.json()
        # 根据后端返回逻辑获取 task_id
        task_id = submit_res.get("id") or submit_res.get("data", {}).get("task_id")
        
        if not task_id:
            print(f"未能获取 Task ID: {submit_res}")
            return
            
        print(f"任务提交成功，Task ID: {task_id}")
        
        # 2. 开始轮询
        print("\n[首尾帧图生视频] 2. 开始轮询任务状态...")
        video_url = wait_for_task(task_id)
        
        if video_url:
            print(f"\n恭喜！首尾帧视频生成成功: {video_url}")
        else:
            print("\n视频生成失败。")
            
    except Exception as e:
        print(f"提交过程发生异常: {e}")

if __name__ == "__main__":
    test_kling_image_tail_flow()
