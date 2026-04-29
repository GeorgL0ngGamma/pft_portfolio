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


PROVENANCE_FIELDS = {"id", "source_csv", "source_row", "raw_row", "raw_json", "raw_overview"}


def semantic_id(namespace: str, value: dict[str, Any]) -> str:
    """Stable identifier for the economic event, not the CSV row that carried it."""
    return stable_id(namespace, semantic_identity(value))


def semantic_identity(value: dict[str, Any]) -> dict[str, Any]:
    input_type = value.get("input_type")
    if input_type == "portfolio_snapshot" and value.get("asset_name"):
        return _identity(
            value,
            "input_type",
            "user_id",
            "account_ref",
            "as_of",
            "symbol",
            "instrument_type",
            "asset_class",
            "chain",
            "address",
            "contract_address",
            "venue",
            "protocol",
        )
    if input_type == "portfolio_snapshot":
        return _identity(value, "input_type", "user_id", "account_ref", "as_of", "currency")
    if input_type == "transaction_history" and value.get("venue") and value.get("external_id"):
        return _identity(value, "input_type", "user_id", "venue", "external_id")
    if (
        input_type == "transaction_history"
        and value.get("chain")
        and value.get("tx_hash")
        and _has_value(value.get("log_index"))
    ):
        return _identity(value, "input_type", "user_id", "chain", "tx_hash", "log_index")
    if input_type == "transaction_history" and value.get("chain") and value.get("tx_hash"):
        return _identity(
            value,
            "input_type",
            "user_id",
            "chain",
            "tx_hash",
            "activity_type",
            "symbol",
            "instrument_type",
            "amount",
            "value",
            "fee_amount",
            "fee_symbol",
        )
    if input_type == "transaction_history" and value.get("tx_hash"):
        return _identity(value, "input_type", "user_id", "account_ref", "tx_hash", "log_index", "activity_type")
    if input_type == "transaction_history" and value.get("external_id"):
        return _identity(value, "input_type", "user_id", "account_ref", "external_id", "activity_type")
    if input_type == "transaction_history":
        return _identity(
            value,
            "input_type",
            "user_id",
            "account_ref",
            "timestamp",
            "activity_type",
            "symbol",
            "instrument_type",
            "amount",
            "price",
            "value",
            "currency",
        )
    return {key: item for key, item in value.items() if key not in PROVENANCE_FIELDS}


def _identity(value: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value.get(key) for key in keys}


def _has_value(value: Any) -> bool:
    return value not in (None, "")
