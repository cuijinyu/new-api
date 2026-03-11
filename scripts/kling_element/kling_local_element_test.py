"""
newapi 本地 Kling Element 接口测试脚本

目标：
1) 测试本地接口 /kling/v1/general/* 的连通性与返回
2) 可选校验调用前后 token usage 变化，验证是否扣费

鉴权优先级：
--token > 环境变量 NEWAPI_TOKEN

示例：
python3 kling_local_element_test.py smoke --token sk-xxx
python3 kling_local_element_test.py custom-list --page-num 1 --page-size 10
python3 kling_local_element_test.py create-image --name test --description demo \
  --frontal-image https://example.com/a.png --refer-image https://example.com/b.png
python3 kling_local_element_test.py usage-check --run smoke
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_URL = os.getenv("NEWAPI_BASE_URL", "http://localhost:3000")


class NewAPIClient:
    def __init__(self, base_url: str, token: str, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout
        if not self.token:
            raise ValueError("缺少 token，请通过 --token 或 NEWAPI_TOKEN 提供")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = requests.request(
            method=method,
            url=url,
            headers=self._headers(),
            params=params,
            json=body,
            timeout=self.timeout,
            allow_redirects=True,
        )
        try:
            payload = resp.json()
        except Exception as exc:
            raise RuntimeError(f"响应不是 JSON: status={resp.status_code}, body={resp.text[:2000]}") from exc

        return {
            "status_code": resp.status_code,
            "json": payload,
        }

    def token_usage(self) -> Dict[str, Any]:
        return self._request("GET", "/api/usage/token/")

    def custom_list(self, page_num: int, page_size: int) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/kling/v1/general/advanced-custom-elements",
            params={"pageNum": page_num, "pageSize": page_size},
        )

    def custom_get(self, task_or_external_id: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"/kling/v1/general/advanced-custom-elements/{task_or_external_id}",
        )

    def presets_list(self, page_num: int, page_size: int) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/kling/v1/general/advanced-presets-elements",
            params={"pageNum": page_num, "pageSize": page_size},
        )

    def create_image_element(
        self,
        name: str,
        description: str,
        frontal_image: str,
        refer_images: List[str],
        tag_ids: List[str],
        callback_url: Optional[str],
        external_task_id: Optional[str],
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "element_name": name,
            "element_description": description,
            "reference_type": "image_refer",
            "element_image_list": {
                "frontal_image": frontal_image,
                "refer_images": [{"image_url": u} for u in refer_images],
            },
        }
        if tag_ids:
            body["tag_list"] = [{"tag_id": t} for t in tag_ids]
        if callback_url:
            body["callback_url"] = callback_url
        if external_task_id:
            body["external_task_id"] = external_task_id

        return self._request("POST", "/kling/v1/general/advanced-custom-elements", body=body)

    def create_video_element(
        self,
        name: str,
        description: str,
        video_url: str,
        tag_ids: List[str],
        callback_url: Optional[str],
        external_task_id: Optional[str],
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "element_name": name,
            "element_description": description,
            "reference_type": "video_refer",
            "element_video_list": {
                "refer_videos": [{"video_url": video_url}],
            },
        }
        if tag_ids:
            body["tag_list"] = [{"tag_id": t} for t in tag_ids]
        if callback_url:
            body["callback_url"] = callback_url
        if external_task_id:
            body["external_task_id"] = external_task_id

        return self._request("POST", "/kling/v1/general/advanced-custom-elements", body=body)

    def delete_element(self, element_id: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/kling/v1/general/delete-elements",
            body={"element_id": element_id},
        )


def print_json(data: Dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def extract_total_used(usage_resp: Dict[str, Any]) -> Optional[int]:
    payload = usage_resp.get("json", {})
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    value = data.get("total_used")
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except Exception:
        return None


def run_smoke(client: NewAPIClient) -> int:
    print("[1/3] 调用 presets 列表")
    presets = client.presets_list(1, 2)
    print_json(presets)

    print("[2/3] 调用 custom 列表")
    custom = client.custom_list(1, 2)
    print_json(custom)

    print("[3/3] 调用 custom-get（示例 ID，可能返回未找到）")
    single = client.custom_get("842250903629086785")
    print_json(single)
    return 0


def run_usage_check(client: NewAPIClient, run_cmd: str) -> int:
    before = client.token_usage()
    before_used = extract_total_used(before)
    print("[usage before]")
    print_json(before)

    if run_cmd == "smoke":
        code = run_smoke(client)
    else:
        proc = subprocess.run(run_cmd, shell=True)
        code = proc.returncode

    after = client.token_usage()
    after_used = extract_total_used(after)
    print("[usage after]")
    print_json(after)

    if before_used is None or after_used is None:
        print("无法解析 total_used，跳过扣费差值计算")
        return code

    delta = after_used - before_used
    print(f"token total_used delta = {delta}")
    if delta == 0:
        print("结论: 本次测试未产生 token 扣费")
    else:
        print("结论: 本次测试产生了 token 扣费，请检查计费逻辑")
    return code


def build_client(args: argparse.Namespace) -> NewAPIClient:
    token = (args.token or os.getenv("NEWAPI_TOKEN", "")).strip()
    return NewAPIClient(base_url=args.base_url, token=token, timeout=args.timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description="newapi 本地 Kling Element 测试")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="本地 newapi 地址")
    parser.add_argument("--token", help="newapi token")
    parser.add_argument("--timeout", type=int, default=60, help="请求超时（秒）")

    subparsers = parser.add_subparsers(dest="cmd", required=True)

    p_smoke = subparsers.add_parser("smoke", help="冒烟测试：presets/custom-list/custom-get")
    _ = p_smoke

    p_usage = subparsers.add_parser("usage-check", help="执行一次命令并比较 token usage 前后差值")
    p_usage.add_argument("--run", default="smoke", help="运行内容：'smoke' 或 shell 命令")

    p_custom_list = subparsers.add_parser("custom-list", help="查询自定义主体列表")
    p_custom_list.add_argument("--page-num", type=int, default=1)
    p_custom_list.add_argument("--page-size", type=int, default=30)

    p_custom_get = subparsers.add_parser("custom-get", help="查询自定义主体（单个）")
    p_custom_get.add_argument("--id", required=True)

    p_presets = subparsers.add_parser("presets-list", help="查询官方主体列表")
    p_presets.add_argument("--page-num", type=int, default=1)
    p_presets.add_argument("--page-size", type=int, default=30)

    p_create_image = subparsers.add_parser("create-image", help="创建图片主体")
    p_create_image.add_argument("--name", required=True)
    p_create_image.add_argument("--description", required=True)
    p_create_image.add_argument("--frontal-image", required=True)
    p_create_image.add_argument("--refer-image", action="append", default=[], help="可多次传")
    p_create_image.add_argument("--tag-id", action="append", default=[])
    p_create_image.add_argument("--callback-url")
    p_create_image.add_argument("--external-task-id")

    p_create_video = subparsers.add_parser("create-video", help="创建视频主体")
    p_create_video.add_argument("--name", required=True)
    p_create_video.add_argument("--description", required=True)
    p_create_video.add_argument("--video-url", required=True)
    p_create_video.add_argument("--tag-id", action="append", default=[])
    p_create_video.add_argument("--callback-url")
    p_create_video.add_argument("--external-task-id")

    p_delete = subparsers.add_parser("delete", help="删除主体")
    p_delete.add_argument("--element-id", required=True)

    args = parser.parse_args()

    try:
        client = build_client(args)

        if args.cmd == "smoke":
            return run_smoke(client)

        if args.cmd == "usage-check":
            return run_usage_check(client, args.run)

        if args.cmd == "custom-list":
            print_json(client.custom_list(args.page_num, args.page_size))
            return 0

        if args.cmd == "custom-get":
            print_json(client.custom_get(args.id))
            return 0

        if args.cmd == "presets-list":
            print_json(client.presets_list(args.page_num, args.page_size))
            return 0

        if args.cmd == "create-image":
            if not args.refer_image:
                raise ValueError("至少提供一张 --refer-image")
            print_json(
                client.create_image_element(
                    name=args.name,
                    description=args.description,
                    frontal_image=args.frontal_image,
                    refer_images=args.refer_image,
                    tag_ids=args.tag_id,
                    callback_url=args.callback_url,
                    external_task_id=args.external_task_id,
                )
            )
            return 0

        if args.cmd == "create-video":
            print_json(
                client.create_video_element(
                    name=args.name,
                    description=args.description,
                    video_url=args.video_url,
                    tag_ids=args.tag_id,
                    callback_url=args.callback_url,
                    external_task_id=args.external_task_id,
                )
            )
            return 0

        if args.cmd == "delete":
            print_json(client.delete_element(args.element_id))
            return 0

        raise ValueError(f"未知命令: {args.cmd}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
