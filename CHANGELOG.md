# Changelog

## 1.1.0

Production-hardening release.

- Add unified `AnimusClient`.
- Export `AnimusAPIError` and telemetry delivery statistics.
- Add percent-encoded URL construction and explicit runtime response-shape validation.
- Add bounded HTTP/error bodies and strict standards-compliant JSON encoding.
- Add atomic, size-bounded, optional SHA-256-verified downloads.
- Harden multipart metadata against CR/LF header injection.
- Reuse telemetry request IDs across retries; add jitter and delivery counters.
- Bound local git probing and disable interactive git prompts.
- Ship PEP 561 `py.typed` metadata.
- Add Python 3.10-3.14 CI, cross-platform smoke tests, build verification, and PyPI Trusted Publishing with attestations.
- Remove tracked Python bytecode/cache artifacts.
