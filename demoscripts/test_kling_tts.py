"""
可灵 Kling 语音合成 (TTS) 接口测试脚本

测试流程：
1. 基础 TTS 测试 - 使用默认参数生成语音
2. 完整参数测试 - 调整语速和音量
3. 长文本测试 - 测试较长文本的合成

参考文档: web/src/pages/Documentation/content/kling-tts.md

计费说明: 按调用次数计费，每次 0.05 元，与文本长度无关
"""

import requests
import os
import json

# 配置信息
BASE_URL = os.getenv("KLING_BASE_URL", "https://www.ezmodel.cloud")
API_KEY = os.getenv("EZMODEL_API_KEY", "YOUR_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 测试用的音色 ID
# 中文音色: 阳光少年 (genshin_vindi2), 语种: zh
# 英文音色: Sunny (genshin_vindi2), 语种: en
TEST_VOICE_ID_ZH = "genshin_vindi2"
TEST_VOICE_ID_EN = "genshin_vindi2"
TEST_VOICE_ID = TEST_VOICE_ID_ZH  # 默认使用中文音色


def test_tts_basic(text: str, voice_id: str):
    """
    基础 TTS 测试 - 使用默认参数
    
    接口: POST /kling/v1/audio/tts
    参数:
        - text: 待合成的文本内容 (必须，最大 1000 字符)
        - voice_id: 音色ID (必须)
    返回:
        - code: 错误码 (0 表示成功)
        - message: 错误信息
        - request_id: 请求ID
        - data.task_result.audios[].id: 生成音频的ID
        - data.task_result.audios[].url: 生成音频的URL
        - data.task_result.audios[].duration: 音频时长 (秒)
    """
    url = f"{BASE_URL}/kling/v1/audio/tts"
    print(f"\n[基础 TTS 测试]")
    print(f"请求地址: POST {url}")
    
    payload = {
        "text": text,
        "voice_id": voice_id
    }
    
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"请求失败: {response.text}")
            return None
        
        data = response.json()
        print(f"响应数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        # 解析响应
        if data.get("code") != 0:
            print(f"✗ 业务错误: {data.get('message')}")
            return None
        
        task_data = data.get("data", {})
        task_result = task_data.get("task_result", {})
        audios = task_result.get("audios", [])
        
        if audios:
            audio = audios[0]
            audio_id = audio.get("id")
            audio_url = audio.get("url")
            duration = audio.get("duration")
            
            print(f"✓ TTS 生成成功！")
            print(f"  - 音频ID: {audio_id}")
            print(f"  - 音频URL: {audio_url}")
            print(f"  - 时长: {duration} 秒")
            
            return audio_url
        else:
            print(f"✗ 未获取到音频数据")
            return None
        
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def test_tts_full_params(text: str, voice_id: str, voice_speed: float = 1.0, voice_language: str = "zh"):
    """
    完整参数 TTS 测试 - 自定义语速和语种
    
    接口: POST /kling/v1/audio/tts
    参数:
        - text: 待合成的文本内容 (必须，最大 1000 字符)
        - voice_id: 音色ID (必须)
        - voice_speed: 语速 [0.8, 2.0]，1.0 为正常语速 (可选)
        - voice_language: 语种 zh/en，默认 zh (可选)
    """
    url = f"{BASE_URL}/kling/v1/audio/tts"
    print(f"\n[完整参数 TTS 测试]")
    print(f"请求地址: POST {url}")
    
    payload = {
        "text": text,
        "voice_id": voice_id,
        "voice_speed": voice_speed,
        "voice_language": voice_language
    }
    
    print(f"请求参数: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"请求失败: {response.text}")
            return None
        
        data = response.json()
        print(f"响应数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        # 解析响应
        if data.get("code") != 0:
            print(f"✗ 业务错误: {data.get('message')}")
            return None
        
        task_data = data.get("data", {})
        task_result = task_data.get("task_result", {})
        audios = task_result.get("audios", [])
        
        if audios:
            audio = audios[0]
            audio_id = audio.get("id")
            audio_url = audio.get("url")
            duration = audio.get("duration")
            
            print(f"✓ TTS 生成成功！")
            print(f"  - 音频ID: {audio_id}")
            print(f"  - 音频URL: {audio_url}")
            print(f"  - 时长: {duration} 秒")
            print(f"  - 语速: {voice_speed}")
            print(f"  - 语种: {voice_language}")
            
            return audio_url
        else:
            print(f"✗ 未获取到音频数据")
            return None
        
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def test_tts_error_handling():
    """
    错误处理测试 - 测试各种错误情况
    """
    url = f"{BASE_URL}/kling/v1/audio/tts"
    print(f"\n[错误处理测试]")
    
    # 测试1: 缺少 text 参数
    print("\n--- 测试1: 缺少 text 参数 ---")
    payload = {"voice_id": TEST_VOICE_ID}
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"异常: {e}")
    
    # 测试2: 缺少 voice_id 参数
    print("\n--- 测试2: 缺少 voice_id 参数 ---")
    payload = {"text": "测试文本"}
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"异常: {e}")
    
    # 测试3: voice_speed 超出范围
    print("\n--- 测试3: voice_speed 超出范围 (3.0) ---")
    payload = {
        "text": "测试文本",
        "voice_id": TEST_VOICE_ID,
        "voice_speed": 3.0  # 超出 [0.8, 2.0] 范围
    }
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"异常: {e}")
    
    # 测试4: voice_language 无效值
    print("\n--- 测试4: voice_language 无效值 (fr) ---")
    payload = {
        "text": "测试文本",
        "voice_id": TEST_VOICE_ID,
        "voice_language": "fr"  # 只支持 zh/en
    }
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        print(f"响应: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"异常: {e}")


def test_tts_full_flow():
    """完整测试流程"""
    print("=" * 60)
    print("可灵 Kling 语音合成 (TTS) 接口测试")
    print("=" * 60)
    print(f"API 地址: {BASE_URL}")
    print(f"音色 ID: {TEST_VOICE_ID}")
    print("=" * 60)
    
    # 测试1: 基础 TTS - 短文本
    print("\n" + "-" * 40)
    print("测试1: 基础 TTS - 短文本")
    print("-" * 40)
    audio_url_1 = test_tts_basic(
        text="你好，欢迎使用可灵AI语音合成服务。",
        voice_id=TEST_VOICE_ID
    )
    
    # 测试2: 完整参数 - 快速语速
    print("\n" + "-" * 40)
    print("测试2: 完整参数 - 快速语速 (1.5x)")
    print("-" * 40)
    audio_url_2 = test_tts_full_params(
        text="这是一段快速播放的测试语音，语速设置为1.5倍。",
        voice_id=TEST_VOICE_ID,
        voice_speed=1.5,
        voice_language="zh"
    )
    
    # 测试3: 完整参数 - 慢速语速
    print("\n" + "-" * 40)
    print("测试3: 完整参数 - 慢速语速 (0.8x)")
    print("-" * 40)
    audio_url_3 = test_tts_full_params(
        text="这是一段慢速播放的测试语音，语速设置为0.8倍。",
        voice_id=TEST_VOICE_ID,
        voice_speed=0.8,
        voice_language="zh"
    )
    
    # 测试4: 完整参数 - 英文语种
    print("\n" + "-" * 40)
    print("测试4: 完整参数 - 英文语种")
    print("-" * 40)
    audio_url_4 = test_tts_full_params(
        text="Hello, this is a test for English text-to-speech.",
        voice_id=TEST_VOICE_ID_EN,  # 使用英文音色
        voice_speed=1.0,
        voice_language="en"
    )
    
    # 测试5: 长文本测试
    print("\n" + "-" * 40)
    print("测试5: 长文本测试")
    print("-" * 40)
    long_text = """
    人工智能正在改变我们的生活方式。从智能手机上的语音助手，到自动驾驶汽车，
    再到医疗诊断系统，AI技术已经渗透到各行各业。语音合成技术作为人工智能的重要分支，
    能够将文字转换为自然流畅的语音，为用户提供更加便捷的交互体验。
    可灵AI语音合成服务采用先进的深度学习技术，支持多种音色选择，
    能够生成高质量、自然流畅的语音内容。无论是新闻播报、有声读物、
    还是智能客服，都能满足您的需求。
    """.strip()
    
    audio_url_5 = test_tts_basic(
        text=long_text,
        voice_id=TEST_VOICE_ID
    )
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    results = [
        ("基础 TTS - 短文本", audio_url_1),
        ("快速语速 (1.5x)", audio_url_2),
        ("慢速语速 (0.8x)", audio_url_3),
        ("英文语种", audio_url_4),
        ("长文本测试", audio_url_5),
    ]
    
    success_count = 0
    for name, url in results:
        status = "✓ 成功" if url else "✗ 失败"
        if url:
            success_count += 1
        print(f"  {status}: {name}")
        if url:
            print(f"         URL: {url[:80]}...")
    
    print("-" * 60)
    print(f"总计: {success_count}/{len(results)} 测试通过")
    print("=" * 60)


def test_tts_single():
    """单次 TTS 测试 - 用于快速验证"""
    print("=" * 60)
    print("单次 TTS 测试")
    print("=" * 60)
    
    audio_url = test_tts_basic(
        text="你好，这是一个简单的语音合成测试。",
        voice_id=TEST_VOICE_ID
    )
    
    if audio_url:
        print(f"\n✓ 测试成功！")
        print(f"音频 URL: {audio_url}")
    else:
        print(f"\n✗ 测试失败！")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "single":
            # 单次测试
            test_tts_single()
        elif cmd == "error":
            # 错误处理测试
            test_tts_error_handling()
        elif cmd == "full":
            # 完整测试
            test_tts_full_flow()
        else:
            print(f"未知命令: {cmd}")
            print("可用命令: single, error, full")
    else:
        # 默认运行完整测试
        test_tts_full_flow()
