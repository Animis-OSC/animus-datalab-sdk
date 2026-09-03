# Releasing Animus DataLab SDK

## Preconditions

A release is cut only from `main` after the exact candidate changes have passed the Python SDK CI workflow.

PyPI must have a Trusted Publisher configured for:

- repository: `Animus-OSC/animus-datalab-sdk`;
- workflow: `release-python-sdk.yml`;
- environment: `pypi`.

No long-lived PyPI API token is required by the release workflow.

Before tagging, verify that the PyPI Trusted Publisher configuration still names the canonical organization repository. Repository transfers or renames do not make the external PyPI publisher configuration update itself.

## Release checklist

1. Confirm DataLab OpenAPI compatibility for every changed SDK HTTP surface.
2. Update `CHANGELOG.md` and `animus_sdk._version.__version__`.
3. Merge through CI with all Python, platform and package jobs green.
4. Confirm the post-merge CI run is green on the exact `main` SHA.
5. Confirm the PyPI Trusted Publisher target is `Animus-OSC/animus-datalab-sdk`, workflow `release-python-sdk.yml`, environment `pypi`.
6. Create an immutable tag `sdk-python-vX.Y.Z` pointing to that exact SHA.
7. The tag-triggered release workflow re-runs compile, Ruff, mypy, tests/coverage, build and `twine check` before OIDC publication.
8. Verify the resulting PyPI files and provenance/attestations before announcing the release.
9. Update the canonical SDK gitlink in `animus-ml-datalab` to the released SDK SHA and validate its submodule/integration gates.

## Rollback

Published PyPI versions and public Git tags are immutable release identities and must not be rewritten. If a release is defective, fix forward with a new version. Server rollout rollback is handled independently by DataLab deployment procedures.

## Historical tag warning

Repository history contains legacy tags created before the current release process. Do not move or reuse them. New releases always use a fresh semantic version and an exact verified commit.
