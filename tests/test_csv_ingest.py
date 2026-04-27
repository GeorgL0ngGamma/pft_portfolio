from __future__ import annotations

from pathlib import Path

from pft_portfolio.canonical import canonical_json
from pft_portfolio.csv_ingest import ingest_portfolio_snapshot_csv, ingest_transaction_history_csv


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def test_cmc_portfolio_snapshot_ingests_to_cmc_like_records() -> None:
    document = ingest_portfolio_snapshot_csv(
        FIXTURES / "test_portfolio_with_portfolio_overview.csv",
        user_id="demo",
        account_ref="manual:cmc",
    )

    overview = document["overview"]
    positions = document["positions"]

    assert document["input_type"] == "portfolio_snapshot"
    assert overview["as_of"] == "2026-04-22T10:01:45Z"
    assert overview["currency"] == "USD"
    assert overview["total_value"] == "78023.63"
    assert overview["all_time_profit_pct"] == "3.2059"
    assert len(positions) == 1

    position = positions[0]
    assert position["asset_name"] == "Bitcoin"
    assert position["symbol"] == "BTC"
    assert position["instrument_type"] == "spot"
    assert position["price"] == "78023.63"
    assert position["holdings_value"] == "78023.63"
    assert position["amount"] == "1.0000"
    assert position["avg_buy_price"] == "75600.00"
    assert position["profit_loss_value"] == "2423.63"
    assert position["profit_loss_pct"] == "3.2059"
    assert position["source_csv"] == "test_portfolio_with_portfolio_overview.csv"
    assert position["source_row"] == 11
    assert "raw_row" in position


def test_transaction_history_ingests_without_cashflow_specific_columns() -> None:
    document = ingest_transaction_history_csv(FIXTURES / "transaction_history_2026-04-22.csv")
    transactions = document["transactions"]

    assert document["input_type"] == "transaction_history"
    assert [record["activity_type"] for record in transactions] == ["deposit", "buy", "fee", "snapshot_update"]
    assert transactions[1]["asset_name"] == "Bitcoin"
    assert transactions[1]["price"] == "75600.00"
    assert transactions[3]["profit_loss_value"] == "2423.63"
    assert transactions[3]["holdings_after"] == "1.0000"

    for record in transactions:
        assert "cashflow" not in record
        assert "fee" not in record
        assert "funding" not in record
        assert "transfer" not in record
        assert record["source_csv"] == "transaction_history_2026-04-22.csv"
        assert "raw_row" in record


def test_normalized_output_is_deterministic() -> None:
    first = ingest_portfolio_snapshot_csv(FIXTURES / "test_portfolio_with_portfolio_overview.csv")
    second = ingest_portfolio_snapshot_csv(FIXTURES / "test_portfolio_with_portfolio_overview.csv")

    assert canonical_json(first) == canonical_json(second)
    assert first["positions"][0]["id"] == second["positions"][0]["id"]
