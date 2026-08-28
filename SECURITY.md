# Security Policy

## Supported releases

Security fixes target the latest `1.x` SDK release. Older releases may receive fixes when a vulnerability materially affects compatibility or safe upgrade paths.

## Reporting a vulnerability

Please use GitHub's private **Report a vulnerability / Security Advisory** flow for this repository. Do not open a public issue for suspected credential exposure, authentication bypasses, request-signing weaknesses, path/header injection, or other exploitable findings.

Include:

- affected SDK version and Python version;
- minimal reproduction;
- expected versus actual behavior;
- whether credentials, integrity, confidentiality, or availability are affected;
- any proposed mitigation.

## Security posture

The SDK treats bearer tokens and CI webhook secrets as sensitive, rejects credentials embedded in gateway URLs, bounds response bodies, rejects CR/LF header injection, performs artifact downloads atomically, and can verify SHA-256 digests before exposing downloaded files at their destination path.
