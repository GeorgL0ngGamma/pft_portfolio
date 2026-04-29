# pft_portfolio

`pft_portfolio` is a CSV-boundary ingestion layer for Post Fiat portfolio history. It turns dated portfolio snapshots and transaction histories from manual exports, public chain APIs, and exchange adapters into normalized records that can be inspected locally or persisted to Postgres with `pgvector` enabled.

The repository is intentionally small. It owns export-to-CSV adapters, CSV normalization, semantic IDs, reviewer-readable JSONL storage, and the Postgres persistence schema. It does not own strategy recommendations, portfolio scoring, embedding generation, or retrieval behavior.

## Architecture

```text
manual export / public chain API / CCXT exchange
  -> dated standard CSV
  -> pft_portfolio.csv_ingest
  -> normalized portfolio_snapshot or transaction_history records
  -> JSONL reviewer store or Postgres persistence
```

CSV is the boundary between data collection and portfolio-history normalization. Exporters are adapters that write standard CSV files; they are not separate ingestion models. The same parser path handles manual CMC-style files, public BTC/ETH/SOL examples, and CCXT exchange-like sources such as Hyperliquid.

| Area | Files | Responsibility |
| --- | --- | --- |
| Data contract | `src/pft_portfolio/constants.py` | Input types, snapshot columns, transaction columns, provenance columns |
| Normalization | `src/pft_portfolio/csv_ingest.py` | CSV parsing, timestamp normalization, numeric cleanup, raw-row preservation |
| Semantic IDs | `src/pft_portfolio/canonical.py` | Deterministic IDs based on economic identity, not CSV row location |
| Local review storage | `src/pft_portfolio/storage.py` | JSONL records and point-in-time readback for deterministic inspection |
| Postgres storage | `src/pft_portfolio/postgres_store.py` | Schema, migrations, upserts, source tracking, `pgvector` tables |
| Exporters | `src/pft_portfolio/exporters/` | BTC, ETH, SOL, and generic CCXT CSV writers |
| CLI | `src/pft_portfolio/cli.py` | Normalize, JSONL store, point-in-time readback, Postgres ingest |
| Live proof | `examples/live_prototype.py` | Public-data CSV-to-Postgres proof run |

## Install

Python 3.10 or newer is required.

```bash
python3 -m pip install -e '.[test]'
```

Install all optional integrations when running the live prototype or Postgres path:

```bash
python3 -m pip install -e '.[test,postgres,exchange]'
```

Dependency extras are intentionally explicit:

| Extra | Adds | Used by |
| --- | --- | --- |
| `test` | `pytest`, `ccxt` | Deterministic tests and exporter mapper tests |
| `postgres` | `psycopg[binary]` | `PostgresPortfolioStore`, `postgres-*` CLI commands |
| `exchange` | `ccxt` | Generic exchange exporter and Hyperliquid proof source |

## Quick Start

Run deterministic tests. Live network tests are excluded by default.

```bash
python3 -m pytest
```

Normalize the checked-in fixture inputs:

```bash
pft-portfolio normalize snapshot fixtures/test_portfolio_with_portfolio_overview.csv
pft-portfolio normalize transactions fixtures/transaction_history_2026-04-22.csv
```

Use the local JSONL review store:

```bash
pft-portfolio store-add portfolio-history.jsonl snapshot fixtures/test_portfolio_with_portfolio_overview.csv
pft-portfolio store-add portfolio-history.jsonl transactions fixtures/transaction_history_2026-04-22.csv
pft-portfolio portfolio-at portfolio-history.jsonl demo 2026-04-22T12:00:00Z
```

If the package is not installed, prefix CLI examples with `PYTHONPATH=src python3 -m pft_portfolio.cli`.

## Data Contract

There are two first-class input types.

| Input type | Meaning |
| --- | --- |
| `portfolio_snapshot` | Point-in-time holdings, valuation, and optional aggregate overview |
| `transaction_history` | Dated economic events and valuation updates |

Snapshots and transactions are both part of portfolio history. A snapshot explains state at a time; a transaction row explains an event or value update at a time.

Standard portfolio snapshot CSV columns:

```text
user_id, account_ref, as_of, currency, asset_name, symbol, instrument_type,
price, change_1h_pct, change_24h_pct, change_7d_pct, holdings_value,
amount, avg_buy_price, profit_loss_value, profit_loss_pct
```

Standard transaction history CSV columns:

```text
user_id, account_ref, timestamp, activity_type, asset_name, symbol,
instrument_type, amount, price, value, currency, profit_loss_value,
profit_loss_pct, holdings_after
```

Optional provenance columns accepted by both CSV types:

```text
asset_class, chain, address, contract_address, tx_hash, block_number,
log_index, external_id, venue, protocol, counterparty, fee_amount, fee_symbol
```

Exporter-generated CSVs also include `raw_json` when useful. Ingested records always preserve source metadata as `source_csv`, `source_row`, and `raw_row`. CMC-style exports with an overview block are accepted directly; the overview becomes an aggregate portfolio record while asset rows become snapshot positions.

Supported `instrument_type` values are intentionally compact: `spot`, `perp`, `future`, `option`, and `yield`. Unknown or missing values normalize to `spot`.

## Identity And Idempotency

Normalized records receive deterministic semantic IDs before storage. IDs exclude `source_csv`, `source_row`, `raw_row`, and other row-location provenance so the same economic event can be re-imported from another file without becoming a new record.

Snapshot IDs use user, account, timestamp, asset, instrument, and source-context identity. Transaction IDs prefer venue identity (`venue`, `external_id`) when present, then chain identity (`chain`, `tx_hash`, `log_index`) when event-level chain data is present, then normalized event fields as a fallback.

Postgres upserts by semantic ID and records ingestion source hashes separately. The JSONL store is a deterministic reviewer/debug backend; it skips records whose IDs are already present and does not try to be a database replacement.

Postgres user identity is controlled by `users.pftl_wallet_address`. CSV `user_id` remains source metadata. The CLI exposes that boundary with `--pftl-wallet-address` on Postgres ingest commands.

## Storage

### Postgres

`PostgresPortfolioStore` is the production persistence path. It enables `pgvector` and applies a compact schema with migration tracking, source provenance, portfolio history, and derived-context tables.

```text
schema_migrations,
users, accounts, ingestion_sources, assets,
portfolio_views, position_snapshots, transactions,
analysis_documents, analysis_embeddings, signal_events
```

Apply migrations and ingest fixture CSVs:

```bash
pft-portfolio postgres-migrate --dsn "$DATABASE_URL"
pft-portfolio postgres-add snapshot fixtures/test_portfolio_with_portfolio_overview.csv --pftl-wallet-address r...
pft-portfolio postgres-add transactions fixtures/transaction_history_2026-04-22.csv --pftl-wallet-address r...
```

For local testing, start a minimal `pgvector` database:

```bash
docker run --rm --name pft-portfolio-pgvector \
  -e POSTGRES_DB=pft_portfolio \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

The schema includes `analysis_documents`, `analysis_embeddings`, and `signal_events` so downstream agents can consume privacy-scoped derived context. This repository only creates the tables; it does not generate embeddings, run retrieval, or emit strategy signals.

### JSONL

`PortfolioStore` writes normalized records to JSONL for local inspection and deterministic tests. The point-in-time helper returns the latest snapshot available before a requested timestamp plus transaction history up to that timestamp.

JSONL is useful for review because it exposes the exact normalized records without requiring Postgres. It is not the production query model.

## Exporters

Exporters write dated CSVs that the ingestion path can read.

| Exporter | Source | Notes |
| --- | --- | --- |
| `exporters.bitcoin` | BTC address | Snapshot and transactions through an Esplora-compatible API |
| `exporters.ethereum` | ETH address | Snapshot through public JSON-RPC, history through Blockscout |
| `exporters.solana` | SOL address | Snapshot and native balance deltas through public Solana JSON-RPC |
| `exporters.ccxt_exchange` | CCXT exchange account | Balances, positions, trades, and fees where the exchange supports them |

Hyperliquid is covered through the generic CCXT exporter. The live proof uses a public Hyperliquid vault as an exchange-like account with address-style provenance.

## Live Proof

The repository includes an executable proof that pulls public data, writes standard CSV files, normalizes them, and upserts them into Postgres with `pgvector` enabled.

```bash
PYTHONPATH=src DATABASE_URL="postgresql://postgres:postgres@localhost:5432/pft_portfolio" \
  python3 examples/live_prototype.py --output-dir prototype-output
```

The default proof sources require no private keys.

| Source | Public identifier |
| --- | --- |
| BTC | `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa` |
| ETH | `0x00000000219ab540356cBB839Cbe05303d7705Fa` |
| SOL | `AwA1urYEnZpCQfkB9w9rFAhTSicqniimBfu9yNnuZTSf` |
| Hyperliquid vault | `0xd6e56265890b76413d1d527eb9b75e334c0c5b42` |

The proof writes these files under the selected output directory:

```text
btc_snapshot.csv, btc_transactions.csv,
eth_snapshot.csv, eth_transactions.csv,
sol_snapshot.csv, sol_transactions.csv,
hyperliquid_vault_snapshot.csv, hyperliquid_vault_transactions.csv,
summary.json
```

`summary.json` includes source row counts, row-quality counters, run metadata, and Postgres table counts. `portfolio_views` can be `0` for live exporter runs because these public exporters emit asset-level snapshots rather than aggregate portfolio overview rows.

GitHub Actions runs the same proof in `.github/workflows/live-prototype.yml` with a `pgvector/pgvector:pg16` service container and uploads `prototype-output/` as the `live-prototype-output` artifact.

Committed sample artifacts live under `artifacts/live-prototype-output/`. They are review fixtures from a specific successful run, not an implicit claim that the current checkout has already regenerated them. `manifest.json` records file columns, row counts, hashes, and workflow metadata; `summary.json` records runtime quality and database counts.

## Tests

Default tests are deterministic and do not call public APIs:

```bash
python3 -m pytest
```

Run live exporter checks separately when network access and public endpoint variability are acceptable:

```bash
python3 -m pytest -m live
```

The live tests use structural assertions because balances, positions, public RPC responses, and exchange histories change over time. The workflow proof is the stronger end-to-end check because it also starts Postgres, applies migrations, stores all proof sources, and uploads the generated CSV/JSON artifact.

## Out Of Scope

This package does not implement embedding generation, RAG queries, strategy recommendations, portfolio scoring, a schema registry, private-key wallet access, or production scheduling. Those layers can consume the normalized history and derived-context tables, but they are intentionally outside this repository.

## Current Fixtures

| File | Purpose |
| --- | --- |
| `fixtures/test_portfolio_with_portfolio_overview.csv` | Minimal CMC-style portfolio snapshot with an overview block |
| `fixtures/transaction_history_2026-04-22.csv` | Matching transaction history using the standard event vocabulary |
| `artifacts/live-prototype-output/` | Public-data sample output from a successful live proof run |

The original shared CMC example remains at the repository root for reference; tests use the fixture copy under `fixtures/`.
