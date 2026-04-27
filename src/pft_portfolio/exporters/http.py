"""Small HTTP JSON helpers for public chain exporters."""

from __future__ import annotations

import json
import urllib.request
from typing import Any


USER_AGENT = "pft-portfolio/0.1"


def get_json(url: str, *, timeout: int = 30) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def post_json(url: str, payload: dict[str, Any], *, timeout: int = 30) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)
