import requests
import time
import json
import sys

import os

# 配置信息
BASE_URL = "https://www.ezmodel.cloud"  # 请根据实际情况修改
API_KEY = os.getenv("EZMODEL_API_KEY", "your_api_key_here")  # 从环境变量读取，默认为 your_api_key_here

MODELS = [
    "seedance-1-5-pro-251215",
    "seedance-1-0-pro-fast-251015",
    "seedance-1-0-pro-250528",
    "seedance-1-0-lite-i2v-250428",
    "seedance-1-0-lite-t2v-250428"
]

def test_video_generation(model):
    print(f"\n{'='*50}")
    print(f"正在测试模型: {model}")
    print(f"{'='*50}")

    submit_url = f"{BASE_URL}/v1/video/generations"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 构造请求数据
    data = {
        "model": model,
        "prompt": "一只可爱的小猫在花园里玩耍，阳光明媚，色彩鲜艳，电影级画质。",
    }
    
    # 如果是 i2v 模型，添加一张示例图片（这里使用占位图，实际测试建议替换为真实图片URL）
    if "i2v" in model:
        data["images"] = ["https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png"]
        print(f"检测到图生视频模型，已添加参考图片。")

    try:
        # 1. 提交任务
        print(f"正在提交任务...")
        response = requests.post(submit_url, headers=headers, json=data)
        res_json = response.json()
        
        if response.status_code != 200:
            print(f"提交任务失败: {res_json}")
            return

        task_id = res_json.get("task_id")
        if not task_id:
            print(f"未获取到 task_id: {res_json}")
            return
        
        print(f"任务提交成功，Task ID: {task_id}")

        # 2. 轮询状态
        fetch_url = f"{BASE_URL}/v1/video/generations/{task_id}"
        max_retries = 30
        retry_interval = 10
        
        print(f"开始轮询任务状态 (最大尝试次数: {max_retries})...")
        for i in range(max_retries):
            time.sleep(retry_interval)
            fetch_res = requests.get(fetch_url, headers=headers)
            fetch_json = fetch_res.json()
            
            if fetch_res.status_code != 200:
                print(f"查询任务失败: {fetch_json}")
                break
                
            # 兼容不同的返回格式
            # new-api 的任务系统通常返回 data 字段
            task_data = fetch_json.get("data", fetch_json)
            status = task_data.get("status")
            progress = task_data.get("progress", "0%")
            
            print(f"尝试 {i+1}: 状态 = {status}, 进度 = {progress}")
            
            if status == "success":
                video_url = task_data.get("url") or task_data.get("video_url")
                print(f"\n🎉 任务成功！")
                print(f"视频链接: {video_url}")
                break
            elif status == "failure":
                reason = task_data.get("fail_reason") or task_data.get("reason")
                print(f"\n❌ 任务失败: {reason}")
                break
        else:
            print(f"\n超时：任务在 {max_retries * retry_interval} 秒内未完成。")

    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    if API_KEY == "your_api_key_here":
        print("请先在脚本中配置 API_KEY")
        sys.exit(1)
        
    for model in MODELS:
        test_video_generation(model)
        print("\n等待 5 秒后开始下一个模型测试...")
        time.sleep(5)
