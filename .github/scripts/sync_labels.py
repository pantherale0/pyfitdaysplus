#!/usr/bin/env python3
"""Sync .github/labels.toml with GitHub issue labels."""

from __future__ import annotations

import json
import os
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_VERSION = "2022-11-28"
LABEL_KEYS = ("name", "color", "description")


def github_request(
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": API_VERSION,
    }
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read().decode()
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        msg = f"GitHub API {method} {url} failed: {exc.code} {detail}"
        raise SystemExit(msg) from exc


def list_labels(owner: str, repo: str, token: str) -> dict[str, dict[str, str]]:
    labels: dict[str, dict[str, str]] = {}
    page = 1
    while True:
        url = (
            f"https://api.github.com/repos/{owner}/{repo}/labels"
            f"?per_page=100&page={page}"
        )
        batch = github_request("GET", url, token)
        if not batch:
            break
        for label in batch:
            labels[label["name"]] = {
                key: label[key] for key in LABEL_KEYS if key in label
            }
        page += 1
    return labels


def load_config(path: Path) -> dict[str, dict[str, str]]:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    desired: dict[str, dict[str, str]] = {}
    for section, values in raw.items():
        if not isinstance(values, dict):
            continue
        desired[values.get("name", section)] = {
            "name": values["name"],
            "color": values["color"].lstrip("#"),
            "description": values.get("description", ""),
        }
    return desired


def sync_labels(owner: str, repo: str, token: str, config_path: Path) -> None:
    desired = load_config(config_path)
    current = list_labels(owner, repo, token)

    for name, label in desired.items():
        payload = {
            "name": label["name"],
            "color": label["color"],
            "description": label["description"],
        }
        if name in current:
            if current[name] == payload:
                continue
            url = (
                f"https://api.github.com/repos/{owner}/{repo}/labels/"
                f"{urllib.parse.quote(name)}"
            )
            github_request("PATCH", url, token, payload)
            print(f"Updated label: {name}")
        else:
            url = f"https://api.github.com/repos/{owner}/{repo}/labels"
            github_request("POST", url, token, payload)
            print(f"Created label: {name}")


def main() -> None:
    repository = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repository or not token:
        msg = "GITHUB_REPOSITORY and GITHUB_TOKEN must be set"
        raise SystemExit(msg)

    owner, repo = repository.split("/", 1)
    config_path = Path(os.environ.get("LABELS_FILE", ".github/labels.toml"))
    if not config_path.exists():
        msg = f"Labels config not found: {config_path}"
        raise SystemExit(msg)

    sync_labels(owner, repo, token, config_path)


if __name__ == "__main__":
    main()
