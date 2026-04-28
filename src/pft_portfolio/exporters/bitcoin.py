"""Bitcoin address exporters using an Esplora-compatible public API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..csv_ingest import decimal_from_base_units, raw_json, to_rfc3339, utc_now, write_snapshot_csv, write_transaction_csv
from .http import get_json


DEFAULT_API_BASE = "https://mempool.space/api"


def export_bitcoin_snapshot(
    address: str,
    output_path: str | Path,
    *,
    user_id: str = "demo",
    account_ref: str | None = None,
    api_base: str = DEFAULT_API_BASE,
    as_of: str | None = None,
) -> Path:
    data = get_json(f"{api_base.rstrip('/')}/address/{address}")
    funded = int(data.get("chain_stats", {}).get("funded_txo_sum", 0))
    spent = int(data.get("chain_stats", {}).get("spent_txo_sum", 0))
    amount = decimal_from_base_units(funded - spent, 8)
    return write_snapshot_csv(
        output_path,
        [
            {
                "user_id": user_id,
                "account_ref": account_ref or f"btc:{address}",
                "as_of": as_of or utc_now(),
                "currency": "USD",
                "asset_name": "Bitcoin",
                "symbol": "BTC",
                "instrument_type": "spot",
                "asset_class": "crypto",
                "chain": "BTC",
                "address": address,
                "price": None,
                "change_1h_pct": None,
                "change_24h_pct": None,
                "change_7d_pct": None,
                "holdings_value": None,
                "amount": amount,
                "avg_buy_price": None,
                "profit_loss_value": None,
                "profit_loss_pct": None,
                "raw_json": raw_json(data),
            }
        ],
    )


def export_bitcoin_transaction_history(
    address: str,
    output_path: str | Path,
    *,
    user_id: str = "demo",
    account_ref: str | None = None,
    api_base: str = DEFAULT_API_BASE,
    limit: int = 25,
) -> Path:
    txs = get_json(f"{api_base.rstrip('/')}/address/{address}/txs")[:limit]
    rows = [_tx_row(tx, address, user_id, account_ref or f"btc:{address}") for tx in txs]
    return write_transaction_csv(output_path, rows)


def _tx_row(tx: dict[str, Any], address: str, user_id: str, account_ref: str) -> dict[str, Any]:
    received = sum(int(out.get("value", 0)) for out in tx.get("vout", []) if out.get("scriptpubkey_address") == address)
    spent = sum(
        int((vin.get("prevout") or {}).get("value", 0))
        for vin in tx.get("vin", [])
        if (vin.get("prevout") or {}).get("scriptpubkey_address") == address
    )
    net = received - spent
    timestamp = tx.get("status", {}).get("block_time")
    return {
        "user_id": user_id,
        "account_ref": account_ref,
        "timestamp": to_rfc3339_from_seconds(timestamp),
        "activity_type": "deposit" if net >= 0 else "withdrawal",
        "asset_name": "Bitcoin",
        "symbol": "BTC",
        "instrument_type": "spot",
        "asset_class": "crypto",
        "chain": "BTC",
        "address": address,
        "tx_hash": tx.get("txid"),
        "external_id": tx.get("txid"),
        "amount": decimal_from_base_units(abs(net), 8),
        "price": None,
        "value": None,
        "currency": "USD",
        "profit_loss_value": None,
        "profit_loss_pct": None,
        "holdings_after": None,
        "raw_json": raw_json({"txid": tx.get("txid"), "received_sats": received, "spent_sats": spent}),
    }


def to_rfc3339_from_seconds(value: int | None) -> str:
    from datetime import datetime, timezone

    if value is None:
        return utc_now()
    return to_rfc3339(datetime.fromtimestamp(int(value), tz=timezone.utc))
