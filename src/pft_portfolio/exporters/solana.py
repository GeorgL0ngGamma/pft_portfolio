"""Solana address exporters using public JSON-RPC."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..csv_ingest import decimal_from_base_units, raw_json, to_rfc3339, utc_now, write_snapshot_csv, write_transaction_csv
from .http import post_json


DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


def export_solana_snapshot(
    address: str,
    output_path: str | Path,
    *,
    user_id: str = "demo",
    account_ref: str | None = None,
    rpc_url: str = DEFAULT_RPC_URL,
    as_of: str | None = None,
) -> Path:
    response = _rpc(rpc_url, "getBalance", [address])
    lamports = int(response["result"]["value"])
    return write_snapshot_csv(
        output_path,
        [
            {
                "user_id": user_id,
                "account_ref": account_ref or f"sol:{address}",
                "as_of": as_of or utc_now(),
                "currency": "USD",
                "asset_name": "Solana",
                "symbol": "SOL",
                "instrument_type": "spot",
                "asset_class": "crypto",
                "chain": "SOL",
                "address": address,
                "price": None,
                "change_1h_pct": None,
                "change_24h_pct": None,
                "change_7d_pct": None,
                "holdings_value": None,
                "amount": decimal_from_base_units(lamports, 9),
                "avg_buy_price": None,
                "profit_loss_value": None,
                "profit_loss_pct": None,
                "raw_json": raw_json(response),
            }
        ],
    )


def export_solana_transaction_history(
    address: str,
    output_path: str | Path,
    *,
    user_id: str = "demo",
    account_ref: str | None = None,
    rpc_url: str = DEFAULT_RPC_URL,
    limit: int = 10,
) -> Path:
    signatures = _rpc(rpc_url, "getSignaturesForAddress", [address, {"limit": limit}])["result"]
    rows = []
    for signature in signatures:
        tx = _rpc(
            rpc_url,
            "getTransaction",
            [signature["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0}],
        ).get("result")
        rows.append(_tx_row(signature, tx, address, user_id, account_ref or f"sol:{address}"))
    return write_transaction_csv(output_path, rows)


def _rpc(url: str, method: str, params: list[Any]) -> dict[str, Any]:
    response = post_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response


def _tx_row(signature: dict[str, Any], tx: dict[str, Any] | None, address: str, user_id: str, account_ref: str) -> dict[str, Any]:
    delta = _native_balance_delta(tx, address) if tx else 0
    return {
        "user_id": user_id,
        "account_ref": account_ref,
        "timestamp": _seconds_to_rfc3339(signature.get("blockTime")),
        "activity_type": "deposit" if delta >= 0 else "withdrawal",
        "asset_name": "Solana",
        "symbol": "SOL",
        "instrument_type": "spot",
        "asset_class": "crypto",
        "chain": "SOL",
        "address": address,
        "tx_hash": signature.get("signature"),
        "block_number": signature.get("slot"),
        "external_id": signature.get("signature"),
        "amount": decimal_from_base_units(abs(delta), 9),
        "price": None,
        "value": None,
        "currency": "USD",
        "profit_loss_value": None,
        "profit_loss_pct": None,
        "holdings_after": None,
        "raw_json": raw_json({"signature": signature.get("signature"), "slot": signature.get("slot"), "err": signature.get("err")}),
    }


def _native_balance_delta(tx: dict[str, Any], address: str) -> int:
    message = tx.get("transaction", {}).get("message", {})
    account_keys = message.get("accountKeys") or []
    keys = [item.get("pubkey") if isinstance(item, dict) else item for item in account_keys]
    if address not in keys:
        return 0
    index = keys.index(address)
    meta = tx.get("meta") or {}
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    if index >= len(pre) or index >= len(post):
        return 0
    return int(post[index]) - int(pre[index])


def _seconds_to_rfc3339(value: int | None) -> str:
    from datetime import datetime, timezone

    if value is None:
        return utc_now()
    return to_rfc3339(datetime.fromtimestamp(int(value), tz=timezone.utc))
