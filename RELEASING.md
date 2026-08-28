# Releasing Animus DataLab SDK

## Preconditions

A release is cut only from `main` after the exact candidate changes have passed the Python SDK CI workflow.

PyPI must have a Trusted Publisher configured for:

- repository: `grewanderer/animus-datalab-sdk`;
- workflow: `release-python-sdk.yml`;
- environment: `pypi`.

No long-lived PyPI API token is required by the release workflow.

## Release checklist

1. Confirm DataLab OpenAPI compatibility for every changed SDK HTTP surface.
2. Update `CHANGELOG.md` and `animus_sdk._version.__version__`.
3. Merge through CI with all Python, platform and package jobs green.
4. Confirm the post-merge CI run is green on the exact `main` SHA.
5. Create an immutable tag `sdk-python-vX.Y.Z` pointing to that exact SHA.
6. The tag-triggered release workflow re-runs compile, Ruff, mypy, tests/coverage, build and `twine check` before OIDC publication.
7. Verify the resulting PyPI files and provenance/attestations before announcing the release.
8. Update the canonical SDK gitlink in `animus-ml-datalab` to the released SDK SHA and validate its submodule/integration gates.

## Rollback

Published PyPI versions and public Git tags are immutable release identities and must not be rewritten. If a release is defective, fix forward with a new version. Server rollout rollback is handled independently by DataLab deployment procedures.

## Historical tag warning

Repository history contains legacy tags created before the current release process. Do not move or reuse them. New releases always use a fresh semantic version and an exact verified commit.
