from __future__ import annotations

import os

from .datasets import DatasetRegistryClient
from .experiments import ExperimentsClient
from .http_client import normalize_base_url


class AnimusClient:
    """Unified entry point for the public Animus DataLab SDK surfaces."""

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

        self.experiments = ExperimentsClient(
            gateway_url=self._gateway_url,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )
        self.datasets = DatasetRegistryClient(
            gateway_url=self._gateway_url,
            auth_token=self._auth_token,
            timeout_seconds=self._timeout_seconds,
        )

    @classmethod
    def from_env(cls, *, timeout_seconds: float = 30.0) -> "AnimusClient":
        return cls(timeout_seconds=timeout_seconds)

    @property
    def gateway_url(self) -> str:
        return self._gateway_url
