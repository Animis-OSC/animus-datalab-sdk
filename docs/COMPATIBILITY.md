# Compatibility policy

## Contract baseline

SDK 1.2.x targets:

- DataLab Dataset Registry API 0.2.x;
- DataLab Experiments API 0.3.x.

The DataLab OpenAPI definitions are authoritative. The SDK must not silently invent behavior that contradicts those contracts.

## SDK versioning

The SDK follows semantic versioning for its Python public API.

- Patch: bug fixes and contract-preserving reliability changes.
- Minor: additive methods, newly projected DataLab endpoints, and deprecation notices that preserve existing behavior.
- Major: removal or incompatible change of an SDK public API.

A server-side DataLab contract can still require an SDK minor or major update depending on the effect on the Python surface.

## Deprecation

Public SDK functionality is deprecated before removal. A deprecated compatibility method remains usable for at least two SDK minor releases unless retaining it creates a security or correctness defect.

`ExperimentsClient.execute_run()` is legacy in DataLab Experiments 0.3.x. It remains in SDK 1.2 for compatibility. New code should use `create_run()` and `dispatch_run()`.

## Python runtimes

SDK 1.2 supports CPython 3.10 through 3.14. Python 3.10 reaches upstream end-of-life in October 2026; new deployments should prefer 3.12-3.14. Dropping a Python minor is announced in release notes before enforcement when practical.

## HTTP compatibility

Dynamic path components are percent-encoded. Error bodies are normalized into `AnimusAPIError`. Unknown additive response fields are tolerated because DataLab response evolution is expected to be additive within compatible contract lines.

## Release gate

A release candidate must pass lint, static typing, tests with branch-coverage threshold, Linux Python matrix, macOS/Windows smoke tests, source/wheel build validation and clean-wheel installation before a release tag is created.
