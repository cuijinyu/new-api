"""Unit tests for app.services.core utility functions."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest

from app.services.core import (
    clamp_int,
    content_type_for_filename,
    dumps_json,
    env_int,
    filename_from_uri,
    int_or_none,
    json_safe,
    new_id,
    normalize_reference_ids,
    safe_filename,
    slug,
    uri_to_prefix,
    utc_now,
    utc_now_iso,
)


class TestNewId:
    def test_prefix(self):
        result = new_id("job")
        assert result.startswith("job-")
        assert len(result) == len("job-") + 12

    def test_uniqueness(self):
        ids = {new_id("x") for _ in range(100)}
        assert len(ids) == 100


class TestUtcNow:
    def test_returns_utc(self):
        now = utc_now()
        assert now.tzinfo == timezone.utc

    def test_iso_format(self):
        iso = utc_now_iso()
        assert iso.endswith("Z")
        assert "+" not in iso


class TestEnvInt:
    def test_default_when_unset(self):
        assert env_int("__NONEXISTENT_VAR_12345__", 10) == 10

    def test_reads_env(self):
        with patch.dict(os.environ, {"__TEST_VAR__": "5"}):
            assert env_int("__TEST_VAR__", 10) == 5

    def test_clamp_minimum(self):
        with patch.dict(os.environ, {"__TEST_VAR__": "0"}):
            assert env_int("__TEST_VAR__", 10, minimum=1) == 1

    def test_clamp_maximum(self):
        with patch.dict(os.environ, {"__TEST_VAR__": "999"}):
            assert env_int("__TEST_VAR__", 10, maximum=64) == 64

    def test_invalid_returns_default(self):
        with patch.dict(os.environ, {"__TEST_VAR__": "abc"}):
            assert env_int("__TEST_VAR__", 42) == 42

    def test_empty_returns_default(self):
        with patch.dict(os.environ, {"__TEST_VAR__": "  "}):
            assert env_int("__TEST_VAR__", 7) == 7


class TestClampInt:
    def test_none_returns_default(self):
        assert clamp_int(None, 5, 1, 10) == 5

    def test_below_minimum(self):
        assert clamp_int(-1, 5, 0, 100) == 0

    def test_above_maximum(self):
        assert clamp_int(200, 5, 0, 100) == 100

    def test_within_range(self):
        assert clamp_int(50, 5, 0, 100) == 50


class TestJsonSafe:
    def test_datetime(self):
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert json_safe(dt) == "2026-01-15T12:00:00Z"

    def test_path(self):
        p = Path("/tmp/test")
        assert json_safe(p) == str(p)

    def test_nested(self):
        dt = datetime(2026, 6, 1, tzinfo=timezone.utc)
        result = json_safe({"a": dt, "b": [dt]})
        assert result == {"a": "2026-06-01T00:00:00Z", "b": ["2026-06-01T00:00:00Z"]}

    def test_tuple(self):
        result = json_safe((1, 2, 3))
        assert result == [1, 2, 3]


class TestDumpsJson:
    def test_deterministic(self):
        result = dumps_json({"b": 2, "a": 1})
        assert result == '{"a":1,"b":2}'

    def test_non_ascii_preserved(self):
        result = dumps_json({"name": "测试"})
        assert "测试" in result


class TestSlug:
    def test_basic(self):
        assert slug("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slug("foo@bar#baz") == "foo-bar-baz"

    def test_empty_raises(self):
        with pytest.raises(Exception):
            slug("   ")

    def test_already_valid(self):
        assert slug("my-slug") == "my-slug"


class TestSafeFilename:
    def test_normal(self):
        assert safe_filename("report.csv") == "report.csv"

    def test_special_chars(self):
        result = safe_filename("my file (1).csv")
        assert ".csv" in result
        assert " " not in result

    def test_chinese(self):
        result = safe_filename("测试文件.json")
        assert "测试文件" in result

    def test_truncates_long_name(self):
        long_name = "a" * 300 + ".txt"
        result = safe_filename(long_name)
        assert len(result) <= 180


class TestContentTypeForFilename:
    def test_json(self):
        assert content_type_for_filename("data.json") == "application/json"

    def test_csv(self):
        assert "csv" in content_type_for_filename("bill.csv")

    def test_md(self):
        assert "markdown" in content_type_for_filename("report.md")

    def test_unknown(self):
        assert content_type_for_filename("archive.zip") == "application/octet-stream"


class TestFilenameFromUri:
    def test_s3_uri(self):
        assert filename_from_uri("s3://bucket/path/to/file.json", "fb") == "file.json"

    def test_empty(self):
        assert filename_from_uri("", "fallback.txt") == "fallback.txt"

    def test_trailing_slash(self):
        result = filename_from_uri("s3://bucket/path/to/dir/", "fb.txt")
        assert result == "dir"


class TestUriToPrefix:
    def test_s3_uri(self):
        assert uri_to_prefix("s3://bucket/some/path/") == "some/path"

    def test_none(self):
        assert uri_to_prefix(None) is None

    def test_bare_string(self):
        assert uri_to_prefix("some/path/") == "some/path"


class TestIntOrNone:
    def test_valid(self):
        assert int_or_none("42") == 42

    def test_none(self):
        assert int_or_none(None) is None

    def test_empty(self):
        assert int_or_none("") is None

    def test_invalid(self):
        assert int_or_none("abc") is None


class TestNormalizeReferenceIds:
    def test_list(self):
        result = normalize_reference_ids(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_dedup(self):
        result = normalize_reference_ids(["a", "b", "a"])
        assert result == ["a", "b"]

    def test_max_12(self):
        result = normalize_reference_ids([str(i) for i in range(20)])
        assert len(result) == 12

    def test_non_list(self):
        assert normalize_reference_ids("not-a-list") == []

    def test_strips_empty(self):
        result = normalize_reference_ids(["a", "", "  ", "b"])
        assert result == ["a", "b"]
