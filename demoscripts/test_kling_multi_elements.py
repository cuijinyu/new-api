"""
可灵 Kling 多模态视频编辑 (Multi-Elements) 接口测试脚本

测试流程：
1. 初始化待编辑视频 - 获取 session_id 和视频信息
2. 增加视频选区 - 标记需要编辑的区域（可选）
3. 预览已选区视频 - 预览标记效果（可选）
4. 创建编辑任务 - 提交视频编辑任务
5. 查询任务状态 - 轮询直到完成

参考文档: web/src/pages/Documentation/content/kling-multi-elements.md
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

# 测试用的视频和图片 URL（请替换为实际可用的 URL）
TEST_VIDEO_URL = "https://example.com/test_video.mp4"
TEST_IMAGE_URL = "https://example.com/test_image.jpg"


def step1_init_selection(video_url: str = None, video_id: str = None):
    """
    步骤1: 初始化待编辑视频
    
    接口: POST /kling/v1/videos/multi-elements/init-selection
    参数:
        - video_id: 视频ID，从历史作品中选择 (与 video_url 二选一)
        - video_url: 视频URL (与 video_id 二选一)
            - 支持格式: MP4, MOV
            - 时长: ≥2s且≤5s，或 ≥7s且≤10s
            - 宽高: 720px - 2160px
            - 帧率: 24, 30, 60fps
    返回:
        - session_id: 会话ID，有效期24小时
        - fps: 帧率
        - original_duration: 视频时长
        - width/height: 视频尺寸
        - total_frame: 总帧数
        - normalized_video: 初始化后的视频URL
    """
    url = f"{BASE_URL}/kling/v1/videos/multi-elements/init-selection"
    print(f"\n[步骤 1] 初始化待编辑视频")
    print(f"请求地址: POST {url}")
    
    payload = {}
    if video_id:
        payload["video_id"] = video_id
    elif video_url:
        payload["video_url"] = video_url
    else:
        print("错误: video_id 和 video_url 必须提供其一")
        return None
    
    print(f"请求参数: {payload}")
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"请求失败: {response.text}")
            return None
        
        data = response.json()
        print(f"响应数据: {data}")
        
        if data.get("code") != 0:
            print(f"业务错误: {data.get('message')}")
            return None
        
        resp_data = data.get("data", {})
        
        if resp_data.get("status") != 0:
            print(f"初始化失败，拒识码: {resp_data.get('status')}")
            return None
        
        session_id = resp_data.get("session_id")
        
        print(f"✓ 初始化成功")
        print(f"  - session_id: {session_id}")
        print(f"  - fps: {resp_data.get('fps')}")
        print(f"  - 时长: {resp_data.get('original_duration')}ms")
        print(f"  - 尺寸: {resp_data.get('width')}x{resp_data.get('height')}")
        print(f"  - 总帧数: {resp_data.get('total_frame')}")
        
        return resp_data
        
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def step2_add_selection(session_id: str, frame_index: int, points: list):
    """
    步骤2: 增加视频选区
    
    接口: POST /kling/v1/videos/multi-elements/add-selection
    参数:
        - session_id: 会话ID (必须)
        - frame_index: 帧号 (必须)，最多支持10个标记帧
        - points: 点选坐标数组 (必须)
            - x: X坐标，范围 [0, 1]
            - y: Y坐标，范围 [0, 1]，[0,0] 代表画面左上角
    返回:
        - rle_mask_list: RLE蒙版列表
    """
    url = f"{BASE_URL}/kling/v1/videos/multi-elements/add-selection"
    print(f"\n[步骤 2] 增加视频选区")
    print(f"请求地址: POST {url}")
    
    payload = {
        "session_id": session_id,
        "frame_index": frame_index,
        "points": points
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
        
        if data.get("code") != 0:
            print(f"业务错误: {data.get('message')}")
            return None
        
        resp_data = data.get("data", {})
        
        if resp_data.get("status") != 0:
            print(f"选区失败，拒识码: {resp_data.get('status')}")
            return None
        
        res = resp_data.get("res", {})
        mask_list = res.get("rle_mask_list", [])
        
        print(f"✓ 选区添加成功")
        print(f"  - 帧号: {res.get('frame_index')}")
        print(f"  - 识别到 {len(mask_list)} 个对象")
        
        return resp_data
        
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def step3_preview_selection(session_id: str):
    """
    步骤3: 预览已选区视频
    
    接口: POST /kling/v1/videos/multi-elements/preview-selection
    参数:
        - session_id: 会话ID (必须)
    返回:
        - video: 含mask的视频URL
        - video_cover: 含mask的视频封面URL
        - tracking_output: 每一帧mask结果
    """
    url = f"{BASE_URL}/kling/v1/videos/multi-elements/preview-selection"
    print(f"\n[步骤 3] 预览已选区视频")
    print(f"请求地址: POST {url}")
    
    payload = {
        "session_id": session_id
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
        
        if data.get("code") != 0:
            print(f"业务错误: {data.get('message')}")
            return None
        
        resp_data = data.get("data", {})
        res = resp_data.get("res", {})
        
        print(f"✓ 预览生成成功")
        print(f"  - 预览视频: {res.get('video')}")
        print(f"  - 视频封面: {res.get('video_cover')}")
        
        return resp_data
        
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def step4_create_task(session_id: str, edit_mode: str, prompt: str,
                      image_list: list = None, negative_prompt: str = None,
                      mode: str = "std", duration: str = "5",
                      model_name: str = "kling-v1-6"):
    """
    步骤4: 创建多模态视频编辑任务
    
    接口: POST /kling/v1/videos/multi-elements
    参数:
        - model_name: 模型名称 (可选)，默认 kling-v1-6
        - session_id: 会话ID (必须)
        - edit_mode: 操作类型 (必须)
            - addition: 增加元素
            - swap: 替换元素
            - removal: 删除元素
        - image_list: 参考图像列表 (根据 edit_mode)
            - addition: 必填，1-2张图片
            - swap: 必填，1张图片
            - removal: 无需填写
        - prompt: 正向文本提示词 (必须)，不超过2500字符
            - 使用 <<<video_1>>> 指代视频
            - 使用 <<<image_1>>> 指代图片
        - negative_prompt: 负向文本提示词 (可选)
        - mode: 生成模式 (可选)，std/pro
        - duration: 视频时长 (可选)，5/10秒
    返回:
        - task_id: 任务ID
    """
    url = f"{BASE_URL}/kling/v1/videos/multi-elements"
    print(f"\n[步骤 4] 创建多模态视频编辑任务")
    print(f"请求地址: POST {url}")
    
    payload = {
        "model_name": model_name,
        "session_id": session_id,
        "edit_mode": edit_mode,
        "prompt": prompt,
        "mode": mode,
        "duration": duration
    }
    
    if image_list:
        payload["image_list"] = image_list
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
            print(f"✓ 任务创建成功，task_id: {task_id}")
        else:
            print(f"未能获取 task_id: {data}")
        
        return task_id
        
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def step5_query_task(task_id: str, max_retries: int = 60, interval: int = 10):
    """
    步骤5: 查询多模态视频编辑任务状态
    
    接口: GET /kling/v1/videos/multi-elements/:task_id
    响应:
        - data.task_id: 任务ID
        - data.task_status: 任务状态
        - data.task_status_msg: 任务状态信息
        - data.task_result.videos[]: 生成的视频列表
            - id: 视频ID
            - session_id: 会话ID
            - url: 视频URL
            - duration: 视频时长
    """
    url = f"{BASE_URL}/kling/v1/videos/multi-elements/{task_id}"
    print(f"\n[步骤 5] 查询任务状态")
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
                            print(f"✓ 视频编辑完成！")
                            print(f"  - 视频ID: {video.get('id')}")
                            print(f"  - 会话ID: {video.get('session_id')}")
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


def step_clear_selection(session_id: str):
    """
    清除视频选区
    
    接口: POST /kling/v1/videos/multi-elements/clear-selection
    """
    url = f"{BASE_URL}/kling/v1/videos/multi-elements/clear-selection"
    print(f"\n[辅助] 清除视频选区")
    print(f"请求地址: POST {url}")
    
    payload = {"session_id": session_id}
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                print("✓ 选区已清除")
                return True
        
        print(f"清除失败: {response.text}")
        return False
        
    except Exception as e:
        print(f"请求异常: {e}")
        return False


def step_delete_selection(session_id: str, frame_index: int, points: list):
    """
    删减视频选区
    
    接口: POST /kling/v1/videos/multi-elements/delete-selection
    """
    url = f"{BASE_URL}/kling/v1/videos/multi-elements/delete-selection"
    print(f"\n[辅助] 删减视频选区")
    print(f"请求地址: POST {url}")
    
    payload = {
        "session_id": session_id,
        "frame_index": frame_index,
        "points": points
    }
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                print("✓ 选区已删减")
                return True
        
        print(f"删减失败: {response.text}")
        return False
        
    except Exception as e:
        print(f"请求异常: {e}")
        return False


def test_addition_mode():
    """测试增加元素模式"""
    print("=" * 60)
    print("可灵 Kling 多模态视频编辑 - 增加元素 (Addition)")
    print("=" * 60)
    
    # 步骤1: 初始化视频
    init_result = step1_init_selection(video_url=TEST_VIDEO_URL)
    if not init_result:
        print("\n初始化失败，测试终止。")
        return
    
    session_id = init_result.get("session_id")
    
    # 步骤2: 可选 - 添加选区（标记要添加元素的位置）
    # step2_add_selection(session_id, frame_index=0, points=[{"x": 0.5, "y": 0.5}])
    
    # 步骤3: 可选 - 预览选区
    # step3_preview_selection(session_id)
    
    # 步骤4: 创建增加元素任务
    task_id = step4_create_task(
        session_id=session_id,
        edit_mode="addition",
        image_list=[{"image": TEST_IMAGE_URL}],
        prompt="基于<<<video_1>>>中的原始内容，以自然生动的方式，将<<<image_1>>>中的猫咪，融入<<<video_1>>>的画面右侧",
        negative_prompt="模糊, 变形",
        mode="std",
        duration="5"
    )
    
    if not task_id:
        print("\n创建任务失败，测试终止。")
        return
    
    # 步骤5: 查询任务状态
    video_url = step5_query_task(task_id)
    
    if video_url:
        print("\n" + "=" * 60)
        print("测试成功！")
        print(f"编辑后的视频: {video_url}")
        print("=" * 60)


def test_swap_mode():
    """测试替换元素模式"""
    print("=" * 60)
    print("可灵 Kling 多模态视频编辑 - 替换元素 (Swap)")
    print("=" * 60)
    
    # 步骤1: 初始化视频
    init_result = step1_init_selection(video_url=TEST_VIDEO_URL)
    if not init_result:
        print("\n初始化失败，测试终止。")
        return
    
    session_id = init_result.get("session_id")
    
    # 步骤2: 添加选区（标记要替换的元素）
    step2_add_selection(session_id, frame_index=0, points=[{"x": 0.5, "y": 0.5}])
    
    # 步骤3: 预览选区
    step3_preview_selection(session_id)
    
    # 步骤4: 创建替换元素任务
    task_id = step4_create_task(
        session_id=session_id,
        edit_mode="swap",
        image_list=[{"image": TEST_IMAGE_URL}],
        prompt="使用<<<image_1>>>中的新角色，替换<<<video_1>>>中标记的人物",
        mode="std",
        duration="5"
    )
    
    if not task_id:
        print("\n创建任务失败，测试终止。")
        return
    
    # 步骤5: 查询任务状态
    video_url = step5_query_task(task_id)
    
    if video_url:
        print("\n" + "=" * 60)
        print("测试成功！")
        print(f"编辑后的视频: {video_url}")
        print("=" * 60)


def test_removal_mode():
    """测试删除元素模式"""
    print("=" * 60)
    print("可灵 Kling 多模态视频编辑 - 删除元素 (Removal)")
    print("=" * 60)
    
    # 步骤1: 初始化视频
    init_result = step1_init_selection(video_url=TEST_VIDEO_URL)
    if not init_result:
        print("\n初始化失败，测试终止。")
        return
    
    session_id = init_result.get("session_id")
    
    # 步骤2: 添加选区（标记要删除的元素）
    step2_add_selection(session_id, frame_index=0, points=[{"x": 0.5, "y": 0.5}])
    
    # 步骤3: 预览选区
    step3_preview_selection(session_id)
    
    # 步骤4: 创建删除元素任务（无需 image_list）
    task_id = step4_create_task(
        session_id=session_id,
        edit_mode="removal",
        prompt="删除<<<video_1>>>中标记的人物",
        mode="std",
        duration="5"
    )
    
    if not task_id:
        print("\n创建任务失败，测试终止。")
        return
    
    # 步骤5: 查询任务状态
    video_url = step5_query_task(task_id)
    
    if video_url:
        print("\n" + "=" * 60)
        print("测试成功！")
        print(f"编辑后的视频: {video_url}")
        print("=" * 60)


def test_init_only():
    """仅测试初始化接口"""
    print("=" * 60)
    print("测试初始化待编辑视频接口")
    print("=" * 60)
    
    init_result = step1_init_selection(video_url=TEST_VIDEO_URL)
    
    if init_result:
        print(f"\n✓ 初始化成功")
        print(f"  session_id: {init_result.get('session_id')}")
    else:
        print("\n✗ 初始化失败")


if __name__ == "__main__":
    # 选择要运行的测试
    
    # 1. 测试增加元素模式
    test_addition_mode()
    
    # 2. 测试替换元素模式
    # test_swap_mode()
    
    # 3. 测试删除元素模式
    # test_removal_mode()
    
    # 4. 仅测试初始化接口
    # test_init_only()
