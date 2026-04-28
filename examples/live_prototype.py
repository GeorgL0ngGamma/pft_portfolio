"""Live BTC/ETH/SOL/Hyperliquid CSV-to-Postgres prototype proof."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pft_portfolio.csv_ingest import ingest_portfolio_snapshot_csv, ingest_transaction_history_csv
from pft_portfolio.exporters.bitcoin import export_bitcoin_snapshot, export_bitcoin_transaction_history
from pft_portfolio.exporters.ccxt_exchange import export_ccxt_portfolio_snapshot, export_ccxt_transaction_history
from pft_portfolio.exporters.ethereum import export_ethereum_snapshot, export_ethereum_transaction_history
from pft_portfolio.exporters.solana import export_solana_snapshot, export_solana_transaction_history
from pft_portfolio.postgres_store import PostgresPortfolioStore


BTC_GENESIS_ADDRESS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
ETH_FOUNDATION_ADDRESS = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"
WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"
HYPERLIQUID_TOP_VAULT = "0xd6e56265890b76413d1d527eb9b75e334c0c5b42"

COUNT_TABLES = (
    "users",
    "accounts",
    "ingestion_sources",
    "assets",
    "portfolio_views",
    "position_snapshots",
    "transactions",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the live CSV-to-Postgres prototype proof.")
    parser.add_argument("--output-dir", default="prototype-output")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--pftl-wallet-address", default="prototype-pftl-wallet")
    parser.add_argument("--btc-address", default=BTC_GENESIS_ADDRESS)
    parser.add_argument("--eth-address", default=ETH_FOUNDATION_ADDRESS)
    parser.add_argument("--sol-address", default=WRAPPED_SOL_MINT)
    parser.add_argument("--hyperliquid-vault", default=HYPERLIQUID_TOP_VAULT)
    parser.add_argument("--chain-transaction-limit", type=int, default=2)
    parser.add_argument("--hyperliquid-trade-limit", type=int, default=5)
    args = parser.parse_args(argv)

    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required for the live prototype")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    store = PostgresPortfolioStore.from_dsn(args.database_url)
    store.apply_migrations()

    source_summaries = [
        _process_btc(output_dir, args.btc_address, args.chain_transaction_limit, store, args.pftl_wallet_address),
        _process_eth(output_dir, args.eth_address, args.chain_transaction_limit, store, args.pftl_wallet_address),
        _process_sol(output_dir, args.sol_address, args.chain_transaction_limit, store, args.pftl_wallet_address),
        _process_hyperliquid(
            output_dir,
            args.hyperliquid_vault,
            args.hyperliquid_trade_limit,
            store,
            args.pftl_wallet_address,
        ),
    ]
    summary = {
        "prototype": "btc_eth_sol_hyperliquid_csv_to_postgres",
        "pftl_wallet_address": args.pftl_wallet_address,
        "sources": source_summaries,
        "postgres_counts": _table_counts(store.connection),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _process_btc(
    output_dir: Path,
    address: str,
    transaction_limit: int,
    store: PostgresPortfolioStore,
    pftl_wallet_address: str,
) -> dict[str, Any]:
    snapshot_csv = output_dir / "btc_snapshot.csv"
    transactions_csv = output_dir / "btc_transactions.csv"
    export_bitcoin_snapshot(address, snapshot_csv, user_id="prototype", account_ref=f"btc:{address}")
    export_bitcoin_transaction_history(
        address,
        transactions_csv,
        user_id="prototype",
        account_ref=f"btc:{address}",
        limit=transaction_limit,
    )
    return _ingest_pair("btc", address, snapshot_csv, transactions_csv, store, pftl_wallet_address)


def _process_eth(
    output_dir: Path,
    address: str,
    transaction_limit: int,
    store: PostgresPortfolioStore,
    pftl_wallet_address: str,
) -> dict[str, Any]:
    snapshot_csv = output_dir / "eth_snapshot.csv"
    transactions_csv = output_dir / "eth_transactions.csv"
    export_ethereum_snapshot(address, snapshot_csv, user_id="prototype", account_ref=f"eth:{address}")
    export_ethereum_transaction_history(
        address,
        transactions_csv,
        user_id="prototype",
        account_ref=f"eth:{address}",
        limit=transaction_limit,
    )
    return _ingest_pair("eth", address, snapshot_csv, transactions_csv, store, pftl_wallet_address)


def _process_sol(
    output_dir: Path,
    address: str,
    transaction_limit: int,
    store: PostgresPortfolioStore,
    pftl_wallet_address: str,
) -> dict[str, Any]:
    snapshot_csv = output_dir / "sol_snapshot.csv"
    transactions_csv = output_dir / "sol_transactions.csv"
    export_solana_snapshot(address, snapshot_csv, user_id="prototype", account_ref=f"sol:{address}")
    export_solana_transaction_history(
        address,
        transactions_csv,
        user_id="prototype",
        account_ref=f"sol:{address}",
        limit=transaction_limit,
    )
    return _ingest_pair("sol", address, snapshot_csv, transactions_csv, store, pftl_wallet_address)


def _process_hyperliquid(
    output_dir: Path,
    vault_address: str,
    trade_limit: int,
    store: PostgresPortfolioStore,
    pftl_wallet_address: str,
) -> dict[str, Any]:
    snapshot_csv = output_dir / "hyperliquid_vault_snapshot.csv"
    transactions_csv = output_dir / "hyperliquid_vault_transactions.csv"
    account_ref = f"hyperliquid:{vault_address}"
    params = {"user": vault_address}
    export_ccxt_portfolio_snapshot(
        "hyperliquid",
        snapshot_csv,
        user_id="prototype",
        account_ref=account_ref,
        params=params,
        fetch_balances=False,
    )
    export_ccxt_transaction_history(
        "hyperliquid",
        transactions_csv,
        user_id="prototype",
        account_ref=account_ref,
        params=params,
        limit=trade_limit,
    )
    return _ingest_pair("hyperliquid_vault", vault_address, snapshot_csv, transactions_csv, store, pftl_wallet_address)


def _ingest_pair(
    source: str,
    address: str,
    snapshot_csv: Path,
    transactions_csv: Path,
    store: PostgresPortfolioStore,
    pftl_wallet_address: str,
) -> dict[str, Any]:
    snapshot = ingest_portfolio_snapshot_csv(snapshot_csv)
    transactions = ingest_transaction_history_csv(transactions_csv)
    positions = snapshot.get("positions") or []
    transaction_rows = transactions.get("transactions") or []
    if not positions:
        raise RuntimeError(f"{source} produced no snapshot positions")
    if not transaction_rows:
        raise RuntimeError(f"{source} produced no transaction rows")

    stored_snapshot_records = store.add_snapshot_csv(snapshot_csv, pftl_wallet_address=pftl_wallet_address)
    stored_transaction_records = store.add_transaction_csv(transactions_csv, pftl_wallet_address=pftl_wallet_address)
    return {
        "source": source,
        "address": address,
        "snapshot_csv": str(snapshot_csv),
        "transactions_csv": str(transactions_csv),
        "positions": len(positions),
        "transactions": len(transaction_rows),
        "stored_snapshot_records": stored_snapshot_records,
        "stored_transaction_records": stored_transaction_records,
    }


def _table_counts(connection: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    cursor = connection.cursor()
    for table in COUNT_TABLES:
        cursor.execute(f"SELECT count(*) FROM {table}")
        row = cursor.fetchone()
        counts[table] = int(row[0]) if row else 0
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
