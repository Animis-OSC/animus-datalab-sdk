import math
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import mock

from animus_sdk import AnimusAPIError, AnimusClient
from animus_sdk.errors import AnimusAPIError as Error
from animus_sdk.git import git_metadata_from_env
from animus_sdk.http_client import (
    _expect_json_object,
    build_url,
    download_file,
    request_json,
    upload_multipart_file_json,
)
from animus_sdk.telemetry import RunTelemetryLogger


class _Headers:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default=None):
        return self._values.get(key, default)


class _Response:
    def __init__(self, body: bytes, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self._offset = 0
        self._status = status
        self.headers = _Headers(headers or {})

    def getcode(self) -> int:
        return self._status

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            data = self._body[self._offset :]
            self._offset = len(self._body)
            return data
        data = self._body[self._offset : self._offset + size]
        self._offset += len(data)
        return data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class TestProductionHardening(unittest.TestCase):
    def test_build_url_percent_encodes_paths_and_queries(self) -> None:
        url = build_url(
            "https://example.test/base",
            "api",
            "runs",
            "a/b",
            query={"name": "a&b c", "limit": 20},
        )
        self.assertEqual(
            url,
            "https://example.test/base/api/runs/a%2Fb?name=a%26b+c&limit=20",
        )

    def test_invalid_response_shape_is_runtime_error_not_assert(self) -> None:
        with self.assertRaises(AnimusAPIError) as ctx:
            _expect_json_object(["not", "an", "object"])
        self.assertEqual(ctx.exception.code, "invalid_response_shape")

    def test_request_json_rejects_non_standard_nan_before_network(self) -> None:
        with mock.patch("animus_sdk.http_client.urllib.request.urlopen") as urlopen:
            with self.assertRaises(ValueError):
                request_json("POST", "https://example.test/api", json_body={"loss": math.nan})
        urlopen.assert_not_called()

    def test_download_checksum_mismatch_is_atomic(self) -> None:
        payload = b"model-bytes"

        def fake_urlopen(req, timeout=None):
            return _Response(
                payload,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(len(payload)),
                },
            )

        with TemporaryDirectory() as td:
            destination = Path(td) / "model.bin"
            with mock.patch("animus_sdk.http_client.urllib.request.urlopen", side_effect=fake_urlopen):
                with self.assertRaises(AnimusAPIError) as ctx:
                    download_file(
                        "GET",
                        "https://example.test/model",
                        dest_path=str(destination),
                        expected_sha256="0" * 64,
                    )
            self.assertEqual(ctx.exception.code, "checksum_mismatch")
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(td).glob(".*.tmp")), [])

    def test_multipart_header_injection_is_rejected(self) -> None:
        with TemporaryDirectory() as td:
            file_path = Path(td) / "payload.bin"
            file_path.write_bytes(b"x")
            with self.assertRaises(ValueError):
                upload_multipart_file_json(
                    "POST",
                    "https://example.test/upload",
                    fields={},
                    file_field_name="file",
                    file_path=str(file_path),
                    filename='safe.bin"\r\nX-Evil: yes',
                )

    def test_unified_client_configures_subclients(self) -> None:
        client = AnimusClient(gateway_url="https://example.test/", auth_token="token", timeout_seconds=2.0)
        self.assertEqual(client.gateway_url, "https://example.test")
        self.assertEqual(client.experiments.gateway_url, "https://example.test")
        self.assertEqual(client.datasets.gateway_url, "https://example.test")

    def test_telemetry_rejects_non_finite_metrics(self) -> None:
        logger = RunTelemetryLogger(gateway_url="https://example.test", run_id="run-1")
        try:
            with self.assertRaises(ValueError):
                logger.log_metric(step=0, name="loss", value=math.inf)
        finally:
            logger.close(flush=False)

    def test_telemetry_stats_and_stable_request_id(self) -> None:
        with mock.patch("animus_sdk.telemetry.request_json") as request:
            request.return_value = None
            logger = RunTelemetryLogger(gateway_url="https://example.test", run_id="run-1")
            try:
                self.assertTrue(logger.log_metric(step=0, name="loss", value=1.0))
                self.assertTrue(logger.flush(timeout_seconds=2.0))
                stats = logger.stats
            finally:
                logger.close(flush=True, timeout_seconds=2.0)

        self.assertEqual(stats.accepted, 1)
        self.assertEqual(stats.sent, 1)
        self.assertEqual(stats.failed, 0)
        headers = request.call_args.kwargs["headers"]
        self.assertTrue(headers["X-Request-Id"])

    def test_git_metadata_prefers_pull_request_head_ref(self) -> None:
        metadata = git_metadata_from_env(
            {
                "GITHUB_SHA": "abc123",
                "GITHUB_REPOSITORY": "org/repo",
                "GITHUB_REF": "refs/pull/42/merge",
                "GITHUB_HEAD_REF": "feature/premium",
            }
        )
        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata.ref, "feature/premium")

    def test_retryable_error_classification(self) -> None:
        self.assertTrue(Error(429, "rate_limited").retryable)
        self.assertTrue(Error(503, "unavailable").retryable)
        self.assertFalse(Error(400, "bad_request").retryable)


if __name__ == "__main__":
    unittest.main()
