from __future__ import annotations

from pathlib import Path
from typing import Any

from pft_portfolio.canonical import semantic_id
from pft_portfolio.csv_ingest import ingest_transaction_history_csv
from pft_portfolio.postgres_store import POSTGRES_SCHEMA_SQL, PostgresPortfolioStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def test_postgres_schema_has_pgvector_and_tasknode_tables() -> None:
    sql = POSTGRES_SCHEMA_SQL.lower()

    assert "create extension if not exists vector" in sql
    for table in (
        "users",
        "accounts",
        "ingestion_sources",
        "assets",
        "position_snapshots",
        "transactions",
        "portfolio_views",
        "analysis_documents",
        "analysis_embeddings",
        "signal_events",
    ):
        assert f"create table if not exists {table}" in sql
    assert "embedding vector(1536)" in sql
    assert "privacy_tier" in sql
    assert "drop index if exists transactions_chain_tx_idx" in sql
    assert "transactions_chain_event_idx" in sql
    assert "002_transaction_chain_event_index" in sql


def test_semantic_ids_ignore_csv_provenance() -> None:
    document = ingest_transaction_history_csv(FIXTURES / "transaction_history_2026-04-22.csv")
    record = document["transactions"][1]
    duplicate = {
        **record,
        "source_csv": "different-file.csv",
        "source_row": 999,
        "raw_row": {"changed": "provenance only"},
    }

    assert semantic_id("txn", record) == semantic_id("txn", duplicate)
    assert record["id"] == semantic_id("txn", duplicate)


def test_chain_transaction_semantic_ids_distinguish_rows_without_log_index() -> None:
    base = {
        "input_type": "transaction_history",
        "user_id": "demo",
        "account_ref": "eth:0xabc",
        "timestamp": "2026-04-22T10:00:00Z",
        "chain": "ETH",
        "tx_hash": "0xtx",
        "instrument_type": "spot",
    }
    transfer = {**base, "activity_type": "deposit", "symbol": "ETH", "amount": "1", "value": "3000"}
    fee = {**base, "activity_type": "fee", "symbol": "ETH", "amount": "0.01", "fee_amount": "0.01", "fee_symbol": "ETH"}

    assert semantic_id("txn", transfer) != semantic_id("txn", fee)


def test_transaction_ingest_preserves_chain_and_exchange_provenance(tmp_path: Path) -> None:
    csv_path = tmp_path / "eth_trade.csv"
    csv_path.write_text(
        "timestamp,activity_type,asset_name,symbol,amount,price,value,currency,chain,address,contract_address,tx_hash,block_number,log_index,venue,external_id,fee_amount,fee_symbol\n"
        "2026-04-22T10:00:00Z,buy,Ethereum,ETH,1,3000,3000,USD,ethereum,0xabc,0xtoken,0xtx,123,4,coinbase,trade-1,2,USD\n",
        encoding="utf-8",
    )

    record = ingest_transaction_history_csv(csv_path)["transactions"][0]

    assert record["asset_class"] == "crypto"
    assert record["chain"] == "ETH"
    assert record["address"] == "0xabc"
    assert record["contract_address"] == "0xtoken"
    assert record["tx_hash"] == "0xtx"
    assert record["block_number"] == "123"
    assert record["log_index"] == "4"
    assert record["venue"] == "coinbase"
    assert record["external_id"] == "trade-1"
    assert record["fee_amount"] == "2"
    assert record["fee_symbol"] == "USD"


def test_postgres_store_upserts_with_fake_connection() -> None:
    connection = FakeConnection()
    store = PostgresPortfolioStore(connection)

    snapshot_count = store.add_snapshot_csv(
        FIXTURES / "test_portfolio_with_portfolio_overview.csv",
        pftl_wallet_address="rPFTLWallet",
        user_id="demo",
        account_ref="manual:cmc",
    )
    transaction_count = store.add_transaction_csv(
        FIXTURES / "transaction_history_2026-04-22.csv",
        pftl_wallet_address="rPFTLWallet",
    )

    executed_sql = "\n".join(sql for sql, _params in connection.executions)

    assert snapshot_count == 2
    assert transaction_count == 4
    assert connection.commits == 2
    assert "INSERT INTO portfolio_views" in executed_sql
    assert "INSERT INTO position_snapshots" in executed_sql
    assert "INSERT INTO transactions" in executed_sql
    assert "ON CONFLICT (id) DO UPDATE" in executed_sql
    assert any(params and params[0] == "rPFTLWallet" for _sql, params in connection.executions)


def test_postgres_store_applies_migration_sql() -> None:
    connection = FakeConnection()

    PostgresPortfolioStore(connection).apply_migrations()

    assert connection.executions == [(POSTGRES_SCHEMA_SQL, None)]
    assert connection.commits == 1


class FakeConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[Any, ...] | None]] = []
        self.commits = 0

    def cursor(self) -> "FakeCursor":
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.row: tuple[int] | None = None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.connection.executions.append((sql, params))
        normalized = " ".join(sql.lower().split())
        self.row = None
        if "insert into users" in normalized:
            self.row = (1,)
        elif "insert into accounts" in normalized:
            self.row = (10,)
        elif "insert into ingestion_sources" in normalized:
            self.row = (20,)
        elif "insert into assets" in normalized:
            self.row = (30,)

    def fetchone(self) -> tuple[int] | None:
        return self.row
