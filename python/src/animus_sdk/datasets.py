from __future__ import annotations

import os

from .http_client import _expect_json_object, build_url, download_file, normalize_base_url, request_json


def _require_text(value: str, *, field: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


class DatasetRegistryClient:
    def __init__(
        self,
        *,
        gateway_url: str | None = None,
        auth_token: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        base = gateway_url or os.environ.get("ANIMUS_GATEWAY_URL") or "http://localhost:8080"
        self._gateway_url = normalize_base_url(base)
        self._auth_token = (auth_token or os.environ.get("ANIMUS_AUTH_TOKEN") or "").strip() or None
        self._timeout_seconds = float(timeout_seconds)
        if self._timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")

    @property
    def gateway_url(self) -> str:
        return self._gateway_url

    def get_dataset_version(self, *, dataset_version_id: str) -> dict[str, object]:
        version_id = _require_text(dataset_version_id, field="dataset_version_id")
        url = build_url(
            self._gateway_url,
            "api",
            "dataset-registry",
            "dataset-versions",
            version_id,
        )
        out = request_json(
            "GET",
            url,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def download_dataset_version(
        self,
        *,
        dataset_version_id: str,
        dest_path: str,
        max_bytes: int | None = None,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        version_id = _require_text(dataset_version_id, field="dataset_version_id")
        _require_text(dest_path, field="dest_path")
        url = build_url(
            self._gateway_url,
            "api",
            "dataset-registry",
            "dataset-versions",
            version_id,
            "download",
        )
        return download_file(
            "GET",
            url,
            dest_path=dest_path,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
            max_bytes=max_bytes,
            expected_sha256=expected_sha256,
        )
