from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class GitMetadata:
    repo: str
    commit: str
    ref: str = ""
    source: str = ""


def normalize_repo(value: str) -> str:
    value = value.strip()
    if not value:
        return ""

    if value.startswith("git@") and ":" in value:
        user_host, path = value.split(":", 1)
        host = user_host.split("@", 1)[1]
        path = path.lstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return f"{host}/{path}"

    if "://" in value:
        parsed = urlparse(value)
        host = (parsed.hostname or "").strip()
        path = (parsed.path or "").lstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if host and path:
            return f"{host}/{path}"
        return value.rstrip("/")

    value = value.rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value


def git_metadata_from_env(env: Mapping[str, str] | None = None) -> GitMetadata | None:
    values = os.environ if env is None else env

    github_sha = values.get("GITHUB_SHA", "").strip()
    github_repo = values.get("GITHUB_REPOSITORY", "").strip()
    if github_sha and github_repo:
        ref = (
            values.get("GITHUB_HEAD_REF", "")
            or values.get("GITHUB_REF_NAME", "")
            or values.get("GITHUB_REF", "")
        ).strip()
        repo = normalize_repo(f"github.com/{github_repo}")
        return GitMetadata(repo=repo, commit=github_sha, ref=ref, source="github")

    gitlab_sha = values.get("CI_COMMIT_SHA", "").strip()
    gitlab_host = values.get("CI_SERVER_HOST", "").strip()
    gitlab_path = values.get("CI_PROJECT_PATH", "").strip()
    if gitlab_sha and gitlab_host and gitlab_path:
        ref = (values.get("CI_COMMIT_REF_NAME", "") or values.get("CI_COMMIT_BRANCH", "")).strip()
        repo = normalize_repo(f"{gitlab_host}/{gitlab_path}")
        return GitMetadata(repo=repo, commit=gitlab_sha, ref=ref, source="gitlab")

    jenkins_sha = values.get("GIT_COMMIT", "").strip()
    jenkins_url = values.get("GIT_URL", "").strip()
    if jenkins_sha and jenkins_url:
        ref = values.get("GIT_BRANCH", "").strip()
        repo = normalize_repo(jenkins_url)
        return GitMetadata(repo=repo, commit=jenkins_sha, ref=ref, source="jenkins")

    return None


def git_metadata_from_git_cli(
    cwd: str | None = None,
    *,
    timeout_seconds: float = 2.0,
) -> GitMetadata | None:
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be > 0")

    process_env = dict(os.environ)
    process_env["GIT_TERMINAL_PROMPT"] = "0"

    def run(args: list[str]) -> str:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=process_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        return completed.stdout.strip()

    try:
        commit = run(["git", "rev-parse", "HEAD"])
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None

    repo = ""
    ref = ""
    try:
        repo = normalize_repo(run(["git", "remote", "get-url", "origin"]))
    except (OSError, subprocess.SubprocessError, UnicodeError):
        repo = ""
    try:
        ref = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if ref == "HEAD":
            ref = ""
    except (OSError, subprocess.SubprocessError, UnicodeError):
        ref = ""

    return GitMetadata(repo=repo, commit=commit, ref=ref, source="git")


def get_git_metadata(
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
) -> GitMetadata | None:
    meta = git_metadata_from_env(env)
    if meta is not None:
        return meta
    return git_metadata_from_git_cli(cwd=cwd)
