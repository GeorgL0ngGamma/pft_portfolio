"""Canonical JSON helpers for deterministic local records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(namespace: str, value: dict[str, Any]) -> str:
    prepared = {key: item for key, item in value.items() if key != "id"}
    digest = hashlib.sha256(canonical_json(prepared).encode("utf-8")).hexdigest()[:24]
    return f"{namespace}_{digest}"
