import argparse
import json
import time
import httpx

class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"

def print_header(text: str) -> None:
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 72}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 72}{Colors.ENDC}\n")

def print_info(text: str) -> None:
    print(f"{Colors.OKBLUE}[INFO] {text}{Colors.ENDC}")

def print_success(text: str) -> None:
    print(f"{Colors.OKGREEN}[OK] {text}{Colors.ENDC}")

def print_warning(text: str) -> None:
    print(f"{Colors.WARNING}[WARN] {text}{Colors.ENDC}")

def print_fail(text: str) -> None:
    print(f"{Colors.FAIL}[FAIL] {text}{Colors.ENDC}")

def test_kling_multi_prompt(base_url: str, api_key: str, duration_val: str) -> None:
    print_header(f"Testing Kling Multi-Prompt with Duration: {duration_val}")
    
    url = f"{base_url.rstrip('/')}/kling/v1/videos/omni-video"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "kling-v3-omni",
        "multi_prompt": [
            {
                "index": 1,
                "duration": duration_val,
                "prompt": "Scene 1 Hospital hallway. Pale blue light. Machines beeping faintly behind a closed door. She stands outside his room. He’s pale but conscious."
            },
            {
                "index": 2,
                "duration": duration_val,
                "prompt": "Scene 2 She takes off the necklace he gave her. Places it in his hand. “This is goodbye.” He stares at her, devastated but too weak to argue."
            },
            {
                "index": 3,
                "duration": duration_val,
                "prompt": "Scene 3 She leans close, whispering: “I can’t watch you fade.” Tears fall onto the sheets. He closes his eyes."
            },
            {
                "index": 4,
                "duration": duration_val,
                "prompt": "Scene 4 — Twist Next morning. Sunlight floods the room. He wakes. She’s not gone. She’s asleep in the chair beside him. Hospital bracelet on her wrist. Camera pans. Two patient charts clipped at the end of the bed. Both undergoing treatment. She opens her eyes. Smiles faintly. “I meant goodbye to the life we had before this.” She squeezes his hand. “We fight together.” Machines steady. Music swells."
            }
        ],
        "mode": "std",
        "sound": "on",
        "aspect_ratio": "16:9"
    }

    print_info(f"Sending request to: {url}")
    print_info(f"Payload multi_prompt duration set to: {duration_val}")
    
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            
            print_info(f"Status Code: {response.status_code}")
            try:
                resp_json = response.json()
                print_info(f"Response Body: {json.dumps(resp_json, indent=2, ensure_ascii=False)}")
                
                if response.status_code == 200:
                    print_success(f"Request succeeded with duration {duration_val}!")
                else:
                    print_warning(f"Request failed with duration {duration_val}.")
            except Exception as e:
                print_fail(f"Failed to parse JSON response: {response.text}")
                
    except Exception as e:
        print_fail(f"Request error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Test Kling Multi-Prompt Duration")
    parser.add_argument("--url", type=str, default="http://localhost:3000", help="API Base URL")
    parser.add_argument("--key", type=str, required=True, help="API Key")
    parser.add_argument("--duration", type=str, default="2", help="Duration to test for each scene (e.g., 2 or 3)")
    
    args = parser.parse_args()
    
    test_kling_multi_prompt(args.url, args.key, args.duration)

if __name__ == "__main__":
    main()
