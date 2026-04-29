"""Postgres-backed storage for TaskNode portfolio context."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from .csv_ingest import ingest_portfolio_snapshot_csv, ingest_transaction_history_csv


POSTGRES_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    pftl_wallet_address TEXT NOT NULL UNIQUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS accounts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_ref TEXT NOT NULL,
    asset_class TEXT,
    chain TEXT,
    address TEXT,
    venue TEXT,
    protocol TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, account_ref)
);

CREATE TABLE IF NOT EXISTS ingestion_sources (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_uri TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    input_type TEXT NOT NULL,
    content_sha256 TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, source_uri, input_type)
);

CREATE TABLE IF NOT EXISTS assets (
    id BIGSERIAL PRIMARY KEY,
    asset_key TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    asset_name TEXT,
    asset_class TEXT NOT NULL DEFAULT 'crypto',
    chain TEXT,
    contract_address TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolio_views (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    as_of TIMESTAMPTZ NOT NULL,
    currency TEXT NOT NULL,
    total_value NUMERIC,
    total_value_change_24h NUMERIC,
    total_value_change_24h_pct NUMERIC,
    all_time_profit_value NUMERIC,
    all_time_profit_pct NUMERIC,
    raw_overview JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_id BIGINT REFERENCES ingestion_sources(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, account_id, as_of, currency)
);

CREATE TABLE IF NOT EXISTS position_snapshots (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    as_of TIMESTAMPTZ NOT NULL,
    currency TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    amount NUMERIC,
    price NUMERIC,
    change_1h_pct NUMERIC,
    change_24h_pct NUMERIC,
    change_7d_pct NUMERIC,
    holdings_value NUMERIC,
    avg_buy_price NUMERIC,
    profit_loss_value NUMERIC,
    profit_loss_pct NUMERIC,
    asset_class TEXT,
    chain TEXT,
    address TEXT,
    venue TEXT,
    protocol TEXT,
    raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_id BIGINT REFERENCES ingestion_sources(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, account_id, asset_id, as_of, instrument_type)
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    timestamp TIMESTAMPTZ NOT NULL,
    activity_type TEXT NOT NULL,
    amount NUMERIC,
    price NUMERIC,
    value NUMERIC,
    currency TEXT NOT NULL,
    profit_loss_value NUMERIC,
    profit_loss_pct NUMERIC,
    holdings_after NUMERIC,
    asset_class TEXT,
    chain TEXT,
    address TEXT,
    tx_hash TEXT,
    block_number BIGINT,
    log_index BIGINT,
    external_id TEXT,
    venue TEXT,
    protocol TEXT,
    counterparty TEXT,
    fee_amount NUMERIC,
    fee_symbol TEXT,
    raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_id BIGINT REFERENCES ingestion_sources(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP INDEX IF EXISTS transactions_chain_tx_idx;

CREATE UNIQUE INDEX IF NOT EXISTS transactions_chain_event_idx
    ON transactions (
        user_id, chain, tx_hash, COALESCE(log_index, -1),
        activity_type, asset_id, COALESCE(external_id, '')
    )
    WHERE chain IS NOT NULL AND tx_hash IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS transactions_external_idx
    ON transactions (user_id, venue, external_id)
    WHERE venue IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS position_snapshots_lookup_idx
    ON position_snapshots (user_id, account_id, as_of DESC);

CREATE INDEX IF NOT EXISTS transactions_lookup_idx
    ON transactions (user_id, account_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS analysis_documents (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    privacy_tier TEXT NOT NULL DEFAULT 'derived',
    document_text TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_table, source_record_id, privacy_tier)
);

CREATE TABLE IF NOT EXISTS analysis_embeddings (
    document_id TEXT NOT NULL REFERENCES analysis_documents(id) ON DELETE CASCADE,
    embedding vector(1536) NOT NULL,
    model TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, model)
);

CREATE TABLE IF NOT EXISTS signal_events (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id BIGINT REFERENCES accounts(id) ON DELETE SET NULL,
    event_time TIMESTAMPTZ NOT NULL,
    signal_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    strength NUMERIC,
    confidence NUMERIC,
    privacy_tier TEXT NOT NULL DEFAULT 'derived',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS signal_events_lookup_idx
    ON signal_events (user_id, event_time DESC, signal_type);

CREATE INDEX IF NOT EXISTS signal_events_features_idx
    ON signal_events USING gin (features);

INSERT INTO schema_migrations (version)
VALUES ('001_postgres_pgvector_portfolio')
ON CONFLICT (version) DO NOTHING;

INSERT INTO schema_migrations (version)
VALUES ('002_transaction_chain_event_index')
ON CONFLICT (version) DO NOTHING;
"""


class PostgresPortfolioStore:
    """Idempotent Postgres persistence for normalized CSV documents."""

    def __init__(self, connection: Any):
        self.connection = connection

    @classmethod
    def from_dsn(cls, dsn: str) -> "PostgresPortfolioStore":
        try:
            import psycopg  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Install the postgres extra: pip install -e '.[postgres]'") from exc
        return cls(psycopg.connect(dsn))

    def apply_migrations(self) -> None:
        self._execute(POSTGRES_SCHEMA_SQL)
        self._commit()

    def add_snapshot_csv(
        self,
        path: str | Path,
        *,
        pftl_wallet_address: str | None = None,
        user_id: str = "demo",
        account_ref: str = "manual:portfolio",
        source_uri: str | None = None,
    ) -> int:
        document = ingest_portfolio_snapshot_csv(path, user_id=user_id, account_ref=account_ref)
        source = self._source_info(path, source_uri, "portfolio_snapshot")
        return self.add_snapshot_document(document, pftl_wallet_address=pftl_wallet_address, source=source)

    def add_transaction_csv(
        self,
        path: str | Path,
        *,
        pftl_wallet_address: str | None = None,
        user_id: str = "demo",
        account_ref: str = "manual:portfolio",
        source_uri: str | None = None,
    ) -> int:
        document = ingest_transaction_history_csv(path, user_id=user_id, account_ref=account_ref)
        source = self._source_info(path, source_uri, "transaction_history")
        return self.add_transaction_document(document, pftl_wallet_address=pftl_wallet_address, source=source)

    def add_snapshot_document(
        self,
        document: dict[str, Any],
        *,
        pftl_wallet_address: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> int:
        records = _records_from_snapshot_document(document)
        count = 0
        for record in records:
            context = self._context(record, pftl_wallet_address, source)
            if record.get("asset_name"):
                self._upsert_position(record, context)
            else:
                self._upsert_portfolio_view(record, context)
            count += 1
        self._commit()
        return count

    def add_transaction_document(
        self,
        document: dict[str, Any],
        *,
        pftl_wallet_address: str | None = None,
        source: dict[str, Any] | None = None,
    ) -> int:
        count = 0
        for record in document.get("transactions") or []:
            self._upsert_transaction(record, self._context(record, pftl_wallet_address, source))
            count += 1
        self._commit()
        return count

    def _context(self, record: dict[str, Any], pftl_wallet_address: str | None, source: dict[str, Any] | None) -> dict[str, int | None]:
        db_user_id = self._upsert_user(pftl_wallet_address or record.get("user_id") or "demo", record.get("user_id"))
        source_id = self._upsert_source(db_user_id, source) if source else None
        account_id = self._upsert_account(db_user_id, record)
        asset_id = self._upsert_asset(record) if record.get("asset_name") or record.get("symbol") else None
        return {"user_id": db_user_id, "source_id": source_id, "account_id": account_id, "asset_id": asset_id}

    def _upsert_user(self, pftl_wallet_address: str, csv_user_id: str | None) -> int:
        row = self._fetchone(
            """
            INSERT INTO users (pftl_wallet_address, metadata)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (pftl_wallet_address) DO UPDATE SET
                metadata = users.metadata || EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
            """,
            (pftl_wallet_address, _json({"csv_user_id": csv_user_id} if csv_user_id else {})),
        )
        return int(row[0])

    def _upsert_account(self, user_id: int, record: dict[str, Any]) -> int:
        row = self._fetchone(
            """
            INSERT INTO accounts (user_id, account_ref, asset_class, chain, address, venue, protocol, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (user_id, account_ref) DO UPDATE SET
                asset_class = COALESCE(EXCLUDED.asset_class, accounts.asset_class),
                chain = COALESCE(EXCLUDED.chain, accounts.chain),
                address = COALESCE(EXCLUDED.address, accounts.address),
                venue = COALESCE(EXCLUDED.venue, accounts.venue),
                protocol = COALESCE(EXCLUDED.protocol, accounts.protocol),
                metadata = accounts.metadata || EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
            """,
            (
                user_id,
                record.get("account_ref") or "manual:portfolio",
                record.get("asset_class"),
                record.get("chain"),
                record.get("address"),
                record.get("venue"),
                record.get("protocol"),
                _json({"csv_user_id": record.get("user_id")}),
            ),
        )
        return int(row[0])

    def _upsert_source(self, user_id: int, source: dict[str, Any]) -> int:
        row = self._fetchone(
            """
            INSERT INTO ingestion_sources (user_id, source_uri, source_kind, input_type, content_sha256, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (user_id, source_uri, input_type) DO UPDATE SET
                source_kind = EXCLUDED.source_kind,
                content_sha256 = EXCLUDED.content_sha256,
                metadata = ingestion_sources.metadata || EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
            """,
            (
                user_id,
                source["source_uri"],
                source["source_kind"],
                source["input_type"],
                source.get("content_sha256"),
                _json(source.get("metadata") or {}),
            ),
        )
        return int(row[0])

    def _upsert_asset(self, record: dict[str, Any]) -> int:
        symbol = record.get("symbol") or record.get("asset_name") or "UNKNOWN"
        asset_class = record.get("asset_class") or "crypto"
        chain = record.get("chain")
        contract_address = record.get("contract_address")
        row = self._fetchone(
            """
            INSERT INTO assets (asset_key, symbol, asset_name, asset_class, chain, contract_address, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (asset_key) DO UPDATE SET
                symbol = EXCLUDED.symbol,
                asset_name = COALESCE(EXCLUDED.asset_name, assets.asset_name),
                asset_class = EXCLUDED.asset_class,
                chain = COALESCE(EXCLUDED.chain, assets.chain),
                contract_address = COALESCE(EXCLUDED.contract_address, assets.contract_address),
                metadata = assets.metadata || EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
            """,
            (_asset_key(asset_class, chain, symbol, contract_address), symbol, record.get("asset_name"), asset_class, chain, contract_address, _json({})),
        )
        return int(row[0])

    def _upsert_portfolio_view(self, record: dict[str, Any], context: dict[str, int | None]) -> None:
        self._execute(
            """
            INSERT INTO portfolio_views (
                id, user_id, account_id, as_of, currency, total_value, total_value_change_24h,
                total_value_change_24h_pct, all_time_profit_value, all_time_profit_pct, raw_overview, source_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (id) DO UPDATE SET
                total_value = EXCLUDED.total_value,
                total_value_change_24h = EXCLUDED.total_value_change_24h,
                total_value_change_24h_pct = EXCLUDED.total_value_change_24h_pct,
                all_time_profit_value = EXCLUDED.all_time_profit_value,
                all_time_profit_pct = EXCLUDED.all_time_profit_pct,
                raw_overview = EXCLUDED.raw_overview,
                source_id = EXCLUDED.source_id,
                updated_at = now()
            """,
            (
                record["id"],
                context["user_id"],
                context["account_id"],
                record.get("as_of"),
                record.get("currency") or "USD",
                _numeric(record.get("total_value")),
                _numeric(record.get("total_value_change_24h")),
                _numeric(record.get("total_value_change_24h_pct")),
                _numeric(record.get("all_time_profit_value")),
                _numeric(record.get("all_time_profit_pct")),
                _json(record.get("raw_overview") or {}),
                context["source_id"],
            ),
        )

    def _upsert_position(self, record: dict[str, Any], context: dict[str, int | None]) -> None:
        self._execute(
            """
            INSERT INTO position_snapshots (
                id, user_id, account_id, asset_id, as_of, currency, instrument_type, amount, price,
                change_1h_pct, change_24h_pct, change_7d_pct, holdings_value, avg_buy_price,
                profit_loss_value, profit_loss_pct, asset_class, chain, address, venue, protocol, raw_row, source_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (id) DO UPDATE SET
                amount = EXCLUDED.amount,
                price = EXCLUDED.price,
                change_1h_pct = EXCLUDED.change_1h_pct,
                change_24h_pct = EXCLUDED.change_24h_pct,
                change_7d_pct = EXCLUDED.change_7d_pct,
                holdings_value = EXCLUDED.holdings_value,
                avg_buy_price = EXCLUDED.avg_buy_price,
                profit_loss_value = EXCLUDED.profit_loss_value,
                profit_loss_pct = EXCLUDED.profit_loss_pct,
                asset_class = EXCLUDED.asset_class,
                chain = EXCLUDED.chain,
                address = EXCLUDED.address,
                venue = EXCLUDED.venue,
                protocol = EXCLUDED.protocol,
                raw_row = EXCLUDED.raw_row,
                source_id = EXCLUDED.source_id,
                updated_at = now()
            """,
            (
                record["id"],
                context["user_id"],
                context["account_id"],
                context["asset_id"],
                record.get("as_of"),
                record.get("currency") or "USD",
                record.get("instrument_type") or "spot",
                _numeric(record.get("amount")),
                _numeric(record.get("price")),
                _numeric(record.get("change_1h_pct")),
                _numeric(record.get("change_24h_pct")),
                _numeric(record.get("change_7d_pct")),
                _numeric(record.get("holdings_value")),
                _numeric(record.get("avg_buy_price")),
                _numeric(record.get("profit_loss_value")),
                _numeric(record.get("profit_loss_pct")),
                record.get("asset_class"),
                record.get("chain"),
                record.get("address"),
                record.get("venue"),
                record.get("protocol"),
                _json(record.get("raw_row") or {}),
                context["source_id"],
            ),
        )

    def _upsert_transaction(self, record: dict[str, Any], context: dict[str, int | None]) -> None:
        self._execute(
            """
            INSERT INTO transactions (
                id, user_id, account_id, asset_id, timestamp, activity_type, amount, price, value,
                currency, profit_loss_value, profit_loss_pct, holdings_after, asset_class, chain,
                address, tx_hash, block_number, log_index, external_id, venue, protocol, counterparty,
                fee_amount, fee_symbol, raw_row, source_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (id) DO UPDATE SET
                amount = EXCLUDED.amount,
                price = EXCLUDED.price,
                value = EXCLUDED.value,
                currency = EXCLUDED.currency,
                profit_loss_value = EXCLUDED.profit_loss_value,
                profit_loss_pct = EXCLUDED.profit_loss_pct,
                holdings_after = EXCLUDED.holdings_after,
                asset_class = EXCLUDED.asset_class,
                chain = EXCLUDED.chain,
                address = EXCLUDED.address,
                tx_hash = EXCLUDED.tx_hash,
                block_number = EXCLUDED.block_number,
                log_index = EXCLUDED.log_index,
                external_id = EXCLUDED.external_id,
                venue = EXCLUDED.venue,
                protocol = EXCLUDED.protocol,
                counterparty = EXCLUDED.counterparty,
                fee_amount = EXCLUDED.fee_amount,
                fee_symbol = EXCLUDED.fee_symbol,
                raw_row = EXCLUDED.raw_row,
                source_id = EXCLUDED.source_id,
                updated_at = now()
            """,
            (
                record["id"],
                context["user_id"],
                context["account_id"],
                context["asset_id"],
                record.get("timestamp"),
                record.get("activity_type") or "trade",
                _numeric(record.get("amount")),
                _numeric(record.get("price")),
                _numeric(record.get("value")),
                record.get("currency") or "USD",
                _numeric(record.get("profit_loss_value")),
                _numeric(record.get("profit_loss_pct")),
                _numeric(record.get("holdings_after")),
                record.get("asset_class"),
                record.get("chain"),
                record.get("address"),
                record.get("tx_hash"),
                _integer(record.get("block_number")),
                _integer(record.get("log_index")),
                record.get("external_id"),
                record.get("venue"),
                record.get("protocol"),
                record.get("counterparty"),
                _numeric(record.get("fee_amount")),
                record.get("fee_symbol"),
                _json(record.get("raw_row") or {}),
                context["source_id"],
            ),
        )

    def _execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        cursor = self.connection.cursor()
        cursor.execute(sql, tuple(params) if params is not None else None)
        return cursor

    def _fetchone(self, sql: str, params: Iterable[Any]) -> tuple[Any, ...]:
        cursor = self._execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Postgres statement did not return a row")
        return tuple(row)

    def _commit(self) -> None:
        commit = getattr(self.connection, "commit", None)
        if commit:
            commit()

    def _source_info(self, path: str | Path, source_uri: str | None, input_type: str) -> dict[str, Any]:
        target = Path(path)
        return {
            "source_uri": source_uri or str(target),
            "source_kind": "csv",
            "input_type": input_type,
            "content_sha256": _file_sha256(target),
            "metadata": {"filename": target.name},
        }


def _records_from_snapshot_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    overview = document.get("overview")
    if overview:
        records.append(overview)
    records.extend(document.get("positions") or [])
    return records


def _asset_key(asset_class: str, chain: str | None, symbol: str, contract_address: str | None) -> str:
    return ":".join((asset_class.lower(), (chain or "").lower(), symbol.upper(), (contract_address or "").lower()))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _numeric(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return text


def _integer(value: Any) -> int | None:
    number = _numeric(value)
    if number is None:
        return None
    return int(Decimal(number))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
