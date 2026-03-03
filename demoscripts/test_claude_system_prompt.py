import os
from openai import OpenAI

# 配置你的 API 地址和 Key
# 可以在环境变量中设置，或者直接在这里修改默认值
API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:3000/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "sk-xxx") # 替换为你的测试 key
MODEL = os.getenv("MODEL", "claude-3-haiku-20240307") # 你可以换成你要测试的 claude 模型，比如 claude-3-5-sonnet-20240620

client = OpenAI(
    api_key=API_KEY,
    base_url=API_BASE
)

def test_claude_system_prompt():
    print(f"Testing model: {MODEL}")
    print(f"API Base: {API_BASE}")
    print("Sending request with a strict system prompt...\n")
    
    # 我们设置一个非常明确的 System Prompt，以便于验证它是否生效
    system_prompt = "你是一个只会用猫叫声（喵喵喵）回复的机器人。无论用户问什么，你都只能回复'喵喵喵'，不能包含任何人类语言。"
    user_prompt = "请问中国首都是哪里？"
    
    print(f"System Prompt: {system_prompt}")
    print(f"User Prompt: {user_prompt}\n")
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1
        )
        
        reply = response.choices[0].message.content
        print("--- Response ---")
        print(reply)
        print("----------------\n")
        
        # 验证回复是否符合 system prompt 的要求
        if "喵" in reply and "北京" not in reply:
            print("✅ 测试成功: 模型严格遵循了 System Prompt 的指令。")
        else:
            print("❌ 测试失败/警告: 模型似乎没有遵循 System Prompt，或者 System Prompt 未生效。")
            
    except Exception as e:
        print(f"❌ 请求发生错误: {e}")

if __name__ == "__main__":
    test_claude_system_prompt()
