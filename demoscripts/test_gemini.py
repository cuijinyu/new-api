import requests
import json

url = "https://www.ezmodel.cloud/v1beta/models/gemini-3-pro-image-preview:generateContent"

payload = {
    "contents": [
        {
            "parts": [
                {
                    "text": "Create a picture of a nano banana dish in a fancy restaurant with a Gemini theme"
                }
            ]
        }
    ],
    "generationConfig": {
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
        "Authorization": "Bearer sk-"
    }
)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")

if response.status_code == 200:
    print("✅ 请求成功！")
else:
    print("❌ 请求失败")
