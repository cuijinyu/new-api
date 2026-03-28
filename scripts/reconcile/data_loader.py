import gzip
import os
import threading

import boto3
import botocore.config
import orjson

_thread_local = threading.local()


def get_s3_client(region, endpoint):
    kwargs = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    ak = os.getenv("RAW_LOG_S3_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID"))
    sk = os.getenv("RAW_LOG_S3_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY"))
    if ak and sk:
        kwargs["aws_access_key_id"] = ak
        kwargs["aws_secret_access_key"] = sk
    kwargs["config"] = botocore.config.Config(
        max_pool_connections=50,
        retries={"max_attempts": 3, "mode": "adaptive"},
    )
    return boto3.client("s3", **kwargs)


def _get_thread_client(region, endpoint):
    key = f"{region}|{endpoint}"
    clients = getattr(_thread_local, "s3_clients", None)
    if clients is None:
        _thread_local.s3_clients = {}
        clients = _thread_local.s3_clients
    client = clients.get(key)
    if client is None:
        client = get_s3_client(region, endpoint)
        clients[key] = client
    return client


def list_s3_objects(s3, bucket, prefix):
    objects = []
    token = None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        for obj in resp.get("Contents", []):
            objects.append(obj["Key"])
        if not resp.get("IsTruncated"):
            break
        token = resp["NextContinuationToken"]
    return objects


def _parse_gzip_data(raw):
    data = gzip.decompress(raw)
    records = []
    for line in data.decode("utf-8", errors="replace").strip().split("\n"):
        if not line.strip():
            continue
        try:
            records.append(orjson.loads(line))
        except orjson.JSONDecodeError:
            continue
    return records


def _get_cache_path(cache_dir, key):
    return os.path.join(cache_dir, key)


def download_and_parse(s3, bucket, key, cache_dir=None):
    if cache_dir:
        cache_path = _get_cache_path(cache_dir, key)
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return _parse_gzip_data(f.read())

    resp = s3.get_object(Bucket=bucket, Key=key)
    raw = resp["Body"].read()

    if cache_dir:
        cache_path = _get_cache_path(cache_dir, key)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(raw)

    return _parse_gzip_data(raw)


def prioritize_cached_keys(keys, cache_dir=None):
    if not cache_dir:
        return list(keys), 0

    cached_keys = []
    uncached_keys = []
    for key in keys:
        if os.path.exists(_get_cache_path(cache_dir, key)):
            cached_keys.append(key)
        else:
            uncached_keys.append(key)
    return cached_keys + uncached_keys, len(cached_keys)


def download_one(region, endpoint, bucket, key, cache_dir=None):
    if cache_dir:
        cache_path = _get_cache_path(cache_dir, key)
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return _parse_gzip_data(f.read())
    client = _get_thread_client(region, endpoint)
    return download_and_parse(client, bucket, key, cache_dir=cache_dir)
