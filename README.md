# pft_portfolio

CSV-first portfolio-history ingestion scaffold for Post Fiat reviewers and TaskNode portfolio context.

## Direction

The package accepts two dated CSV inputs:

- `portfolio_snapshot`: point-in-time holdings and valuation, close to the CoinMarketCap portfolio export shape.
- `transaction_history`: dated user activity rows using the same value-oriented vocabulary.

Exchange and chain helpers are exporters, not separate ingestion models:

```text
exchange account via CCXT -> dated CSV -> common storage
chain address via public API/RPC -> dated CSV -> common storage
manual CMC-style export -> dated CSV -> common storage
```

This deliberately keeps CSV as the boundary between data pulling and portfolio-history normalization.

The production storage target is Postgres with `pgvector`. JSONL remains available as a reviewer-readable local/debug backend.

## Primitive Vocabulary

`input_type` is intentionally small:

- `portfolio_snapshot`
- `transaction_history`

`instrument_type` is supported but peripheral:

- `spot`
- `perp`
- `future`
- `option`
- `yield`

There is no `source_type`, `state_model`, or dedicated `record_type` in this v0 scaffold. CSV provenance is carried by `source_csv`, `source_row`, and preserved raw CSV row content after ingestion. Chain, exchange, and protocol provenance are explicit optional fields.

## CSV Fields

Portfolio snapshots normalize around CMC-like fields:

```text
user_id, account_ref, as_of, currency, asset_name, symbol, instrument_type,
price, change_1h_pct, change_24h_pct, change_7d_pct, holdings_value,
amount, avg_buy_price, profit_loss_value, profit_loss_pct
```

Transaction histories use the same valuation vocabulary plus activity labels:

```text
user_id, account_ref, timestamp, activity_type, asset_name, symbol,
instrument_type, amount, price, value, currency, profit_loss_value,
profit_loss_pct, holdings_after
```

Both CSV types can also include these optional production provenance fields:

```text
asset_class, chain, address, tx_hash, block_number, log_index,
external_id, venue, protocol, counterparty, fee_amount, fee_symbol
```

Fees, funding, transfers, deposits, withdrawals, buys, sells, rewards, staking, and similar events are represented as `activity_type` values. `fee_amount` and `fee_symbol` are optional provenance/valuation fields for events where fee data is already available.

## Fixtures

- `fixtures/test_portfolio_with_portfolio_overview.csv`: minimal CMC-style dated portfolio snapshot.
- `fixtures/transaction_history_2026-04-22.csv`: dated transaction history using the same value-oriented vocabulary.

The original shared CMC example remains at the repository root for reference; the fixture copy under `fixtures/` is used by tests.

## Storage

`PortfolioStore` writes normalized records as JSONL so reviewers can inspect the exact records without a database server:

```bash
pft-portfolio store-add portfolio-history.jsonl snapshot fixtures/test_portfolio_with_portfolio_overview.csv
pft-portfolio store-add portfolio-history.jsonl transactions fixtures/transaction_history_2026-04-22.csv
pft-portfolio portfolio-at portfolio-history.jsonl demo 2026-04-22T12:00:00Z
```

The point-in-time helper returns the latest snapshot available before the requested timestamp plus transaction history up to that timestamp. This is a storage/readback utility, not an LLM retrieval layer.

`PostgresPortfolioStore` is the production path. It applies a schema with these tables:

```text
users, accounts, ingestion_sources, assets, portfolio_views,
position_snapshots, transactions, analysis_documents,
analysis_embeddings, signal_events
```

`users.pftl_wallet_address` is the TaskNode identity boundary. CSV `user_id` is preserved as source metadata, while `--pftl-wallet-address` controls the Postgres user identity.

Postgres records are upserted idempotently with semantic IDs. Snapshot position IDs are based on user/account/time/asset identity, not CSV filename or row number. Transaction IDs prefer chain transaction identity (`chain`, `tx_hash`, `log_index`) or exchange identity (`venue`, `external_id`) before falling back to normalized event fields.

Apply migrations and ingest into Postgres:

```bash
pft-portfolio postgres-migrate --dsn "$DATABASE_URL"
pft-portfolio postgres-add snapshot fixtures/test_portfolio_with_portfolio_overview.csv --pftl-wallet-address r...
pft-portfolio postgres-add transactions fixtures/transaction_history_2026-04-22.csv --pftl-wallet-address r...
```

The migration enables `pgvector` and creates `analysis_documents` plus `analysis_embeddings` for derived context chunks. Trading or research agents should consume derived `signal_events` and privacy-scoped analysis documents, not unrestricted raw CSV rows by default.

## Live Prototype Proof

The repository includes an executable live proof that pulls public data, writes CSVs, normalizes them, and upserts them into Postgres with `pgvector` enabled:

```bash
PYTHONPATH=src DATABASE_URL="postgresql://postgres:postgres@localhost:5432/pft_portfolio" \
  python3 examples/live_prototype.py --output-dir prototype-output
```

The proof sources are intentionally public and require no private keys:

```text
BTC address: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
ETH address: 0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe
SOL address: So11111111111111111111111111111111111111112
Hyperliquid vault: 0xd6e56265890b76413d1d527eb9b75e334c0c5b42
```

The Hyperliquid address is the public `[ Systemic Strategies ] HyperGrowth` vault. It is a normal user vault, not HLP or Liquidator, and is fetched through the same CCXT venue path used by other exchange-like accounts.

The live proof writes these files under `prototype-output/`:

```text
btc_snapshot.csv, btc_transactions.csv,
eth_snapshot.csv, eth_transactions.csv,
sol_snapshot.csv, sol_transactions.csv,
hyperliquid_vault_snapshot.csv, hyperliquid_vault_transactions.csv,
summary.json
```

`summary.json` includes per-source row counts and Postgres table counts for `users`, `accounts`, `ingestion_sources`, `assets`, `portfolio_views`, `position_snapshots`, and `transactions`.

GitHub Actions runs the same proof in `.github/workflows/live-prototype.yml` with a minimal `pgvector/pgvector:pg16` service container and uploads `prototype-output/` as the `live-prototype-output` artifact.

For local Postgres testing, one minimal database option is:

```bash
docker run --rm --name pft-portfolio-pgvector \
  -e POSTGRES_DB=pft_portfolio \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

## Exporters

Exporters produce dated CSV files that the ingestion path can read:

- `exporters.ccxt_exchange`: generic CCXT exchange exporter for balances, positions, and trades where the exchange supports them.
- `exporters.bitcoin`: BTC address snapshot and transaction CSV using an Esplora-compatible public API.
- `exporters.ethereum`: ETH snapshot via public JSON-RPC and transaction history via Blockscout.
- `exporters.solana`: SOL snapshot and transaction history via public Solana JSON-RPC.

Hyperliquid is covered through the generic CCXT exporter. It is useful as a crossover case because a public Hyperliquid account behaves like both an exchange account and an address-like chain context.

## Quick Start

```bash
python3 -m pytest
```

Normalize a fixture:

```bash
PYTHONPATH=src python3 -m pft_portfolio.cli normalize snapshot fixtures/test_portfolio_with_portfolio_overview.csv
PYTHONPATH=src python3 -m pft_portfolio.cli normalize transactions fixtures/transaction_history_2026-04-22.csv
```

Use the package directly:

```python
from pft_portfolio.storage import PortfolioStore
from pft_portfolio.postgres_store import PostgresPortfolioStore

store = PortfolioStore("portfolio-history.jsonl")
store.add_snapshot_csv("fixtures/test_portfolio_with_portfolio_overview.csv")
store.add_transaction_csv("fixtures/transaction_history_2026-04-22.csv")
view = store.portfolio_at("demo", "2026-04-22T12:00:00Z")

pg_store = PostgresPortfolioStore.from_dsn("postgresql://...")
pg_store.apply_migrations()
pg_store.add_transaction_csv("fixtures/transaction_history_2026-04-22.csv", pftl_wallet_address="r...")
```

## Live Tests

The test suite includes live tests, not fake exchange or chain adapters:

- CCXT Hyperliquid public vault snapshot and trades.
- BTC address snapshot and transactions.
- ETH address snapshot and transactions.
- SOL address snapshot and transactions.

These tests make public network calls and use structural assertions because balances and positions move. The GitHub Actions live prototype proof is a stronger end-to-end check because it also starts Postgres with `pgvector`, applies migrations, stores all four sources, and uploads the resulting CSV/JSON artifact.

## Out Of Scope

The v0 package does not implement:

- Embedding generation, RAG retrieval, or semantic search queries.
- Query modeling beyond a minimal `portfolio_at` readback helper.
- Strategy recommendations or portfolio scoring.
- A heavyweight schema registry.

The intended next layer can derive signal events and privacy-scoped analysis documents from normalized history, but this package stops at CSV export, CSV ingestion, JSONL review storage, and Postgres persistence.

## Open Questions

- How much derivative-specific detail should be preserved in CSV columns versus `raw_json`.
- Which chain/indexer providers should be official defaults for production transaction history.
- Whether CMC-style overview rows should remain a special parser or be converted into the standardized snapshot CSV before ingestion.
