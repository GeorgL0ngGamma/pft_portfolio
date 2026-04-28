from __future__ import annotations

from pathlib import Path

import pytest

from pft_portfolio.csv_ingest import ingest_portfolio_snapshot_csv, ingest_transaction_history_csv
from pft_portfolio.exporters.bitcoin import export_bitcoin_snapshot, export_bitcoin_transaction_history
from pft_portfolio.exporters.ccxt_exchange import export_ccxt_portfolio_snapshot, export_ccxt_transaction_history
from pft_portfolio.exporters.ethereum import export_ethereum_snapshot, export_ethereum_transaction_history
from pft_portfolio.exporters.solana import export_solana_snapshot, export_solana_transaction_history


HYPERLIQUID_TOP_VAULT = "0xd6e56265890b76413d1d527eb9b75e334c0c5b42"
BTC_GENESIS_ADDRESS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
ETH_FOUNDATION_ADDRESS = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"
WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"


@pytest.mark.live
def test_live_ccxt_hyperliquid_exports_csv_snapshot_and_transactions(tmp_path: Path) -> None:
    snapshot_csv = tmp_path / "hyperliquid_snapshot.csv"
    transactions_csv = tmp_path / "hyperliquid_transactions.csv"

    export_ccxt_portfolio_snapshot(
        "hyperliquid",
        snapshot_csv,
        account_ref=f"hyperliquid:{HYPERLIQUID_TOP_VAULT}",
        params={"user": HYPERLIQUID_TOP_VAULT},
        fetch_balances=False,
    )
    export_ccxt_transaction_history(
        "hyperliquid",
        transactions_csv,
        account_ref=f"hyperliquid:{HYPERLIQUID_TOP_VAULT}",
        params={"user": HYPERLIQUID_TOP_VAULT},
        limit=5,
    )

    snapshot = ingest_portfolio_snapshot_csv(snapshot_csv)
    transactions = ingest_transaction_history_csv(transactions_csv)

    assert len(snapshot["positions"]) > 0
    assert any(record["instrument_type"] == "perp" for record in snapshot["positions"])
    assert all(record["input_type"] == "portfolio_snapshot" for record in snapshot["positions"])
    assert len(transactions["transactions"]) >= 1
    assert all(record["input_type"] == "transaction_history" for record in transactions["transactions"])


@pytest.mark.live
def test_live_bitcoin_address_exports_snapshot_and_transactions(tmp_path: Path) -> None:
    snapshot_csv = tmp_path / "btc_snapshot.csv"
    transactions_csv = tmp_path / "btc_transactions.csv"

    export_bitcoin_snapshot(BTC_GENESIS_ADDRESS, snapshot_csv)
    export_bitcoin_transaction_history(BTC_GENESIS_ADDRESS, transactions_csv, limit=2)

    snapshot = ingest_portfolio_snapshot_csv(snapshot_csv)
    transactions = ingest_transaction_history_csv(transactions_csv)

    assert snapshot["positions"][0]["symbol"] == "BTC"
    assert snapshot["positions"][0]["amount"] is not None
    assert len(transactions["transactions"]) == 2
    assert {record["symbol"] for record in transactions["transactions"]} == {"BTC"}


@pytest.mark.live
def test_live_ethereum_address_exports_snapshot_and_transactions(tmp_path: Path) -> None:
    snapshot_csv = tmp_path / "eth_snapshot.csv"
    transactions_csv = tmp_path / "eth_transactions.csv"

    export_ethereum_snapshot(ETH_FOUNDATION_ADDRESS, snapshot_csv)
    export_ethereum_transaction_history(ETH_FOUNDATION_ADDRESS, transactions_csv, limit=2)

    snapshot = ingest_portfolio_snapshot_csv(snapshot_csv)
    transactions = ingest_transaction_history_csv(transactions_csv)

    assert snapshot["positions"][0]["symbol"] == "ETH"
    assert snapshot["positions"][0]["amount"] is not None
    assert len(transactions["transactions"]) == 2
    assert {record["symbol"] for record in transactions["transactions"]} == {"ETH"}


@pytest.mark.live
def test_live_solana_address_exports_snapshot_and_transactions(tmp_path: Path) -> None:
    snapshot_csv = tmp_path / "sol_snapshot.csv"
    transactions_csv = tmp_path / "sol_transactions.csv"

    export_solana_snapshot(WRAPPED_SOL_MINT, snapshot_csv)
    export_solana_transaction_history(WRAPPED_SOL_MINT, transactions_csv, limit=1)

    snapshot = ingest_portfolio_snapshot_csv(snapshot_csv)
    transactions = ingest_transaction_history_csv(transactions_csv)
    assert snapshot["positions"][0]["symbol"] == "SOL"
    assert snapshot["positions"][0]["amount"] is not None
    assert len(transactions["transactions"]) == 1
    assert transactions["transactions"][0]["symbol"] == "SOL"
