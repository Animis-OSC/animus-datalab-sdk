from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import mimetypes
import os
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote, urlencode, urlsplit
import urllib.error
import urllib.request

from ._version import __version__
from .errors import AnimusAPIError

_DEFAULT_MAX_JSON_BYTES = 8 * 1024 * 1024
_DEFAULT_MAX_ERROR_BYTES = 64 * 1024


def normalize_base_url(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if not value:
        raise ValueError("gateway_url is required")
    target = urlsplit(value)
    if target.scheme not in {"http", "https"} or not target.hostname:
        raise ValueError("gateway_url must be an absolute http/https URL")
    if target.username is not None or target.password is not None:
        raise ValueError("gateway_url must not contain credentials")
    if target.query:
        raise ValueError("gateway_url must not contain a query string")
    if target.fragment:
        raise ValueError("gateway_url must not contain a URL fragment")
    return value


def build_url(
    base_url: str,
    *segments: str,
    query: dict[str, object] | None = None,
) -> str:
    url = normalize_base_url(base_url)
    if segments:
        encoded = "/".join(quote(str(segment), safe="") for segment in segments)
        url = f"{url}/{encoded}"
    if query:
        pairs: list[tuple[str, str]] = []
        for key, value in query.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                pairs.extend((str(key), str(item)) for item in value)
            else:
                pairs.append((str(key), str(value)))
        if pairs:
            url = f"{url}?{urlencode(pairs)}"
    return url


def _validate_timeout(timeout_seconds: float) -> float:
    value = float(timeout_seconds)
    if value <= 0:
        raise ValueError("timeout_seconds must be > 0")
    return value


def _encode_json(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"JSON payload is not standards-compliant: {exc}") from exc
    return text.encode("utf-8")


def _build_headers(*, headers: dict[str, str] | None, auth_token: str | None) -> dict[str, str]:
    req_headers = {
        "Accept": "application/json",
        "User-Agent": f"animus-datalab/{__version__}",
    }
    if headers:
        for key, value in headers.items():
            if "\r" in key or "\n" in key or "\r" in value or "\n" in value:
                raise ValueError("HTTP header names and values must not contain CR/LF")
            req_headers[str(key)] = str(value)

    token = auth_token or os.environ.get("ANIMUS_AUTH_TOKEN", "").strip()
    if token:
        if any(ch in token for ch in ("\r", "\n", "\x00")):
            raise ValueError("auth_token must not contain CR/LF/NUL")
        req_headers.setdefault("Authorization", f"Bearer {token}")

    req_headers.setdefault("X-Request-Id", uuid.uuid4().hex)
    return req_headers


def _content_length(headers: object) -> int | None:
    try:
        raw = headers.get("Content-Length")  # type: ignore[attr-defined]
    except Exception:
        return None
    if raw in (None, ""):
        return None
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _read_bounded(stream: object, *, max_bytes: int, request_id: str | None) -> bytes:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")
    try:
        raw = stream.read(max_bytes + 1)  # type: ignore[attr-defined]
    except TypeError:
        raw = stream.read()  # type: ignore[attr-defined]
    if len(raw) > max_bytes:
        raise AnimusAPIError(
            0,
            "response_too_large",
            request_id,
            {"max_bytes": max_bytes},
        )
    return raw


def _parse_error_body(status: int, raw: bytes, fallback_request_id: str | None) -> AnimusAPIError:
    parsed: object | None = None
    if raw:
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {"detail": raw[:1024].decode("utf-8", errors="replace")}

    code = "request_failed"
    request_id = fallback_request_id
    if isinstance(parsed, dict):
        code = str(parsed.get("error") or parsed.get("code") or code)
        request_id = str(parsed.get("request_id") or "") or request_id
    return AnimusAPIError(status, code, request_id, parsed)


def _expect_json_object(value: object | None, *, request_id: str | None = None) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AnimusAPIError(
            0,
            "invalid_response_shape",
            request_id,
            {"expected": "object", "actual": type(value).__name__},
        )
    return value


def request_json(
    method: str,
    url: str,
    *,
    json_body: object | None = None,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    auth_token: str | None = None,
    timeout_seconds: float = 30.0,
    max_response_bytes: int = _DEFAULT_MAX_JSON_BYTES,
) -> object | None:
    if json_body is not None and data is not None:
        raise ValueError("provide only one of json_body or data")

    timeout = _validate_timeout(timeout_seconds)
    target = urlsplit(url)
    if target.scheme not in {"http", "https"} or not target.hostname:
        raise ValueError("url must be an absolute http/https URL")
    if target.username is not None or target.password is not None:
        raise ValueError("url must not contain credentials")
    if target.fragment:
        raise ValueError("url must not contain a fragment")

    req_headers = _build_headers(headers=headers, auth_token=auth_token)
    request_id = req_headers.get("X-Request-Id")

    body_bytes: bytes | None
    if json_body is not None:
        body_bytes = _encode_json(json_body)
        req_headers.setdefault("Content-Type", "application/json")
    else:
        body_bytes = data
        if body_bytes is not None:
            req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method.strip().upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(resp.getcode() or 0)
            declared = _content_length(getattr(resp, "headers", None))
            if declared is not None and declared > max_response_bytes:
                raise AnimusAPIError(
                    status,
                    "response_too_large",
                    request_id,
                    {"max_bytes": max_response_bytes, "content_length": declared},
                )
            raw = _read_bounded(resp, max_bytes=max_response_bytes, request_id=request_id)
            if status >= 400:
                raise _parse_error_body(status, raw, request_id)
            if not raw:
                return None
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AnimusAPIError(status, "invalid_json_response", request_id) from exc
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        try:
            raw = _read_bounded(exc, max_bytes=_DEFAULT_MAX_ERROR_BYTES, request_id=request_id)
        except AnimusAPIError as read_exc:
            raise AnimusAPIError(status, "error_response_too_large", request_id, read_exc.body) from None
        raise _parse_error_body(status, raw, request_id) from None
    except urllib.error.URLError as exc:
        raise AnimusAPIError(0, "network_error", request_id, {"detail": str(exc)}) from None


def download_file(
    method: str,
    url: str,
    *,
    dest_path: str,
    headers: dict[str, str] | None = None,
    auth_token: str | None = None,
    timeout_seconds: float = 30.0,
    chunk_size: int = 1024 * 1024,
    max_bytes: int | None = None,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    """Download bytes atomically and return content metadata."""

    m = method.strip().upper()
    if m not in {"GET", "HEAD"}:
        raise ValueError("download_file supports only GET/HEAD")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if max_bytes is not None and max_bytes < 0:
        raise ValueError("max_bytes must be >= 0")

    expected = (expected_sha256 or "").strip().lower() or None
    if expected is not None and (len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected)):
        raise ValueError("expected_sha256 must be a 64-character hexadecimal SHA-256 digest")

    timeout = _validate_timeout(timeout_seconds)
    target = urlsplit(url)
    if target.scheme not in {"http", "https"} or not target.hostname:
        raise ValueError("url must be an absolute http/https URL")
    if target.username is not None or target.password is not None:
        raise ValueError("url must not contain credentials")
    if target.fragment:
        raise ValueError("url must not contain a fragment")

    req_headers = _build_headers(headers=headers, auth_token=auth_token)
    request_id = req_headers.get("X-Request-Id")

    dst = Path(dest_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None

    req = urllib.request.Request(url, headers=req_headers, method=m)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(resp.getcode() or 0)
            content_type = (resp.headers.get("Content-Type") or "").strip()
            declared = _content_length(getattr(resp, "headers", None))
            if max_bytes is not None and declared is not None and declared > max_bytes:
                raise AnimusAPIError(
                    status,
                    "download_too_large",
                    request_id,
                    {"max_bytes": max_bytes, "content_length": declared},
                )
            if m == "HEAD":
                return {
                    "content_type": content_type,
                    "size_bytes": declared or 0,
                    "sha256": "",
                }

            fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=str(dst.parent))
            tmp_path = Path(tmp_name)
            sha256 = hashlib.sha256()
            size_bytes = 0
            with os.fdopen(fd, "wb") as handle:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if max_bytes is not None and size_bytes > max_bytes:
                        raise AnimusAPIError(
                            status,
                            "download_too_large",
                            request_id,
                            {"max_bytes": max_bytes, "size_bytes": size_bytes},
                        )
                    handle.write(chunk)
                    sha256.update(chunk)
                handle.flush()
                os.fsync(handle.fileno())

            digest = sha256.hexdigest()
            if expected is not None and not hmac.compare_digest(digest, expected):
                raise AnimusAPIError(
                    status,
                    "checksum_mismatch",
                    request_id,
                    {"expected_sha256": expected, "actual_sha256": digest},
                )

            os.replace(tmp_path, dst)
            tmp_path = None
            return {
                "content_type": content_type,
                "size_bytes": size_bytes,
                "sha256": digest,
            }
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        try:
            raw = _read_bounded(exc, max_bytes=_DEFAULT_MAX_ERROR_BYTES, request_id=request_id)
        except AnimusAPIError:
            raw = b""
        raise _parse_error_body(status, raw, request_id) from None
    except urllib.error.URLError as exc:
        raise AnimusAPIError(0, "network_error", request_id, {"detail": str(exc)}) from None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _guess_content_type(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def _multipart_token(value: str, *, field: str) -> str:
    text = str(value)
    if not text:
        raise ValueError(f"{field} must not be empty")
    if any(ch in text for ch in ("\r", "\n", "\x00")):
        raise ValueError(f"{field} must not contain CR/LF/NUL")
    return text.replace("\\", "\\\\").replace('"', '\\"')


def upload_multipart_file_json(
    method: str,
    url: str,
    *,
    fields: dict[str, str] | None,
    file_field_name: str,
    file_path: str,
    filename: str | None = None,
    content_type: str | None = None,
    headers: dict[str, str] | None = None,
    auth_token: str | None = None,
    timeout_seconds: float = 30.0,
    chunk_size: int = 1024 * 1024,
    max_response_bytes: int = _DEFAULT_MAX_JSON_BYTES,
) -> object | None:
    """Stream a multipart upload without loading the file into memory."""

    m = method.strip().upper()
    if m not in {"POST", "PUT"}:
        raise ValueError("upload_multipart_file_json supports only POST/PUT")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    timeout = _validate_timeout(timeout_seconds)
    target = urlsplit(url)
    if target.scheme not in {"http", "https"} or not target.hostname:
        raise ValueError("only absolute http/https URLs are supported")
    if target.username is not None or target.password is not None:
        raise ValueError("url must not contain credentials")
    if target.fragment:
        raise ValueError("url must not contain a fragment")

    boundary = f"----animus-{uuid.uuid4().hex}"
    request_headers = _build_headers(headers=headers, auth_token=auth_token)
    request_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    request_id = request_headers.get("X-Request-Id")

    path_obj = Path(file_path)
    if not path_obj.is_file():
        raise FileNotFoundError(file_path)
    file_name = _multipart_token(filename or path_obj.name or "file.bin", field="filename")
    field_name = _multipart_token(file_field_name, field="file_field_name")
    file_ct = (content_type or _guess_content_type(file_path)).strip() or "application/octet-stream"
    if any(ch in file_ct for ch in ("\r", "\n", "\x00")):
        raise ValueError("content_type must not contain CR/LF/NUL")

    pre_parts: list[bytes] = []
    for key, value in (fields or {}).items():
        name = _multipart_token(str(key).strip(), field="multipart field name")
        pre_parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                "\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        )

    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'
        f"Content-Type: {file_ct}\r\n"
        "\r\n"
    ).encode("utf-8")
    file_footer = b"\r\n"
    closing = f"--{boundary}--\r\n".encode("utf-8")

    file_size = path_obj.stat().st_size
    content_length = sum(len(part) for part in pre_parts) + len(file_header) + file_size + len(file_footer) + len(closing)
    request_headers["Content-Length"] = str(content_length)

    request_path = target.path or "/"
    if target.query:
        request_path += "?" + target.query

    port = target.port or (443 if target.scheme == "https" else 80)
    conn_cls = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    conn: http.client.HTTPConnection | None = None

    try:
        conn = conn_cls(target.hostname, port, timeout=timeout)
        conn.putrequest(m, request_path)
        for key, value in request_headers.items():
            conn.putheader(key, value)
        conn.endheaders()

        for part in pre_parts:
            conn.send(part)
        conn.send(file_header)
        with path_obj.open("rb") as handle:
            _stream_copy(conn, handle, chunk_size=chunk_size)
        conn.send(file_footer)
        conn.send(closing)

        resp = conn.getresponse()
        status = int(resp.status or 0)
        declared = _content_length(getattr(resp, "headers", None))
        if declared is not None and declared > max_response_bytes:
            raise AnimusAPIError(
                status,
                "response_too_large",
                request_id,
                {"max_bytes": max_response_bytes, "content_length": declared},
            )
        raw = _read_bounded(resp, max_bytes=max_response_bytes, request_id=request_id)
        if status >= 400:
            raise _parse_error_body(status, raw, request_id)
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AnimusAPIError(status, "invalid_json_response", request_id) from exc
    except AnimusAPIError:
        raise
    except (OSError, http.client.HTTPException) as exc:
        raise AnimusAPIError(0, "network_error", request_id, {"detail": str(exc)}) from None
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass


def _stream_copy(conn: http.client.HTTPConnection, handle: BinaryIO, *, chunk_size: int) -> None:
    while True:
        chunk = handle.read(chunk_size)
        if not chunk:
            return
        conn.send(chunk)
