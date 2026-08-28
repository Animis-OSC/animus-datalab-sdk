from __future__ import annotations

import json
import os

from .http_client import (
    _expect_json_object,
    build_url,
    download_file,
    normalize_base_url,
    request_json,
    upload_multipart_file_json,
)


def _require_text(value: str, *, field: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _limit(value: int) -> int:
    limit = int(value)
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    return limit


def _idempotency_headers(idempotency_key: str | None) -> dict[str, str] | None:
    if idempotency_key is None:
        return None
    return {"Idempotency-Key": _require_text(idempotency_key, field="idempotency_key")}


class DatasetRegistryClient:
    """Client for the DataLab Dataset Registry API (contract 0.2.x)."""

    CONTRACT_VERSION = "0.2"

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

    def list_projects(self, *, limit: int = 100) -> dict[str, object]:
        url = build_url(self._gateway_url, "api", "dataset-registry", "projects", query={"limit": _limit(limit)})
        return _expect_json_object(
            request_json("GET", url, auth_token=self._auth_token, timeout_seconds=self._timeout_seconds)
        )

    def create_project(
        self,
        *,
        name: str,
        description: str = "",
        metadata: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        url = build_url(self._gateway_url, "api", "dataset-registry", "projects")
        body = {"name": _require_text(name, field="name"), "description": str(description), "metadata": metadata or {}}
        return _expect_json_object(
            request_json(
                "POST",
                url,
                json_body=body,
                headers=_idempotency_headers(idempotency_key),
                auth_token=self._auth_token,
                timeout_seconds=self._timeout_seconds,
            )
        )

    def get_project(self, *, project_id: str) -> dict[str, object]:
        url = build_url(self._gateway_url, "api", "dataset-registry", "projects", _require_text(project_id, field="project_id"))
        return _expect_json_object(
            request_json("GET", url, auth_token=self._auth_token, timeout_seconds=self._timeout_seconds)
        )

    def list_datasets(self, *, limit: int = 100) -> dict[str, object]:
        url = build_url(self._gateway_url, "api", "dataset-registry", "datasets", query={"limit": _limit(limit)})
        return _expect_json_object(
            request_json("GET", url, auth_token=self._auth_token, timeout_seconds=self._timeout_seconds)
        )

    def create_dataset(
        self,
        *,
        name: str,
        description: str = "",
        metadata: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        url = build_url(self._gateway_url, "api", "dataset-registry", "datasets")
        body = {"name": _require_text(name, field="name"), "description": str(description), "metadata": metadata or {}}
        return _expect_json_object(
            request_json(
                "POST",
                url,
                json_body=body,
                headers=_idempotency_headers(idempotency_key),
                auth_token=self._auth_token,
                timeout_seconds=self._timeout_seconds,
            )
        )

    def get_dataset(self, *, dataset_id: str) -> dict[str, object]:
        url = build_url(self._gateway_url, "api", "dataset-registry", "datasets", _require_text(dataset_id, field="dataset_id"))
        return _expect_json_object(
            request_json("GET", url, auth_token=self._auth_token, timeout_seconds=self._timeout_seconds)
        )

    def list_dataset_versions(self, *, dataset_id: str, limit: int = 100) -> dict[str, object]:
        url = build_url(
            self._gateway_url,
            "api",
            "dataset-registry",
            "datasets",
            _require_text(dataset_id, field="dataset_id"),
            "versions",
            query={"limit": _limit(limit)},
        )
        return _expect_json_object(
            request_json("GET", url, auth_token=self._auth_token, timeout_seconds=self._timeout_seconds)
        )

    def upload_dataset_version(
        self,
        *,
        dataset_id: str,
        file_path: str,
        metadata: dict[str, object] | None = None,
        quality_rule_id: str | None = None,
        filename: str | None = None,
        content_type: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        _require_text(file_path, field="file_path")
        fields: dict[str, str] = {}
        if metadata is not None:
            fields["metadata"] = json.dumps(metadata, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
        if quality_rule_id:
            fields["quality_rule_id"] = _require_text(quality_rule_id, field="quality_rule_id")
        url = build_url(
            self._gateway_url,
            "api",
            "dataset-registry",
            "datasets",
            _require_text(dataset_id, field="dataset_id"),
            "versions",
            "upload",
        )
        out = upload_multipart_file_json(
            "POST",
            url,
            fields=fields,
            file_field_name="file",
            file_path=file_path,
            filename=filename,
            content_type=content_type,
            headers=_idempotency_headers(idempotency_key),
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def get_dataset_version(self, *, dataset_version_id: str) -> dict[str, object]:
        version_id = _require_text(dataset_version_id, field="dataset_version_id")
        url = build_url(self._gateway_url, "api", "dataset-registry", "dataset-versions", version_id)
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
        url = build_url(self._gateway_url, "api", "dataset-registry", "dataset-versions", version_id, "download")
        return download_file(
            "GET",
            url,
            dest_path=dest_path,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
            max_bytes=max_bytes,
            expected_sha256=expected_sha256,
        )
