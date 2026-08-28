from __future__ import annotations

import math
import os
import queue
import random
import threading
import time
import uuid
from dataclasses import dataclass, field

from .errors import AnimusAPIError
from .http_client import build_url, normalize_base_url, request_json


@dataclass(frozen=True, slots=True)
class TelemetryStats:
    accepted: int
    dropped: int
    sent: int
    failed: int
    retried: int


@dataclass(slots=True)
class _TelemetryTask:
    kind: str
    url: str
    body: dict[str, object]
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempts: int = 0
    next_retry_at: float = 0.0


class RunTelemetryLogger:
    """Best-effort, non-blocking telemetry publisher for training workloads."""

    def __init__(
        self,
        *,
        gateway_url: str,
        run_id: str,
        auth_token: str | None = None,
        timeout_seconds: float = 5.0,
        max_queue: int = 2048,
        max_retries: int = 6,
    ) -> None:
        self._gateway_url = normalize_base_url(gateway_url)
        self._run_id = (run_id or "").strip()
        if not self._run_id:
            raise ValueError("run_id is required")

        self._auth_token = (auth_token or "").strip() or None
        self._timeout_seconds = float(timeout_seconds)
        if self._timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if max_queue <= 0:
            raise ValueError("max_queue must be > 0")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        self._queue: queue.Queue[_TelemetryTask | None] = queue.Queue(maxsize=int(max_queue))
        self._max_retries = int(max_retries)
        self._stop = threading.Event()
        self._closed = threading.Event()
        self._state_lock = threading.Lock()
        self._last_error: AnimusAPIError | None = None
        self._accepted = 0
        self._dropped = 0
        self._sent = 0
        self._failed = 0
        self._retried = 0
        self._thread = threading.Thread(target=self._run_loop, name="animus-telemetry", daemon=True)
        self._thread.start()

    @classmethod
    def from_env(
        cls,
        *,
        gateway_url: str | None = None,
        run_id: str | None = None,
        auth_token: str | None = None,
        timeout_seconds: float = 5.0,
        max_queue: int = 2048,
        max_retries: int = 6,
    ) -> "RunTelemetryLogger":
        base = (
            gateway_url
            or os.environ.get("DATAPILOT_URL")
            or os.environ.get("ANIMUS_GATEWAY_URL")
            or "http://localhost:8080"
        )
        run = (run_id or os.environ.get("RUN_ID") or "").strip()
        if not run:
            raise ValueError("run_id is required (or set RUN_ID)")
        token = (
            auth_token
            or os.environ.get("TOKEN")
            or os.environ.get("ANIMUS_AUTH_TOKEN")
            or ""
        ).strip() or None
        return cls(
            gateway_url=base,
            run_id=run,
            auth_token=token,
            timeout_seconds=timeout_seconds,
            max_queue=max_queue,
            max_retries=max_retries,
        )

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def last_error(self) -> AnimusAPIError | None:
        with self._state_lock:
            return self._last_error

    @property
    def stats(self) -> TelemetryStats:
        with self._state_lock:
            return TelemetryStats(
                accepted=self._accepted,
                dropped=self._dropped,
                sent=self._sent,
                failed=self._failed,
                retried=self._retried,
            )

    def log_metric(
        self,
        *,
        step: int,
        name: str,
        value: float,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        metric_name = (name or "").strip()
        if not metric_name:
            raise ValueError("name is required")
        return self.log_metrics(step=step, metrics={metric_name: value}, metadata=metadata)

    def log_metrics(
        self,
        *,
        step: int,
        metrics: dict[str, float],
        metadata: dict[str, object] | None = None,
    ) -> bool:
        if step < 0:
            raise ValueError("step must be >= 0")
        if not metrics:
            raise ValueError("metrics must not be empty")

        normalized: dict[str, float] = {}
        for name, value in metrics.items():
            key = (name or "").strip()
            if not key:
                raise ValueError("metric names must not be empty")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"metric {key!r} must be finite")
            normalized[key] = number

        body: dict[str, object] = {"step": int(step), "metrics": normalized}
        if metadata:
            body["metadata"] = metadata

        url = build_url(
            self._gateway_url,
            "api",
            "experiments",
            "experiment-runs",
            self._run_id,
            "metrics",
        )
        return self._enqueue(_TelemetryTask(kind="metrics", url=url, body=body))

    def log_status(
        self,
        *,
        status: str,
        message: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        status_value = (status or "").strip()
        if not status_value:
            raise ValueError("status is required")

        meta: dict[str, object] = {"status": status_value}
        if metadata:
            meta.update(metadata)

        msg = (message or "").strip() or f"status: {status_value}"
        return self._log_event(level="info", message=msg, metadata=meta)

    def log_event(
        self,
        *,
        level: str,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return self._log_event(level=level, message=message, metadata=metadata)

    def log_progress(
        self,
        *,
        step: int,
        total_steps: int | None = None,
        percent: float | None = None,
        message: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        if step < 0:
            raise ValueError("step must be >= 0")

        meta: dict[str, object] = {"progress_step": int(step)}
        if total_steps is not None:
            if total_steps <= 0:
                raise ValueError("total_steps must be > 0")
            meta["progress_total_steps"] = int(total_steps)
        if percent is not None:
            value = float(percent)
            if not math.isfinite(value) or value < 0.0 or value > 1.0:
                raise ValueError("percent must be finite and between 0.0 and 1.0")
            meta["progress_percent"] = value
        if metadata:
            meta.update(metadata)

        msg = (message or "").strip() or "progress"
        return self._log_event(level="info", message=msg, metadata=meta)

    def close(self, *, flush: bool = True, timeout_seconds: float = 5.0) -> None:
        if self._closed.is_set():
            return

        timeout = max(0.0, float(timeout_seconds))
        if flush:
            self.flush(timeout_seconds=timeout)

        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        self._thread.join(timeout=max(0.1, timeout))
        self._closed.set()

    def flush(self, *, timeout_seconds: float = 5.0) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.05)
        return self._queue.unfinished_tasks == 0

    def _log_event(
        self,
        *,
        level: str,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        msg = (message or "").strip()
        if not msg:
            raise ValueError("message is required")
        lvl = (level or "").strip().lower() or "info"
        if lvl not in {"debug", "info", "warn", "error"}:
            raise ValueError("invalid level")

        body: dict[str, object] = {"level": lvl, "message": msg}
        if metadata:
            body["metadata"] = metadata
        url = build_url(
            self._gateway_url,
            "api",
            "experiments",
            "experiment-runs",
            self._run_id,
            "events",
        )
        return self._enqueue(_TelemetryTask(kind="event", url=url, body=body))

    def _enqueue(self, task: _TelemetryTask) -> bool:
        if self._stop.is_set() or self._closed.is_set():
            return False
        try:
            self._queue.put_nowait(task)
        except queue.Full:
            with self._state_lock:
                self._dropped += 1
            return False
        with self._state_lock:
            self._accepted += 1
        return True

    def _record_error(self, error: AnimusAPIError) -> None:
        with self._state_lock:
            self._last_error = error

    def _requeue(self, task: _TelemetryTask) -> bool:
        try:
            self._queue.put_nowait(task)
            return True
        except queue.Full:
            with self._state_lock:
                self._dropped += 1
                self._failed += 1
            return False

    def _run_loop(self) -> None:
        while True:
            if self._stop.is_set() and self._queue.empty():
                return

            try:
                task = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if task is None:
                self._queue.task_done()
                if self._stop.is_set():
                    return
                continue

            try:
                now = time.monotonic()
                if task.next_retry_at > now and not self._stop.is_set():
                    delay = task.next_retry_at - now
                    if self._requeue(task) and delay > 0 and self._queue.qsize() == 1:
                        self._stop.wait(timeout=min(delay, 0.2))
                    continue

                request_json(
                    "POST",
                    task.url,
                    json_body=task.body,
                    headers={"X-Request-Id": task.request_id},
                    auth_token=self._auth_token,
                    timeout_seconds=self._timeout_seconds,
                )
                with self._state_lock:
                    self._sent += 1
            except AnimusAPIError as exc:
                self._record_error(exc)
                task.attempts += 1
                if exc.retryable and task.attempts <= self._max_retries and not self._stop.is_set():
                    base = min(10.0, 0.25 * (2 ** (task.attempts - 1)))
                    task.next_retry_at = time.monotonic() + base * random.uniform(0.8, 1.2)
                    with self._state_lock:
                        self._retried += 1
                    self._requeue(task)
                else:
                    with self._state_lock:
                        self._failed += 1
            except Exception as exc:  # telemetry must never crash the training process
                error = AnimusAPIError(
                    0,
                    "telemetry_logger_error",
                    task.request_id,
                    {"detail": str(exc), "kind": task.kind},
                )
                self._record_error(error)
                with self._state_lock:
                    self._failed += 1
            finally:
                self._queue.task_done()

    def __enter__(self) -> "RunTelemetryLogger":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close(flush=True)
