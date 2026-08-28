from __future__ import annotations


class AnimusAPIError(RuntimeError):
    """Normalized SDK error for HTTP, protocol, and transport failures."""

    def __init__(
        self,
        status: int,
        code: str,
        request_id: str | None = None,
        body: object | None = None,
    ) -> None:
        self.status = int(status)
        self.code = str(code)
        self.request_id = request_id
        self.body = body
        super().__init__(f"{self.code} (status={self.status}, request_id={self.request_id})")

    @property
    def retryable(self) -> bool:
        """Whether retrying is generally useful from a transport/status perspective."""
        non_retryable_codes = {
            "checksum_mismatch",
            "download_too_large",
            "error_response_too_large",
            "invalid_json_response",
            "invalid_response_shape",
            "response_too_large",
        }
        if self.code in non_retryable_codes:
            return False
        return self.status == 0 or self.status in {408, 425, 429} or self.status >= 500
