"""Generic CCXT exporter: exchange account data to standard CSV files."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..csv_ingest import raw_json, to_rfc3339, utc_now, write_snapshot_csv, write_transaction_csv


def export_ccxt_portfolio_snapshot(
    exchange_id: str,
    output_path: str | Path,
    *,
    user_id: str = "demo",
    account_ref: str | None = None,
    params: dict[str, Any] | None = None,
    exchange_options: dict[str, Any] | None = None,
    fetch_balances: bool = True,
    fetch_positions: bool = True,
    as_of: str | None = None,
) -> Path:
    exchange = _make_exchange(exchange_id, exchange_options)
    account = account_ref or f"ccxt:{exchange_id}"
    fetch_params = params or {}
    venue_address = _venue_address(fetch_params)
    timestamp = as_of or utc_now()
    rows: list[dict[str, Any]] = []
    errors: list[Exception] = []

    if fetch_balances and exchange.has.get("fetchBalance"):
        try:
            balance = exchange.fetch_balance(fetch_params)
            rows.extend(_balance_rows(balance, exchange_id, user_id, account, timestamp, venue_address))
        except Exception as exc:  # pragma: no cover - exercised by live exchange differences
            errors.append(exc)

    if fetch_positions and exchange.has.get("fetchPositions"):
        try:
            positions = exchange.fetch_positions(None, fetch_params)
            rows.extend(_position_rows(positions, exchange_id, user_id, account, timestamp, venue_address))
        except Exception as exc:  # pragma: no cover - exercised by live exchange differences
            errors.append(exc)

    if not rows and errors:
        raise errors[0]
    return write_snapshot_csv(output_path, rows)


def export_ccxt_transaction_history(
    exchange_id: str,
    output_path: str | Path,
    *,
    user_id: str = "demo",
    account_ref: str | None = None,
    symbol: str | None = None,
    since: int | None = None,
    limit: int | None = 100,
    params: dict[str, Any] | None = None,
    exchange_options: dict[str, Any] | None = None,
) -> Path:
    exchange = _make_exchange(exchange_id, exchange_options)
    if not exchange.has.get("fetchMyTrades"):
        raise NotImplementedError(f"{exchange_id} does not advertise fetchMyTrades in CCXT")
    account = account_ref or f"ccxt:{exchange_id}"
    fetch_params = params or {}
    venue_address = _venue_address(fetch_params)
    trades = exchange.fetch_my_trades(symbol, since, limit, fetch_params)
    rows: list[dict[str, Any]] = []
    for trade in trades:
        rows.append(_trade_row(trade, exchange_id, user_id, account, venue_address))
        fee = trade.get("fee") or {}
        if fee.get("cost") not in (None, "", 0, "0", "0.0"):
            rows.append(_fee_row(trade, exchange_id, user_id, account, venue_address))
    return write_transaction_csv(output_path, rows)


def _make_exchange(exchange_id: str, exchange_options: dict[str, Any] | None):
    try:
        import ccxt  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Install ccxt or use the exchange extra: pip install -e '.[exchange]'") from exc
    exchange_class = getattr(ccxt, exchange_id)
    options = {"enableRateLimit": True}
    options.update(exchange_options or {})
    return exchange_class(options)


def _balance_rows(
    balance: dict[str, Any], exchange_id: str, user_id: str, account_ref: str, as_of: str, address: str | None
) -> list[dict[str, Any]]:
    rows = []
    totals = balance.get("total") or {}
    for asset, amount in sorted(totals.items()):
        if _is_zero(amount):
            continue
        rows.append(
            {
                "user_id": user_id,
                "account_ref": account_ref,
                "as_of": as_of,
                "currency": "USD",
                "asset_name": asset,
                "symbol": asset,
                "instrument_type": "spot",
                "asset_class": "crypto",
                "address": address,
                "venue": exchange_id,
                "price": None,
                "change_1h_pct": None,
                "change_24h_pct": None,
                "change_7d_pct": None,
                "holdings_value": None,
                "amount": str(amount),
                "avg_buy_price": None,
                "profit_loss_value": None,
                "profit_loss_pct": None,
                "raw_json": raw_json({"exchange_id": exchange_id, "balance": balance.get(asset, {})}),
            }
        )
    return rows


def _position_rows(
    positions: list[dict[str, Any]], exchange_id: str, user_id: str, account_ref: str, as_of: str, address: str | None
) -> list[dict[str, Any]]:
    rows = []
    for position in positions:
        amount = position.get("contracts") or position.get("contractSize") or _info(position).get("szi")
        if _is_zero(amount):
            continue
        side = str(position.get("side") or "").lower()
        signed_amount = _signed_amount(amount, side)
        symbol = position.get("symbol") or _info(position).get("coin")
        rows.append(
            {
                "user_id": user_id,
                "account_ref": account_ref,
                "as_of": as_of,
                "currency": position.get("settle") or position.get("quote") or "USDC",
                "asset_name": position.get("base") or _asset_from_symbol(symbol),
                "symbol": symbol,
                "instrument_type": _instrument_type_from_position(position),
                "asset_class": "crypto",
                "address": address,
                "venue": exchange_id,
                "external_id": position.get("id"),
                "price": _first(position, "markPrice", "entryPrice"),
                "change_1h_pct": None,
                "change_24h_pct": None,
                "change_7d_pct": None,
                "holdings_value": _first(position, "notional", "initialMargin"),
                "amount": signed_amount,
                "avg_buy_price": position.get("entryPrice"),
                "profit_loss_value": position.get("unrealizedPnl"),
                "profit_loss_pct": position.get("percentage"),
                "raw_json": raw_json({"exchange_id": exchange_id, "position": position}),
            }
        )
    return rows


def _trade_row(trade: dict[str, Any], exchange_id: str, user_id: str, account_ref: str, address: str | None = None) -> dict[str, Any]:
    timestamp = _timestamp_ms_to_rfc3339(trade.get("timestamp"))
    symbol = trade.get("symbol")
    info = _info(trade)
    return {
        "user_id": user_id,
        "account_ref": account_ref,
        "timestamp": timestamp,
        "activity_type": str(trade.get("side") or "trade").lower(),
        "asset_name": _asset_from_symbol(symbol),
        "symbol": symbol,
        "instrument_type": _instrument_type_from_symbol(symbol),
        "asset_class": "crypto",
        "address": address,
        "tx_hash": info.get("hash"),
        "venue": exchange_id,
        "external_id": trade.get("id") or trade.get("order"),
        "fee_amount": (trade.get("fee") or {}).get("cost"),
        "fee_symbol": (trade.get("fee") or {}).get("currency"),
        "amount": trade.get("amount"),
        "price": trade.get("price"),
        "value": trade.get("cost"),
        "currency": "USD",
        "profit_loss_value": info.get("closedPnl"),
        "profit_loss_pct": None,
        "holdings_after": info.get("startPosition"),
        "raw_json": raw_json({"exchange_id": exchange_id, "trade": trade}),
    }


def _fee_row(trade: dict[str, Any], exchange_id: str, user_id: str, account_ref: str, address: str | None = None) -> dict[str, Any]:
    fee = trade.get("fee") or {}
    info = _info(trade)
    return {
        "user_id": user_id,
        "account_ref": account_ref,
        "timestamp": _timestamp_ms_to_rfc3339(trade.get("timestamp")),
        "activity_type": "fee",
        "asset_name": fee.get("currency"),
        "symbol": fee.get("currency"),
        "instrument_type": "spot",
        "asset_class": "crypto",
        "address": address,
        "tx_hash": info.get("hash"),
        "venue": exchange_id,
        "external_id": f"fee:{trade.get('id') or trade.get('order')}",
        "fee_amount": fee.get("cost"),
        "fee_symbol": fee.get("currency"),
        "amount": fee.get("cost"),
        "price": "1",
        "value": fee.get("cost"),
        "currency": fee.get("currency") or "USD",
        "profit_loss_value": None,
        "profit_loss_pct": None,
        "holdings_after": None,
        "raw_json": raw_json({"exchange_id": exchange_id, "fee_for_trade": trade.get("id") or trade.get("order")}),
    }


def _timestamp_ms_to_rfc3339(value: Any) -> str | None:
    if value is None:
        return None
    from datetime import datetime, timezone

    return to_rfc3339(datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc))


def _info(value: dict[str, Any]) -> dict[str, Any]:
    info = value.get("info")
    return info if isinstance(info, dict) else {}


def _venue_address(params: dict[str, Any]) -> str | None:
    user = params.get("user")
    return str(user) if user not in (None, "") else None


def _first(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if value.get(key) not in (None, ""):
            return value[key]
    return None


def _is_zero(value: Any) -> bool:
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, TypeError):
        return value in (None, "", 0)


def _signed_amount(value: Any, side: str) -> str:
    amount = Decimal(str(value))
    if side == "short" and amount > 0:
        amount = -amount
    return format(amount, "f")


def _asset_from_symbol(symbol: Any) -> str | None:
    if not symbol:
        return None
    text = str(symbol)
    return text.split("/")[0].split(":")[0]


def _instrument_type_from_position(position: dict[str, Any]) -> str:
    symbol = str(position.get("symbol") or "")
    if position.get("expiry"):
        return "future"
    if position.get("option"):
        return "option"
    if position.get("contract") or ":" in symbol:
        return "perp"
    return "spot"


def _instrument_type_from_symbol(symbol: Any) -> str:
    if not symbol:
        return "spot"
    return "perp" if ":" in str(symbol) else "spot"
