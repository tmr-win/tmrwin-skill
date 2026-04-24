#!/usr/bin/env python3
"""Check whether a newer public tmrwin-skill version is available."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from _common import (
    SKILL_INSTALL_COMMAND,
    SKILL_MANIFEST_URL,
    SKILL_NAME,
    SKILL_REPO_URL,
    SKILL_VERSION,
    print_json,
)

VERSION_CHECK_SCHEMA = "tmrwin-skill-version-check-v1"


def parse_version(value: str) -> tuple[int, ...]:
    """Parse a dotted numeric version string."""

    cleaned = str(value or "").strip()
    if cleaned.startswith(("v", "V")):
        cleaned = cleaned[1:]
    if not cleaned:
        raise ValueError("version is empty")
    parts = cleaned.split(".")
    numbers: list[int] = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"invalid version segment: {part}")
        numbers.append(int(part))
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)


def is_remote_newer(local_version: str, remote_version: str) -> bool:
    """Return whether the remote version is newer than the local version."""

    local = parse_version(local_version)
    remote = parse_version(remote_version)
    width = max(len(local), len(remote))
    local = local + (0,) * (width - len(local))
    remote = remote + (0,) * (width - len(remote))
    return remote > local


def load_remote_manifest(url: str, *, timeout: int) -> dict[str, Any]:
    """Fetch the remote version manifest."""

    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("remote manifest is not a JSON object")
    return payload


def result_payload(
    *,
    status: str,
    summary: str,
    local_version: str,
    latest_version: str | None,
    update_available: bool,
    manifest_url: str,
    repo_url: str,
    install_command: str,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable version-check result."""

    payload: dict[str, Any] = {
        "schema": VERSION_CHECK_SCHEMA,
        "skill_name": SKILL_NAME,
        "status": status,
        "local_version": local_version,
        "latest_version": latest_version,
        "update_available": update_available,
        "manifest_url": manifest_url,
        "repo_url": repo_url,
        "install_command": install_command,
        "summary": summary,
    }
    if diagnostics:
        payload["diagnostics"] = diagnostics
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="check whether a newer tmrwin-skill version is available")
    parser.add_argument("--manifest-url", default=None)
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    manifest_url = args.manifest_url or os.environ.get("TMRWIN_SKILL_MANIFEST_URL") or SKILL_MANIFEST_URL

    try:
        remote_manifest = load_remote_manifest(manifest_url, timeout=args.timeout)
        latest_version = str(remote_manifest.get("version") or "").strip()
        if not latest_version:
            raise ValueError("remote manifest misses version")
        repo_url = str(remote_manifest.get("repo_url") or SKILL_REPO_URL).strip() or SKILL_REPO_URL
        install_command = str(remote_manifest.get("install_command") or SKILL_INSTALL_COMMAND).strip() or SKILL_INSTALL_COMMAND
        if is_remote_newer(SKILL_VERSION, latest_version):
            print_json(
                result_payload(
                    status="update_available",
                    summary=f"a newer tmrwin-skill version is available: {latest_version}",
                    local_version=SKILL_VERSION,
                    latest_version=latest_version,
                    update_available=True,
                    manifest_url=manifest_url,
                    repo_url=repo_url,
                    install_command=install_command,
                )
            )
            return 0
        print_json(
            result_payload(
                status="up_to_date",
                summary="tmrwin-skill is up to date",
                local_version=SKILL_VERSION,
                latest_version=latest_version,
                update_available=False,
                manifest_url=manifest_url,
                repo_url=repo_url,
                install_command=install_command,
            )
        )
        return 0
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print_json(
            result_payload(
                status="unknown",
                summary="could not check for a newer tmrwin-skill version",
                local_version=SKILL_VERSION,
                latest_version=None,
                update_available=False,
                manifest_url=manifest_url,
                repo_url=SKILL_REPO_URL,
                install_command=SKILL_INSTALL_COMMAND,
                diagnostics={"failure_reason": "version_check_failed", "error": str(exc)},
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
