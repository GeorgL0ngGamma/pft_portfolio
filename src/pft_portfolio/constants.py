"""Small vocabulary for CSV-first portfolio history ingestion."""

INPUT_TYPES = ("portfolio_snapshot", "transaction_history")

INSTRUMENT_TYPES = ("spot", "perp", "future", "option", "yield")

EXTENDED_COLUMNS = (
    "asset_class",
    "chain",
    "address",
    "contract_address",
    "tx_hash",
    "block_number",
    "log_index",
    "external_id",
    "venue",
    "protocol",
    "counterparty",
    "fee_amount",
    "fee_symbol",
)

SNAPSHOT_COLUMNS = (
    "user_id",
    "account_ref",
    "as_of",
    "currency",
    "asset_name",
    "symbol",
    "instrument_type",
    "price",
    "change_1h_pct",
    "change_24h_pct",
    "change_7d_pct",
    "holdings_value",
    "amount",
    "avg_buy_price",
    "profit_loss_value",
    "profit_loss_pct",
    *EXTENDED_COLUMNS,
)

TRANSACTION_COLUMNS = (
    "user_id",
    "account_ref",
    "timestamp",
    "activity_type",
    "asset_name",
    "symbol",
    "instrument_type",
    "amount",
    "price",
    "value",
    "currency",
    "profit_loss_value",
    "profit_loss_pct",
    "holdings_after",
    *EXTENDED_COLUMNS,
)

EXPORT_EXTRA_COLUMNS = ("raw_json",)

SNAPSHOT_EXPORT_COLUMNS = SNAPSHOT_COLUMNS + EXPORT_EXTRA_COLUMNS
TRANSACTION_EXPORT_COLUMNS = TRANSACTION_COLUMNS + EXPORT_EXTRA_COLUMNS

ASSET_SYMBOLS = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "ether": "ETH",
    "eth": "ETH",
    "solana": "SOL",
    "sol": "SOL",
    "usd coin": "USDC",
    "usdc": "USDC",
    "us dollar": "USD",
    "usd": "USD",
}

DEFAULT_USER_ID = "demo"
DEFAULT_ACCOUNT_REF = "manual:portfolio"
