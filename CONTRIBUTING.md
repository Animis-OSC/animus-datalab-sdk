# Contributing to Animus DataLab SDK

Thank you for contributing. The SDK is a public integration boundary for Animus DataLab, so changes are reviewed for API compatibility, failure semantics, security, packaging, and reproducibility as well as code correctness.

## Scope

This repository contains the public Python SDK. It does not define server-side product policy by itself.

- DataLab server/API contracts are authoritative for HTTP paths, payloads, compatibility, and execution semantics.
- The SDK should project those contracts without silently widening them.
- Private server implementation details are not a dependency and should not be copied into this repository.

## Development setup

From the repository root:

```bash
python -m pip install -e "python[dev]"
```

Run the local quality gates from `python/`:

```bash
python -m compileall -q src
python -m ruff check src tests
python -m mypy src/animus_sdk
python -m pytest --cov=animus_sdk --cov-branch --cov-report=term-missing --cov-fail-under=70
```

The GitHub Actions matrix additionally validates supported CPython versions and platform smoke tests.

## Change rules

### API and compatibility

For any change to HTTP paths, request/response models, authentication, retries, execution dispatch, datasets, experiments, artifacts, or telemetry:

1. identify the corresponding DataLab contract/version;
2. preserve documented compatibility or explicitly propose a version boundary;
3. add positive and negative tests for the changed behavior;
4. document any new failure mode or retry/idempotency implication;
5. update `docs/COMPATIBILITY.md` when the supported contract surface changes.

### Security-sensitive changes

Treat credentials, signing, headers, URL parsing, artifact paths, integrity checks, temporary files, and error-body handling as security-sensitive surfaces.

Do not weaken validation or bounds merely to make an integration pass. Security regressions require an explicit design discussion and tests.

For suspected vulnerabilities, follow `SECURITY.md` and use GitHub's private security-advisory flow instead of a public issue.

### Runtime dependencies

The SDK intentionally has zero runtime dependencies. Adding one changes an important deployment property and requires explicit justification, security/supply-chain review, and documentation.

### Large-file behavior

Artifact operations should remain streaming and bounded. Avoid whole-file buffering unless a documented hard size limit makes it safe and the tradeoff is justified.

### Telemetry

Telemetry must not make the training/application workload fail merely because observability delivery is unavailable. Queues, retries, drops, and shutdown behavior should remain bounded and observable.

## Pull requests

Keep PRs focused and explain:

- the user/integration problem;
- the relevant contract or compatibility boundary;
- failure and retry behavior;
- security implications when applicable;
- tests added or changed;
- documentation/release impact.

A PR is ready to merge only when required CI is green and review comments affecting correctness, compatibility, or security are resolved.

## Releases

Do not create or move release tags as part of a normal feature PR. Release identity and PyPI publication follow `RELEASING.md`.

Published versions and tags are immutable. Defects are fixed forward with a new version.

## Style

Prefer small, explicit interfaces and predictable errors over convenience magic. Preserve request IDs and diagnostic context where safe. Make validation deterministic and test negative cases, not only happy paths.
