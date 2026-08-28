from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from .git import GitMetadata, get_git_metadata
from .http_client import (
    _expect_json_object,
    build_url,
    download_file,
    normalize_base_url,
    request_json,
    upload_multipart_file_json,
)


def _format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_text(value: str, *, field: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _validate_timeout(timeout_seconds: float) -> float:
    value = float(timeout_seconds)
    if value <= 0:
        raise ValueError("timeout_seconds must be > 0")
    return value


def _canonical_json_bytes(payload: object) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"payload is not standards-compliant JSON: {exc}") from exc


def compute_ci_webhook_signature(secret: str, ts: str, method: str, body: bytes) -> str:
    secret_value = _require_text(secret, field="secret")
    ts_value = _require_text(ts, field="ts")
    method_value = _require_text(method, field="method").upper()
    body_hash = hashlib.sha256(body).hexdigest()
    msg = "\n".join([ts_value, method_value, body_hash])
    mac = hmac.new(secret_value.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("utf-8").rstrip("=")


class ExperimentsClient:
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
        self._timeout_seconds = _validate_timeout(timeout_seconds)

    @property
    def gateway_url(self) -> str:
        return self._gateway_url

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    def create_experiment(
        self,
        *,
        name: str,
        description: str = "",
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        experiment_name = _require_text(name, field="name")
        body = {
            "name": experiment_name,
            "description": str(description),
            "metadata": metadata or {},
        }
        url = build_url(self._gateway_url, "api", "experiments", "experiments")
        out = request_json(
            "POST",
            url,
            json_body=body,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def list_experiments(self, *, limit: int = 100, name: str | None = None) -> dict[str, object]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        query: dict[str, object] = {"limit": int(limit)}
        if name:
            query["name"] = name
        url = build_url(self._gateway_url, "api", "experiments", "experiments", query=query)
        out = request_json(
            "GET",
            url,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def create_run(
        self,
        *,
        experiment_id: str,
        dataset_version_id: str | None = None,
        status: str,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        git: GitMetadata | None = None,
        params: dict[str, object] | None = None,
        metrics: dict[str, object] | None = None,
        artifacts_prefix: str | None = None,
    ) -> dict[str, object]:
        experiment = _require_text(experiment_id, field="experiment_id")
        run_status = _require_text(status, field="status")
        git_meta = git or get_git_metadata()
        body: dict[str, object] = {
            "dataset_version_id": (dataset_version_id or "").strip(),
            "status": run_status,
            "started_at": _format_dt(started_at),
            "ended_at": _format_dt(ended_at),
            "git_repo": git_meta.repo if git_meta else "",
            "git_commit": git_meta.commit if git_meta else "",
            "git_ref": git_meta.ref if git_meta else "",
            "params": params or {},
            "metrics": metrics or {},
            "artifacts_prefix": (artifacts_prefix or "").strip(),
        }
        body = {key: value for key, value in body.items() if value not in (None, "")}

        url = build_url(self._gateway_url, "api", "experiments", "experiments", experiment, "runs")
        out = request_json(
            "POST",
            url,
            json_body=body,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def create_run_with_git(
        self,
        *,
        experiment_id: str,
        dataset_version_id: str | None = None,
        status: str,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        params: dict[str, object] | None = None,
        metrics: dict[str, object] | None = None,
        artifacts_prefix: str | None = None,
    ) -> dict[str, object]:
        git_meta = get_git_metadata()
        return self.create_run(
            experiment_id=experiment_id,
            dataset_version_id=dataset_version_id,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            git=git_meta,
            params=params,
            metrics=metrics,
            artifacts_prefix=artifacts_prefix,
        )

    def post_ci_webhook(
        self,
        *,
        payload: dict[str, object],
        ci_secret: str | None = None,
        ts: str | None = None,
    ) -> dict[str, object]:
        return self._post_signed_ci("webhook", payload=payload, ci_secret=ci_secret, ts=ts)

    def post_ci_report(
        self,
        *,
        payload: dict[str, object],
        ci_secret: str | None = None,
        ts: str | None = None,
    ) -> dict[str, object]:
        return self._post_signed_ci("report", payload=payload, ci_secret=ci_secret, ts=ts)

    def _post_signed_ci(
        self,
        endpoint: str,
        *,
        payload: dict[str, object],
        ci_secret: str | None,
        ts: str | None,
    ) -> dict[str, object]:
        secret = (ci_secret or os.environ.get("ANIMUS_CI_WEBHOOK_SECRET") or "").strip()
        if not secret:
            raise ValueError("ci_secret is required (or set ANIMUS_CI_WEBHOOK_SECRET)")

        ts_value = (ts or str(int(datetime.now(tz=timezone.utc).timestamp()))).strip()
        body = _canonical_json_bytes(payload)
        headers = {
            "X-Animus-CI-Ts": ts_value,
            "X-Animus-CI-Sig": compute_ci_webhook_signature(secret, ts_value, "POST", body),
        }
        url = build_url(self._gateway_url, "api", "experiments", "ci", endpoint)
        out = request_json(
            "POST",
            url,
            data=body,
            headers=headers,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def execute_run(
        self,
        *,
        experiment_id: str,
        dataset_version_id: str,
        image_ref: str,
        git_repo: str = "",
        git_commit: str = "",
        git_ref: str = "",
        params: dict[str, object] | None = None,
        resources: dict[str, object] | None = None,
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "experiment_id": _require_text(experiment_id, field="experiment_id"),
            "dataset_version_id": _require_text(dataset_version_id, field="dataset_version_id"),
            "image_ref": _require_text(image_ref, field="image_ref"),
            "git_repo": git_repo.strip(),
            "git_commit": git_commit.strip(),
            "git_ref": git_ref.strip(),
            "params": params or {},
            "resources": resources or {},
        }
        body = {key: value for key, value in body.items() if value not in ("", None)}
        url = build_url(self._gateway_url, "api", "experiments", "experiments", "runs:execute")
        out = request_json(
            "POST",
            url,
            json_body=body,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def get_run(self, *, run_id: str) -> dict[str, object]:
        run = _require_text(run_id, field="run_id")
        url = build_url(self._gateway_url, "api", "experiments", "experiment-runs", run)
        out = request_json(
            "GET",
            url,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def list_run_artifacts(
        self,
        *,
        run_id: str,
        kind: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        run = _require_text(run_id, field="run_id")
        if limit <= 0:
            raise ValueError("limit must be > 0")
        query: dict[str, object] = {"limit": int(limit)}
        if kind:
            query["kind"] = kind
        url = build_url(
            self._gateway_url,
            "api",
            "experiments",
            "experiment-runs",
            run,
            "artifacts",
            query=query,
        )
        out = request_json(
            "GET",
            url,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def get_run_artifact(self, *, run_id: str, artifact_id: str) -> dict[str, object]:
        run = _require_text(run_id, field="run_id")
        artifact = _require_text(artifact_id, field="artifact_id")
        url = build_url(
            self._gateway_url,
            "api",
            "experiments",
            "experiment-runs",
            run,
            "artifacts",
            artifact,
        )
        out = request_json(
            "GET",
            url,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)

    def download_run_artifact(
        self,
        *,
        run_id: str,
        artifact_id: str,
        dest_path: str,
        max_bytes: int | None = None,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        run = _require_text(run_id, field="run_id")
        artifact = _require_text(artifact_id, field="artifact_id")
        _require_text(dest_path, field="dest_path")
        url = build_url(
            self._gateway_url,
            "api",
            "experiments",
            "experiment-runs",
            run,
            "artifacts",
            artifact,
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

    def upload_run_artifact(
        self,
        *,
        run_id: str,
        kind: str,
        file_path: str,
        name: str | None = None,
        metadata: dict[str, object] | None = None,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, object]:
        run = _require_text(run_id, field="run_id")
        artifact_kind = _require_text(kind, field="kind")
        _require_text(file_path, field="file_path")

        fields: dict[str, str] = {"kind": artifact_kind}
        if name:
            fields["name"] = name
        if metadata is not None:
            fields["metadata"] = _canonical_json_bytes(metadata).decode("utf-8")

        url = build_url(self._gateway_url, "api", "experiments", "experiment-runs", run, "artifacts")
        out = upload_multipart_file_json(
            "POST",
            url,
            fields=fields,
            file_field_name="file",
            file_path=file_path,
            filename=filename,
            content_type=content_type,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        return _expect_json_object(out)
