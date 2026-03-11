"""
可灵主体 API 测试脚本（重构版）

核心特性：
1) 每次请求前都基于 AccessKey + SecretKey 动态生成 JWT API Token
2) 覆盖主体文档主要能力：
   - 查询官方主体（列表）
   - 查询自定义主体（列表）
   - 查询自定义主体（单个）
   - 创建图片定制主体
   - 创建视频定制主体
   - 删除自定义主体

文档参考：
https://app.klingai.com/cn/dev/document-api/apiReference/model/element

默认域名：
https://api-beijing.klingai.com

快速示例：
python kling.py official-list --page-num 1 --page-size 10
python kling.py create-image --name "测试角色" --description "图片主体测试" --frontal-image "https://xx/0.png" --refer-image "https://xx/1.png"
python kling.py create-video --name "测试角色" --description "视频主体测试" --video-url "https://xx/a.mp4"
python kling.py custom-list --page-num 1 --page-size 10
python kling.py custom-get --id "task_id_or_external_task_id"
python kling.py delete --element-id "123456"

鉴权来源优先级：
--ak/--sk > 硬编码常量 > 环境变量 KLING_ACCESS_KEY / KLING_SECRET_KEY
"""

import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from pathlib import Path
import requests


# 你可直接硬编码用于临时测试。
ACCESS_KEY = "AMgaGnNDLCdbQpftfYrGLfD4DmpGRRYp"
CODED_SECRET_KEY = "DCyy8rL9pTh4ynB3Ntnm8rHGybgtFBJH"

DEFAULT_BASE_URL = os.getenv("KLING_API_BASE_URL", "https://api.klingai.com")
DEFAULT_LOG_FILE = "kling.log"

logger = logging.getLogger("kling")


def setup_logging(log_file: str, log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def generate_api_token(access_key: str, secret_key: str, expire_seconds: int = 1800) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": access_key,
        "exp": now + expire_seconds,
        "nbf": now - 5,
    }

    header_seg = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_seg = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_seg}.{payload_seg}".encode("utf-8")
    sign = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sign_seg = b64url_encode(sign)
    return f"{header_seg}.{payload_seg}.{sign_seg}"


class KlingClient:
    def __init__(self, base_url: str, access_key: str, secret_key: str, expire_seconds: int = 1800) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.expire_seconds = max(30, expire_seconds)

    def _build_headers(self) -> Dict[str, str]:
        token = generate_api_token(self.access_key, self.secret_key, self.expire_seconds)
        return {
            "Authorization": f"Bearer {token}",
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
        logger.debug("request: method=%s url=%s params=%s body=%s", method, url, params, body)
        resp = requests.request(
            method=method,
            url=url,
            headers=self._build_headers(),
            params=params,
            json=body,
            timeout=60,
        )

        try:
            payload = resp.json()
        except Exception as exc:
            raw = resp.text
            logger.error("response(non-json): status=%s raw=%s", resp.status_code, raw[:1000])
            raise RuntimeError(f"响应不是 JSON，HTTP={resp.status_code}，raw={raw[:2000]}") from exc

        logger.debug("response: status=%s payload=%s", resp.status_code, payload)

        code = payload.get("code") if isinstance(payload, dict) else None
        if resp.status_code != 200 or code not in (None, 0):
            message = payload.get("message", "") if isinstance(payload, dict) else ""
            request_id = payload.get("request_id") if isinstance(payload, dict) else None
            hint = ""
            if code == 1002:
                hint = "；提示：access key not found 通常表示 iss 不是有效 AK，或 SK 与 AK 不匹配"
            if code == 1200:
                hint = "；提示：请求参数非法，请检查 path/query/body 字段"
            raise RuntimeError(
                f"HTTP {resp.status_code}, code={code}, message={message}, request_id={request_id}{hint}"
            )

        return payload

    def official_list(self, page_num: int, page_size: int) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/v1/general/advanced-presets-elements",
            params={"pageNum": page_num, "pageSize": page_size},
        )

    def custom_list(self, page_num: int, page_size: int) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/v1/general/advanced-custom-elements",
            params={"pageNum": page_num, "pageSize": page_size},
        )

    def custom_get(self, id_value: str) -> Dict[str, Any]:
        # 文档路径：GET /v1/general/advanced-custom-elements/{id}
        return self._request("GET", f"/v1/general/advanced-custom-elements/{id_value}")

    def create_image_element(
        self,
        name: str,
        description: str,
        frontal_image: str,
        refer_images: List[str],
        voice_id: Optional[str],
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
                "refer_images": [{"image_url": x} for x in refer_images],
            },
        }
        if voice_id:
            body["element_voice_id"] = voice_id
        if tag_ids:
            body["tag_list"] = [{"tag_id": t} for t in tag_ids]
        if callback_url:
            body["callback_url"] = callback_url
        if external_task_id:
            body["external_task_id"] = external_task_id

        return self._request("POST", "/v1/general/advanced-custom-elements", body=body)

    def create_video_element(
        self,
        name: str,
        description: str,
        video_url: str,
        voice_id: Optional[str],
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
        if voice_id:
            body["element_voice_id"] = voice_id
        if tag_ids:
            body["tag_list"] = [{"tag_id": t} for t in tag_ids]
        if callback_url:
            body["callback_url"] = callback_url
        if external_task_id:
            body["external_task_id"] = external_task_id

        return self._request("POST", "/v1/general/advanced-custom-elements", body=body)

    def delete_element(self, element_id: str) -> Dict[str, Any]:
        return self._request("POST", "/v1/general/delete-elements", body={"element_id": element_id})


def validate_page(page_num: int, page_size: int) -> None:
    if not (1 <= page_num <= 1000):
        raise ValueError("page-num 范围必须是 1~1000")
    if not (1 <= page_size <= 500):
        raise ValueError("page-size 范围必须是 1~500")


def build_client(args: argparse.Namespace) -> KlingClient:
    ak_source = "--ak" if args.ak else ("hardcoded ACCESS_KEY" if ACCESS_KEY else "KLING_ACCESS_KEY")
    sk_source = "--sk" if args.sk else ("hardcoded CODED_SECRET_KEY" if CODED_SECRET_KEY else "KLING_SECRET_KEY")

    access_key = (args.ak or ACCESS_KEY or os.getenv("KLING_ACCESS_KEY", "")).strip()
    secret_key = (args.sk or CODED_SECRET_KEY or os.getenv("KLING_SECRET_KEY", "")).strip()

    if not access_key or not secret_key:
        raise ValueError(
            "缺少 AK/SK。请通过 --ak/--sk 传入，或填写脚本中的 ACCESS_KEY/CODED_SECRET_KEY，"
            "或设置环境变量 KLING_ACCESS_KEY/KLING_SECRET_KEY"
        )

    if args.debug_auth:
        now = int(time.time())
        logger.info("[DEBUG] auth source: AK=%s, SK=%s", ak_source, sk_source)
        logger.info("[DEBUG] base_url=%s", args.base_url)
        logger.info("[DEBUG] iss(access_key)=%s", access_key)
        logger.info("[DEBUG] ak_len=%s, sk_len=%s", len(access_key), len(secret_key))
        logger.info("[DEBUG] jwt_time_window: nbf=%s, exp=%s, now=%s", now - 5, now + max(30, args.exp_seconds), now)

    return KlingClient(
        base_url=args.base_url,
        access_key=access_key,
        secret_key=secret_key,
        expire_seconds=args.exp_seconds,
    )
# ====== 插入到工具函数区域（例如 print_json 上方） ======
def image_file_to_base64(path_str: str) -> str:
    p = Path(path_str).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise ValueError(f"图片文件不存在: {p}")
    data = p.read_bytes()
    if len(data) > 10 * 1024 * 1024:
        raise ValueError(f"图片超过10MB: {p}")
    return base64.b64encode(data).decode("utf-8")


def normalize_image_input(url_value: Optional[str], file_value: Optional[str]) -> str:
    """
    二选一：
    - 传 url_value: 直接用 URL
    - 传 file_value: 读取本地文件并转 Base64
    """
    if url_value and file_value:
        raise ValueError("同一个图片参数不能同时传 URL 和本地文件路径")
    if file_value:
        return image_file_to_base64(file_value)
    if url_value:
        return url_value
    raise ValueError("缺少图片输入，请传 URL 或本地文件路径")


def video_file_to_base64(path_str: str) -> str:
    p = Path(path_str).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise ValueError(f"视频文件不存在: {p}")

    ext = p.suffix.lower()
    if ext not in {".mp4", ".mov"}:
        raise ValueError(f"视频格式不支持: {p.name}，仅支持 .mp4/.mov")

    data = p.read_bytes()
    if len(data) > 200 * 1024 * 1024:
        raise ValueError(f"视频超过200MB: {p}")
    return base64.b64encode(data).decode("utf-8")


def normalize_video_input(url_value: Optional[str], file_value: Optional[str]) -> str:
    """
    二选一：
    - 传 url_value: 直接用 URL
    - 传 file_value: 读取本地文件并转 Base64
    """
    if url_value and file_value:
        raise ValueError("同一个视频参数不能同时传 URL 和本地文件路径")
    if file_value:
        return video_file_to_base64(file_value)
    if url_value:
        return url_value
    raise ValueError("缺少视频输入，请传 URL 或本地文件路径")

def print_json(obj: Dict[str, Any]) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    print(text)
    logger.info("API 响应:\n%s", text)


def main() -> int:
    parser = argparse.ArgumentParser(description="可灵主体 API 全功能测试脚本")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API 域名")
    parser.add_argument("--ak", help="AccessKey")
    parser.add_argument("--sk", help="SecretKey")
    parser.add_argument("--exp-seconds", type=int, default=1800, help="JWT 有效期秒数")
    parser.add_argument("--debug-auth", action="store_true", help="打印鉴权来源和JWT时间窗（不打印SK内容）")
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE, help="日志文件路径")
    parser.add_argument("--log-level", default="INFO", help="日志级别：DEBUG/INFO/WARNING/ERROR")

    subparsers = parser.add_subparsers(dest="cmd", required=True)

    p_official = subparsers.add_parser("official-list", help="查询官方主体（列表）")
    p_official.add_argument("--page-num", type=int, default=1)
    p_official.add_argument("--page-size", type=int, default=30)

    p_custom_list = subparsers.add_parser("custom-list", help="查询自定义主体（列表）")
    p_custom_list.add_argument("--page-num", type=int, default=1)
    p_custom_list.add_argument("--page-size", type=int, default=30)

    p_custom_get = subparsers.add_parser("custom-get", help="查询自定义主体（单个）")
    p_custom_get.add_argument("--id", required=True, help="task_id 或 external_task_id")

    p_create_image = subparsers.add_parser("create-image", help="创建图片定制主体")
    p_create_image.add_argument("--name", required=True, help="主体名称")
    p_create_image.add_argument("--description", required=True, help="主体描述")

    # 正面图：支持 URL 或本地文件（二选一）
    p_create_image.add_argument("--frontal-image", help="正面参考图 URL")
    p_create_image.add_argument("--frontal-image-file", help="正面参考图本地文件路径")

    # 参考图：支持 URL 列表 或 本地文件列表（二选一）
    p_create_image.add_argument("--refer-image", action="append", default=[], help="其他参考图 URL，可多次传")
    p_create_image.add_argument("--refer-image-file", action="append", default=[], help="其他参考图本地文件路径，可多次传")

    p_create_image.add_argument("--voice-id", help="音色 ID")
    p_create_image.add_argument("--tag-id", action="append", default=[], help="标签 ID，可多次传")
    p_create_image.add_argument("--callback-url", help="回调地址")
    p_create_image.add_argument("--external-task-id", help="自定义任务 ID")

    p_create_video = subparsers.add_parser("create-video", help="创建视频定制主体")
    p_create_video.add_argument("--name", required=True, help="主体名称")
    p_create_video.add_argument("--description", required=True, help="主体描述")
    p_create_video.add_argument("--video-url", help="参考视频 URL")
    p_create_video.add_argument("--video-file", help="参考视频本地文件路径（.mp4/.mov）")
    p_create_video.add_argument("--voice-id", help="音色 ID")
    p_create_video.add_argument("--tag-id", action="append", default=[], help="标签 ID，可多次传")
    p_create_video.add_argument("--callback-url", help="回调地址")
    p_create_video.add_argument("--external-task-id", help="自定义任务 ID")

    p_delete = subparsers.add_parser("delete", help="删除自定义主体")
    p_delete.add_argument("--element-id", required=True, help="主体 ID")

    args = parser.parse_args()

    try:
        setup_logging(args.log_file, args.log_level)
        logger.info("脚本启动: cmd=%s base_url=%s", args.cmd, args.base_url)
        client = build_client(args)

        if args.cmd == "official-list":
            validate_page(args.page_num, args.page_size)
            print_json(client.official_list(args.page_num, args.page_size))
            return 0

        if args.cmd == "custom-list":
            validate_page(args.page_num, args.page_size)
            print_json(client.custom_list(args.page_num, args.page_size))
            return 0

        if args.cmd == "custom-get":
            print_json(client.custom_get(args.id))
            return 0

        if args.cmd == "create-image":
            frontal_value = normalize_image_input(args.frontal_image, args.frontal_image_file)

            if args.refer_image and args.refer_image_file:
                raise ValueError("--refer-image 和 --refer-image-file 不能同时使用")

            if args.refer_image_file:
                refer_values = [image_file_to_base64(p) for p in args.refer_image_file]
            else:
                refer_values = args.refer_image

            if len(refer_values) < 1:
                raise ValueError("至少需要 1 张参考图（--refer-image 或 --refer-image-file）")

            print_json(
                client.create_image_element(
                    name=args.name,
                    description=args.description,
                    frontal_image=frontal_value,
                    refer_images=refer_values,
                    voice_id=args.voice_id,
                    tag_ids=args.tag_id,
                    callback_url=args.callback_url,
                    external_task_id=args.external_task_id,
                )
            )
            return 0

        if args.cmd == "create-video":
            video_value = normalize_video_input(args.video_url, args.video_file)
            print_json(
                client.create_video_element(
                    name=args.name,
                    description=args.description,
                    video_url=video_value,
                    voice_id=args.voice_id,
                    tag_ids=args.tag_id,
                    callback_url=args.callback_url,
                    external_task_id=args.external_task_id,
                )
            )
            return 0

        if args.cmd == "delete":
            print_json(client.delete_element(args.element_id))
            return 0

        raise ValueError(f"不支持的命令: {args.cmd}")
    except Exception as exc:
        logger.exception("脚本执行失败")
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
