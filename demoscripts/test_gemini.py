import requests
import json

url = "https://www.ezmodel.cloud/v1beta/models/gemini-2.5-flash-image:generateContent"

payload = {
    "contents": [
        {
            "parts": [
                {
                    "text": "一只在森林里奔跑的赛博朋克风格的狐狸"
                }
            ]
        }
    ],
    "generationConfig": {
        "responseModalities": ["IMAGE", "TEXT"],
        "imageConfig": {
            "aspectRatio": "16:9",
            "imageSize": "2K"
        }
    }
}

response = requests.post(
    url, 
    json=payload,
    headers={
        "Authorization": "Bearer YOUR_API_KEY"
    }
)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")

if response.status_code == 200:
    print("✅ 请求成功！")
else:
    print("❌ 请求失败")
