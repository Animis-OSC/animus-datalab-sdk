# Changelog

## 1.2.0

Contract-alignment and release-governance release.

- Align `DatasetRegistryClient` with the DataLab Dataset Registry 0.2.x contract: projects, datasets, immutable versions, streaming version upload, download, and bounded list APIs.
- Align `ExperimentsClient` with the DataLab Experiments 0.3.x contract: experiment/run reads, project-scoped Data Plane dispatch, execution/build-context reads, and metric listing.
- Keep `execute_run()` as a documented legacy compatibility surface; canonical execution is `create_run()` followed by project-scoped `dispatch_run()`.
- Add contract-version markers to the public clients.
- Add contract regression tests for URL mapping, idempotency payloads, limits, multipart upload, and legacy compatibility.
- Document the ownership boundary: DataLab owns the OpenAPI contracts; this package is the client-side projection used by CI and training workloads. Animus Link is a separate live product in the same Animus company portfolio.
- Move GitHub Actions checkout/setup steps to current Node 24-based major versions.
- Preserve the zero-runtime-dependency universal-wheel strategy and the hardened transport introduced in 1.1.0.

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
