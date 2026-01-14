import requests

url = "https://www.ezmodel.cloud/v1/video/generations"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}
data = {
    "model": "sora-2",
    "prompt": "一只金毛寻回犬在草地上奔跑",
    "size": "1024x1024"
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
