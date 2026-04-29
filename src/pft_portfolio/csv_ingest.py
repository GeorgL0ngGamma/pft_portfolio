"""CSV ingestion for portfolio snapshots and transaction histories."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from .canonical import semantic_id
from .constants import (
    ASSET_SYMBOLS,
    DEFAULT_ACCOUNT_REF,
    DEFAULT_USER_ID,
    INSTRUMENT_TYPES,
    SNAPSHOT_EXPORT_COLUMNS,
    TRANSACTION_EXPORT_COLUMNS,
)


def ingest_portfolio_snapshot_csv(
    path: str | Path,
    *,
    user_id: str = DEFAULT_USER_ID,
    account_ref: str = DEFAULT_ACCOUNT_REF,
) -> dict[str, Any]:
    rows = _read_csv_rows(path)
    if rows and rows[0] and rows[0][0].startswith("Last updated"):
        return _ingest_cmc_snapshot(path, rows, user_id=user_id, account_ref=account_ref)
    return _ingest_standard_snapshot(path, user_id=user_id, account_ref=account_ref)


def ingest_transaction_history_csv(
    path: str | Path,
    *,
    user_id: str = DEFAULT_USER_ID,
    account_ref: str = DEFAULT_ACCOUNT_REF,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for source_row, row in enumerate(reader, start=2):
            timestamp = parse_timestamp(_pick(row, "timestamp", "time", "date"))
            record = {
                "input_type": "transaction_history",
                "user_id": _pick(row, "user_id") or user_id,
                "account_ref": _pick(row, "account_ref") or account_ref,
                "timestamp": timestamp,
                "activity_type": (_pick(row, "activity_type", "type", "side") or "trade").lower(),
                "asset_name": _pick(row, "asset_name", "name", "asset", "currency"),
                "symbol": _symbol(_pick(row, "symbol"), _pick(row, "asset_name", "name", "asset", "currency")),
                "instrument_type": _instrument_type(_pick(row, "instrument_type")),
                "amount": clean_decimal(_pick(row, "amount", "quantity", "qty", "size")),
                "price": clean_decimal(_pick(row, "price", "avg_buy_price")),
                "value": clean_decimal(_pick(row, "value", "holdings_value", "cost")),
                "currency": _pick(row, "currency", "valuation_ccy") or "USD",
                "profit_loss_value": clean_decimal(_pick(row, "profit_loss_value", "profit_loss", "pnl")),
                "profit_loss_pct": clean_percent(_pick(row, "profit_loss_pct", "profit_loss_percent", "pnl_pct")),
                "holdings_after": clean_decimal(_pick(row, "holdings_after", "balance_after")),
                "source_csv": Path(path).name,
                "source_row": source_row,
                "raw_row": _raw_row(row),
            }
            record.update(_extended_fields(row, record["symbol"], record["account_ref"]))
            record["id"] = semantic_id("txn", record)
            records.append(record)
    return {"input_type": "transaction_history", "transactions": records}


def write_snapshot_csv(path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    return write_csv(path, SNAPSHOT_EXPORT_COLUMNS, rows)


def write_transaction_csv(path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    return write_csv(path, TRANSACTION_EXPORT_COLUMNS, rows)


def write_csv(path: str | Path, columns: Iterable[str], rows: Iterable[dict[str, Any]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})
    return target


def clean_decimal(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "--":
        return None
    text = text.replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    try:
        return format(Decimal(text), "f")
    except InvalidOperation:
        return text


def clean_percent(value: Any) -> str | None:
    return clean_decimal(value)


def decimal_from_base_units(value: int | str, decimals: int) -> str:
    amount = Decimal(str(value)) / (Decimal(10) ** decimals)
    return format(amount, "f")


def parse_timestamp(value: str | None) -> str:
    if not value:
        raise ValueError("timestamp is required")
    text = value.strip()
    if text.endswith("Z") or "+" in text[10:] or re.search(r"-\d\d:\d\d$", text):
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    elif "T" in text:
        parsed = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    elif len(text) == 10:
        parsed = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return to_rfc3339(parsed)


def to_rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return to_rfc3339(datetime.now(timezone.utc))


def raw_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _ingest_cmc_snapshot(
    path: str | Path,
    rows: list[list[str]],
    *,
    user_id: str,
    account_ref: str,
) -> dict[str, Any]:
    assets_index = next(index for index, row in enumerate(rows) if row and row[0].strip() == "Assets")
    overview_pairs = {row[0]: row[1] for row in rows[:assets_index] if len(row) >= 2 and row[0]}
    as_of = _parse_cmc_as_of(next(iter(overview_pairs)), overview_pairs[next(iter(overview_pairs))])
    currency = overview_pairs.get("Currency") or "USD"
    overview = {
        "input_type": "portfolio_snapshot",
        "user_id": user_id,
        "account_ref": account_ref,
        "as_of": as_of,
        "currency": currency,
        "total_value": clean_decimal(_first_matching(overview_pairs, "Total value")),
        "total_value_change_24h": clean_decimal(_first_matching(overview_pairs, "24h Total value change (")),
        "total_value_change_24h_pct": clean_percent(_first_matching(overview_pairs, "24h Total value change%")),
        "all_time_profit_value": clean_decimal(_first_matching(overview_pairs, "All time profit (")),
        "all_time_profit_pct": clean_percent(_first_matching(overview_pairs, "All time profit change%")),
        "source_csv": Path(path).name,
        "raw_overview": dict(overview_pairs),
    }
    overview["id"] = semantic_id("overview", overview)

    asset_header = rows[assets_index + 1]
    positions: list[dict[str, Any]] = []
    for source_row, row in enumerate(rows[assets_index + 2 :], start=assets_index + 3):
        if not row or not any(cell.strip() for cell in row):
            continue
        raw = dict(zip(asset_header, row))
        asset_name = raw.get("Name") or raw.get("Asset")
        record = {
            "input_type": "portfolio_snapshot",
            "user_id": user_id,
            "account_ref": account_ref,
            "as_of": as_of,
            "currency": currency,
            "asset_name": asset_name,
            "symbol": _symbol(None, asset_name),
            "instrument_type": "spot",
            "price": clean_decimal(raw.get(f"Price ({currency})") or raw.get("Price (USD)") or raw.get("Price")),
            "change_1h_pct": clean_percent(raw.get("1h %")),
            "change_24h_pct": clean_percent(raw.get("24h %")),
            "change_7d_pct": clean_percent(raw.get("7d %")),
            "holdings_value": clean_decimal(raw.get(f"Holdings ({currency})") or raw.get("Holdings (USD)") or raw.get("Holdings")),
            "amount": clean_decimal(raw.get("Amount")),
            "avg_buy_price": clean_decimal(raw.get(f"Avg Buy Price ({currency})") or raw.get("Avg Buy Price (USD)") or raw.get("Avg Buy Price")),
            "profit_loss_value": clean_decimal(raw.get(f"Profit / Loss ({currency})") or raw.get("Profit / Loss (USD)") or raw.get("Profit / Loss")),
            "profit_loss_pct": clean_percent(raw.get("Profit / Loss %")),
            "source_csv": Path(path).name,
            "source_row": source_row,
            "raw_row": raw,
        }
        record.update(_extended_fields(raw, record["symbol"], record["account_ref"]))
        record["id"] = semantic_id("snapshot", record)
        positions.append(record)

    return {"input_type": "portfolio_snapshot", "overview": overview, "positions": positions}


def _ingest_standard_snapshot(path: str | Path, *, user_id: str, account_ref: str) -> dict[str, Any]:
    positions: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for source_row, row in enumerate(reader, start=2):
            as_of = parse_timestamp(_pick(row, "as_of", "timestamp", "time", "date"))
            record = {
                "input_type": "portfolio_snapshot",
                "user_id": _pick(row, "user_id") or user_id,
                "account_ref": _pick(row, "account_ref") or account_ref,
                "as_of": as_of,
                "currency": _pick(row, "currency", "valuation_ccy") or "USD",
                "asset_name": _pick(row, "asset_name", "name", "asset"),
                "symbol": _symbol(_pick(row, "symbol"), _pick(row, "asset_name", "name", "asset")),
                "instrument_type": _instrument_type(_pick(row, "instrument_type")),
                "price": clean_decimal(_pick(row, "price")),
                "change_1h_pct": clean_percent(_pick(row, "change_1h_pct", "1h %")),
                "change_24h_pct": clean_percent(_pick(row, "change_24h_pct", "24h %")),
                "change_7d_pct": clean_percent(_pick(row, "change_7d_pct", "7d %")),
                "holdings_value": clean_decimal(_pick(row, "holdings_value", "value")),
                "amount": clean_decimal(_pick(row, "amount", "quantity", "balance")),
                "avg_buy_price": clean_decimal(_pick(row, "avg_buy_price", "average_price", "entry_price")),
                "profit_loss_value": clean_decimal(_pick(row, "profit_loss_value", "profit_loss", "pnl")),
                "profit_loss_pct": clean_percent(_pick(row, "profit_loss_pct", "profit_loss_percent", "pnl_pct")),
                "source_csv": Path(path).name,
                "source_row": source_row,
                "raw_row": _raw_row(row),
            }
            record.update(_extended_fields(row, record["symbol"], record["account_ref"]))
            record["id"] = semantic_id("snapshot", record)
            positions.append(record)
    return {"input_type": "portfolio_snapshot", "overview": None, "positions": positions}


def _read_csv_rows(path: str | Path) -> list[list[str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _parse_cmc_as_of(label: str, value: str) -> str:
    match = re.search(r"UTC([+-])(\d+):(\d+)", label)
    if not match:
        return parse_timestamp(value)
    sign = 1 if match.group(1) == "+" else -1
    offset = timezone(sign * timedelta(hours=int(match.group(2)), minutes=int(match.group(3))))
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=offset)
    return to_rfc3339(parsed)


def _first_matching(values: dict[str, str], prefix: str) -> str | None:
    for key, value in values.items():
        if key.startswith(prefix):
            return value
    return None


def _pick(row: dict[str, Any], *keys: str) -> str | None:
    normalized = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()
    return None


def _symbol(symbol: str | None, asset_name: str | None) -> str | None:
    if symbol:
        return symbol.strip().upper() if "/" not in symbol else symbol.strip()
    if not asset_name:
        return None
    return ASSET_SYMBOLS.get(asset_name.strip().lower(), asset_name.strip().upper().replace(" ", "_"))


def _instrument_type(value: str | None) -> str:
    if not value:
        return "spot"
    normalized = value.strip().lower()
    return normalized if normalized in INSTRUMENT_TYPES else "spot"


def _extended_fields(row: dict[str, Any], symbol: str | None, account_ref: str | None) -> dict[str, str | None]:
    chain = _normalize_chain(_pick(row, "chain", "network", "blockchain")) or _chain_from_symbol_or_account(symbol, account_ref)
    venue = _pick(row, "venue", "exchange", "exchange_id") or _venue_from_account(account_ref)
    address = _pick(row, "address", "wallet_address", "chain_address") or _address_from_account(account_ref, chain)
    return {
        "asset_class": _pick(row, "asset_class") or ("crypto" if symbol else None),
        "chain": chain,
        "address": address,
        "contract_address": _pick(row, "contract_address", "token_address", "token_contract"),
        "tx_hash": _pick(row, "tx_hash", "txid", "hash", "signature"),
        "block_number": clean_decimal(_pick(row, "block_number", "block", "slot")),
        "log_index": clean_decimal(_pick(row, "log_index", "event_index", "instruction_index")),
        "external_id": _pick(row, "external_id", "trade_id", "order_id", "id"),
        "venue": venue,
        "protocol": _pick(row, "protocol"),
        "counterparty": _pick(row, "counterparty", "from", "to"),
        "fee_amount": clean_decimal(_pick(row, "fee_amount", "fee_cost")),
        "fee_symbol": _pick(row, "fee_symbol", "fee_currency"),
    }


def _normalize_chain(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    aliases = {
        "bitcoin": "BTC",
        "btc": "BTC",
        "ethereum": "ETH",
        "eth": "ETH",
        "solana": "SOL",
        "sol": "SOL",
    }
    return aliases.get(normalized, value.strip().upper())


def _chain_from_symbol_or_account(symbol: str | None, account_ref: str | None) -> str | None:
    if account_ref:
        prefix = account_ref.split(":", 1)[0].lower()
        if prefix in {"btc", "eth", "sol"}:
            return prefix.upper()
    if symbol in {"BTC", "ETH", "SOL"}:
        return symbol
    return None


def _venue_from_account(account_ref: str | None) -> str | None:
    if not account_ref:
        return None
    prefix, _, value = account_ref.partition(":")
    if prefix == "ccxt" and value:
        return value
    return None


def _address_from_account(account_ref: str | None, chain: str | None) -> str | None:
    if not account_ref or not chain:
        return None
    prefix, _, value = account_ref.partition(":")
    if prefix.lower() == chain.lower() and value:
        return value
    return None


def _raw_row(row: dict[str, Any]) -> dict[str, str]:
    return {str(key): "" if value is None else str(value) for key, value in row.items()}
