<p align="center">
  <img src="https://raw.githubusercontent.com/grewanderer/animus-datalab-sdk/main/assets/banner.png" width="100%" alt="Animus DataLab">
</p>

# Animus DataLab Python SDK

Typed, zero-runtime-dependency Python integration SDK for **Animus DataPilot / Animus DataLab**.

> Product boundary: **Animus Link is a separate live managed-access product.** Animus DataLab is the governed ML infrastructure platform in the same Animus systems portfolio. This repository is the client-side integration layer for DataLab; it is not part of the Animus Link runtime.

## Why this SDK exists

DataLab deliberately separates authoritative platform state from workload execution. The Control Plane owns metadata, policy, lineage, audit and artifact mediation; training and CI workloads run outside that process boundary. Those workloads still need a small, dependable way to report evidence and consume governed inputs.

This SDK is that boundary. It gives CI systems, training containers and operator tooling a stable Python projection of selected DataPilot gateway APIs without embedding DataLab server code or requiring a large dependency graph.

Typical uses:

- register and resolve datasets and immutable dataset versions;
- create experiments and immutable run records;
- dispatch an existing run to the Data Plane through the project-scoped execution API;
- stream metrics, progress and status evidence from training workloads;
- upload and download run artifacts without buffering whole files in memory;
- submit signed CI provenance;
- preserve request IDs and normalized failure semantics at the integration boundary.

## Contract ownership

**DataLab owns the API contracts. The SDK is a projection of those contracts.**

The 1.2 release line targets these current DataLab contract families:

- Dataset Registry API `0.2.x`;
- Experiments API `0.3.x`.

The canonical OpenAPI definitions live in the `animus-ml-datalab` repository under `core/contracts/openapi/`. SDK changes that affect HTTP paths, payloads or compatibility must be validated against those definitions before release.

`ExperimentsClient.execute_run()` remains available for compatibility, but DataLab marks `/experiments/runs:execute` as legacy. New integrations should create/resolve a run and use the project-scoped `dispatch_run()` API.

## Design goals

- **Zero runtime dependencies** by default: deploy cleanly into CI, training images, on-prem and air-gapped environments.
- **Bounded and integrity-aware I/O**: streaming uploads/downloads, atomic downloads, optional SHA-256 verification, bounded JSON/error bodies.
- **Predictable failure semantics**: normalized `AnimusAPIError`, stable request IDs, explicit validation instead of optimization-removable `assert` checks.
- **Typed distribution**: PEP 561 `py.typed` marker and Python 3.10-3.14 compatibility.
- **Non-blocking telemetry**: bounded background queue, retry with jitter, stable request IDs across retries and observable delivery counters.
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

project = client.datasets.create_project(
    name="fraud-ml",
    idempotency_key="project-fraud-ml-v1",
)

dataset = client.datasets.create_dataset(
    name="fraud-training",
    metadata={"owner": "ml"},
)

experiment = client.experiments.create_experiment(
    name="baseline",
    metadata={"team": "ml", "project": "fraud"},
)
```

`ExperimentsClient` and `DatasetRegistryClient` remain available directly for focused integrations.

## Environment variables

- `ANIMUS_GATEWAY_URL` - DataPilot gateway URL. Defaults to `http://localhost:8080` for local development.
- `ANIMUS_AUTH_TOKEN` - optional bearer token.
- `ANIMUS_CI_WEBHOOK_SECRET` - HMAC secret for signed CI webhook/report calls.
- `DATAPILOT_URL`, `RUN_ID`, `TOKEN` - execution-scoped values used by `RunTelemetryLogger.from_env()`.

## Dataset lifecycle

```python
from animus_sdk import DatasetRegistryClient

client = DatasetRegistryClient(gateway_url="https://datapilot.example.com")

client.create_dataset(
    name="fraud-training",
    metadata={"owner": "ml"},
    idempotency_key="dataset-fraud-training-v1",
)

version = client.upload_dataset_version(
    dataset_id="dataset-id",
    file_path="/data/train.zip",
    metadata={"source": "warehouse", "snapshot": "2026-08-28"},
    quality_rule_id="quality-rule-id",
    idempotency_key="dataset-version-2026-08-28",
)
```

Uploads are streamed; dataset downloads can be size-bounded and SHA-256 verified before the destination is atomically replaced.

## Experiments and canonical execution

```python
from animus_sdk import ExperimentsClient

client = ExperimentsClient(gateway_url="https://datapilot.example.com")

run = client.create_run(
    experiment_id="experiment-id",
    dataset_version_id="dataset-version-id",
    status="pending",
    params={"lr": 1e-3},
)

client.dispatch_run(
    project_id="project-id",
    run_id=str(run["run_id"]),
    idempotency_key="dispatch-build-123",
)
```

The project-scoped dispatch API is the canonical Control Plane → Data Plane boundary in the current Experiments contract. `execute_run()` is retained only for legacy compatibility.

Read surfaces include experiment/run listing, execution records, immutable build context and metric samples.

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

Telemetry is deliberately best-effort so an observability outage cannot crash training. `stats` exposes accepted, dropped, sent, failed and retried counts.

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

`retryable` describes transport/status retryability. Application-level retry safety still depends on operation semantics and idempotency guarantees.

## Performance and binary strategy

The SDK remains a universal **pure-Python wheel** intentionally. Its dominant paths are network and file I/O, so compiling the entire package with Cython/Nuitka would add platform-specific build and debugging cost without a justified end-to-end latency gain.

The production strategy is:

1. keep the public API typed and portable;
2. stream large payloads instead of copying them into RAM;
3. minimize allocations and use deterministic compact JSON;
4. validate on CPython 3.10-3.14;
5. introduce a Rust/PyO3 `abi3` native extension only when profiling identifies a CPU-bound kernel whose measured gain justifies the binary surface.

## Compatibility

SDK `1.2.x` is an additive compatibility line over DataLab Dataset Registry `0.2.x` and Experiments `0.3.x`. See `docs/COMPATIBILITY.md` for the compatibility policy and `docs/ARCHITECTURE.md` for the system boundary.

Python 3.10 remains supported in the 1.2 line for compatibility, but reaches upstream end-of-life in October 2026. New deployments should prefer Python 3.12-3.14.

## Release model

Releases use tags of the form:

```text
sdk-python-v1.2.0
```

The release workflow verifies compile, Ruff, mypy, tests/branch coverage, package metadata and tag/version identity before publishing. Publication uses PyPI OIDC Trusted Publishing with attestations. See `RELEASING.md`.

## License

Apache-2.0.
