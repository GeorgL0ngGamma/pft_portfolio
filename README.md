# pft_portfolio

CSV-first portfolio-history ingestion scaffold for Post Fiat reviewers.

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

There is no `source_type`, `state_model`, or dedicated `record_type` in this v0 scaffold. Provenance is carried by `source_csv`, `source_row`, and preserved raw CSV row content after ingestion.

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

Fees, funding, transfers, deposits, withdrawals, buys, sells, rewards, staking, and similar events are represented as `activity_type` values, not as top-level schema columns.

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

store = PortfolioStore("portfolio-history.jsonl")
store.add_snapshot_csv("fixtures/test_portfolio_with_portfolio_overview.csv")
store.add_transaction_csv("fixtures/transaction_history_2026-04-22.csv")
view = store.portfolio_at("demo", "2026-04-22T12:00:00Z")
```

## Live Tests

The test suite includes live tests, not fake exchange or chain adapters:

- CCXT Hyperliquid public account snapshot and trades.
- BTC address snapshot and transactions.
- ETH address snapshot and transactions.
- SOL address snapshot and transactions.

These tests make public network calls and use structural assertions because balances and positions move.

## Out Of Scope

The v0 package does not implement:

- LLM retrieval, RAG, embeddings, or semantic search.
- Query modeling beyond a minimal `portfolio_at` readback helper.
- Strategy recommendations or portfolio scoring.
- A heavyweight schema registry.

The intended next layer can brainstorm with LLMs over the normalized history, but this package stops at CSV export, CSV ingestion, and reviewer-readable historical storage.

## Open Questions

- Whether JSONL remains sufficient or should evolve into SQLite/Postgres once reviewers settle the CSV contract.
- How much derivative-specific detail should be preserved in CSV columns versus `raw_json`.
- Which chain/indexer providers should be official defaults for production transaction history.
- Whether CMC-style overview rows should remain a special parser or be converted into the standardized snapshot CSV before ingestion.
