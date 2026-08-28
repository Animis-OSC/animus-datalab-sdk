<p align="center">
  <img src="https://raw.githubusercontent.com/grewanderer/animus-datalab-sdk/main/assets/banner.png" width="100%" alt="Animus DataLab">
</p>

# Animus DataLab Python SDK

Production-oriented, typed Python SDK for **Animus DataPilot** dataset, experiment, CI provenance, artifact, and live-training telemetry APIs.

## Design goals

- **Zero runtime dependencies** by default: deploy cleanly into CI, training images, on-prem, and air-gapped environments.
- **Bounded and integrity-aware I/O**: streaming uploads/downloads, atomic downloads, optional SHA-256 verification, bounded JSON/error bodies.
- **Predictable failure semantics**: normalized `AnimusAPIError`, stable request IDs, explicit validation instead of optimization-removable `assert` checks.
- **Typed distribution**: PEP 561 `py.typed` marker and Python 3.10-3.14 compatibility.
- **Non-blocking telemetry**: bounded background queue, retry with jitter, stable request IDs across retries, and observable delivery counters.
- **Supply-chain ready**: build verification on every change and PyPI Trusted Publishing/attestations on release.

## Install

```bash
pip install animus-datalab
```

Development from the repository root:

```bash
python -m pip install -e "python[dev]"
```

## Unified client

```python
from animus_sdk import AnimusClient

client = AnimusClient(
    gateway_url="https://datapilot.example.com",
    auth_token="...",
)

experiment = client.experiments.create_experiment(
    name="baseline",
    metadata={"team": "ml", "project": "fraud"},
)

dataset = client.datasets.get_dataset_version(
    dataset_version_id="dataset-version-id",
)
```

`ExperimentsClient` and `DatasetRegistryClient` remain available directly for focused integrations.

## Environment variables

- `ANIMUS_GATEWAY_URL` - DataPilot gateway URL. Defaults to `http://localhost:8080` for local development.
- `ANIMUS_AUTH_TOKEN` - optional bearer token.
- `ANIMUS_CI_WEBHOOK_SECRET` - HMAC secret for signed CI webhook/report calls.
- `DATAPILOT_URL`, `RUN_ID`, `TOKEN` - execution-scoped values used by `RunTelemetryLogger.from_env()`.

## Experiments and immutable run metadata

```python
from animus_sdk import ExperimentsClient

client = ExperimentsClient(gateway_url="https://datapilot.example.com")

exp = client.create_experiment(
    name="baseline",
    description="Baseline training run",
    metadata={"team": "ml"},
)

run = client.create_run(
    experiment_id=str(exp["experiment_id"]),
    dataset_version_id="dataset-version-id",
    status="succeeded",
    params={"lr": 1e-3},
    metrics={"accuracy": 0.91},
)
```

GitHub Actions, GitLab CI, Jenkins, and local git metadata are detected automatically when available.

## Signed CI provenance

```python
client.post_ci_report(
    payload={
        "image_digest": "sha256:...",
        "repo": "ghcr.io/acme/train",
        "commit_sha": "deadbeef...",
        "pipeline_id": "build-123",
        "provider": "github_actions",
    }
)
```

CI payload JSON is canonicalized and rejects non-standard values such as NaN/Infinity before signing.

## Artifact upload and integrity-checked download

Uploads are streamed instead of loading the artifact into memory.

```python
client.upload_run_artifact(
    run_id="run-id",
    kind="model",
    file_path="/tmp/model.bin",
    metadata={"format": "safetensors"},
)
```

Downloads are written to a temporary file in the destination directory, flushed, and atomically renamed only after completion. Optional size and digest constraints fail closed:

```python
meta = client.download_run_artifact(
    run_id="run-id",
    artifact_id="artifact-id",
    dest_path="/models/model.bin",
    max_bytes=8 * 1024 * 1024 * 1024,
    expected_sha256="0123456789abcdef" * 4,
)
```

## Live telemetry

```python
from animus_sdk import RunTelemetryLogger

with RunTelemetryLogger.from_env(timeout_seconds=2.0) as telemetry:
    telemetry.log_status(status="starting")

    for step in range(100):
        telemetry.log_metric(step=step, name="loss", value=1.0 / (step + 1))
        telemetry.log_progress(
            step=step,
            total_steps=100,
            percent=(step + 1) / 100.0,
        )

    telemetry.log_status(status="finished")
    print(telemetry.stats)
```

Telemetry is deliberately best-effort so an observability outage cannot crash training. `stats` exposes accepted, dropped, sent, failed, and retried counts.

## Error handling

```python
from animus_sdk import AnimusAPIError

try:
    client.experiments.get_run(run_id="run-id")
except AnimusAPIError as exc:
    print(exc.status, exc.code, exc.request_id)
    if exc.retryable:
        ...
```

`retryable` describes transport/status retryability. Application-level retry safety still depends on operation semantics.

## Performance and binary strategy

The SDK remains a universal **pure-Python wheel** intentionally. Its hot path is network and file I/O, so compiling the entire package with Cython/Nuitka would add platform-specific build and debugging cost without a justified end-to-end latency win.

The production strategy is:

1. keep the public API typed and portable;
2. stream large payloads instead of copying them into RAM;
3. minimize allocations and use deterministic compact JSON;
4. validate on CPython 3.10-3.14;
5. introduce a Rust/PyO3 `abi3` native extension only when profiling identifies a CPU-bound kernel whose measured gain justifies the binary surface.

This preserves one universal wheel today while keeping a clean path to native acceleration later.

## Release model

Releases use tags of the form:

```text
sdk-python-v1.1.0
```

The release workflow verifies tests, lint, typing, package metadata, and the tag/version match before publishing. PyPI publishing is configured for OIDC Trusted Publishing with attestations; the PyPI project must have the repository workflow registered as a Trusted Publisher.

## Compatibility note

Python 3.10 remains supported in the 1.1 line for compatibility, but it reaches upstream end-of-life in October 2026. New deployments should prefer Python 3.12-3.14.

## License

Apache-2.0.
