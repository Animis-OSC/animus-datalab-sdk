# Architecture

## System boundary

Animus DataLab is a governed ML infrastructure platform. Animus Link is a separate live managed-access product in the same Animus company portfolio; the two do not share an application runtime.

The Python SDK belongs to DataLab. It is the client-side projection used by CI systems, training containers and operator tooling to interact with the DataPilot gateway.

```text
CI / training / operator tooling
             |
       animus-datalab SDK
             |
        DataPilot Gateway
             |
   +---------+----------+
   |                    |
Dataset Registry    Experiments
                        |
                 Control Plane state
                        |
              project-scoped dispatch
                        |
                    Data Plane
```

## Authority

The SDK is not an independent source of API truth. Canonical external contracts are owned by DataLab under `core/contracts/openapi/` in the `animus-ml-datalab` repository. SDK methods are reviewed as projections of those contracts.

The 1.2 SDK line targets Dataset Registry `0.2.x` and Experiments `0.3.x`.

## Execution model

The Control Plane owns authoritative metadata, policy decisions, run identity, auditability and artifact mediation. User workloads execute in the Data Plane. The canonical execution transition is therefore an explicit project-scoped dispatch of an existing run.

`ExperimentsClient.execute_run()` maps a legacy compatibility endpoint and must not be used as the architectural model for new integrations. New integrations use `create_run()` followed by `dispatch_run()`.

## Runtime strategy

The SDK intentionally has zero runtime dependencies and ships as a universal pure-Python wheel. Network and file I/O dominate its normal workload, so native compilation is not a default optimization. Rust/PyO3 `abi3` extensions are reserved for measured CPU-bound kernels.

## Failure model

Transport failures are normalized into `AnimusAPIError`; response bodies are bounded; URL/header inputs are validated; large files are streamed; downloads are written atomically and may be size- and digest-constrained. Telemetry is best-effort and bounded so observability failure cannot crash a training workload.
