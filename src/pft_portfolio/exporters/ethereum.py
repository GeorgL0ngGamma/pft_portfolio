"""Ethereum address exporters using public JSON-RPC and Blockscout history."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..csv_ingest import decimal_from_base_units, raw_json, parse_timestamp, utc_now, write_snapshot_csv, write_transaction_csv
from .http import get_json, post_json


DEFAULT_RPC_URL = "https://ethereum-rpc.publicnode.com"
DEFAULT_BLOCKSCOUT_BASE = "https://eth.blockscout.com/api/v2"


def export_ethereum_snapshot(
    address: str,
    output_path: str | Path,
    *,
    user_id: str = "demo",
    account_ref: str | None = None,
    rpc_url: str = DEFAULT_RPC_URL,
    as_of: str | None = None,
) -> Path:
    response = post_json(
        rpc_url,
        {"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [address, "latest"]},
    )
    balance_wei = int(response["result"], 16)
    return write_snapshot_csv(
        output_path,
        [
            {
                "user_id": user_id,
                "account_ref": account_ref or f"eth:{address}",
                "as_of": as_of or utc_now(),
                "currency": "USD",
                "asset_name": "Ethereum",
                "symbol": "ETH",
                "instrument_type": "spot",
                "asset_class": "crypto",
                "chain": "ETH",
                "address": address,
                "price": None,
                "change_1h_pct": None,
                "change_24h_pct": None,
                "change_7d_pct": None,
                "holdings_value": None,
                "amount": decimal_from_base_units(balance_wei, 18),
                "avg_buy_price": None,
                "profit_loss_value": None,
                "profit_loss_pct": None,
                "raw_json": raw_json(response),
            }
        ],
    )


def export_ethereum_transaction_history(
    address: str,
    output_path: str | Path,
    *,
    user_id: str = "demo",
    account_ref: str | None = None,
    blockscout_base: str = DEFAULT_BLOCKSCOUT_BASE,
    limit: int = 25,
) -> Path:
    data = get_json(f"{blockscout_base.rstrip('/')}/addresses/{address}/transactions")
    rows = [_tx_row(tx, address, user_id, account_ref or f"eth:{address}") for tx in (data.get("items") or [])[:limit]]
    return write_transaction_csv(output_path, rows)


def _tx_row(tx: dict[str, Any], address: str, user_id: str, account_ref: str) -> dict[str, Any]:
    from_addr = ((tx.get("from") or {}).get("hash") or "").lower()
    to_addr = ((tx.get("to") or {}).get("hash") or "").lower()
    value_wei = int(tx.get("value") or 0)
    is_outbound = from_addr == address.lower() and to_addr != address.lower()
    timestamp = parse_timestamp(tx.get("timestamp")) if tx.get("timestamp") else utc_now()
    return {
        "user_id": user_id,
        "account_ref": account_ref,
        "timestamp": timestamp,
        "activity_type": "withdrawal" if is_outbound else "deposit",
        "asset_name": "Ethereum",
        "symbol": "ETH",
        "instrument_type": "spot",
        "asset_class": "crypto",
        "chain": "ETH",
        "address": address,
        "tx_hash": tx.get("hash"),
        "block_number": tx.get("block"),
        "external_id": tx.get("hash"),
        "counterparty": to_addr if is_outbound else from_addr,
        "amount": decimal_from_base_units(value_wei, 18),
        "price": None,
        "value": None,
        "currency": "USD",
        "profit_loss_value": None,
        "profit_loss_pct": None,
        "holdings_after": None,
        "raw_json": raw_json({"hash": tx.get("hash"), "status": tx.get("status"), "from": from_addr, "to": to_addr}),
    }
