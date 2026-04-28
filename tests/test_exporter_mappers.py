from __future__ import annotations

from pft_portfolio.exporters.ccxt_exchange import _fee_row, _trade_row
from pft_portfolio.exporters.ethereum import _include_eth_transaction
from pft_portfolio.exporters.solana import _tx_row


def test_eth_filter_excludes_failed_and_zero_value_rows_by_default() -> None:
    assert not _include_eth_transaction({"status": "ok", "value": "0"}, include_failed=False, include_zero_value=False)
    assert not _include_eth_transaction({"status": "error", "value": "1"}, include_failed=False, include_zero_value=False)
    assert _include_eth_transaction({"status": "ok", "value": "1"}, include_failed=False, include_zero_value=False)


def test_ccxt_trade_rows_preserve_venue_address_and_transaction_hash() -> None:
    trade = {
        "amount": 2,
        "cost": 20,
        "fee": {"cost": 0.01, "currency": "USDC"},
        "id": "tid-1",
        "info": {"closedPnl": "0", "hash": "0xabc", "startPosition": "4"},
        "order": "oid-1",
        "price": 10,
        "side": "buy",
        "symbol": "HYPE/USDC:USDC",
        "timestamp": 1777394472383,
    }

    row = _trade_row(trade, "hyperliquid", "prototype", "hyperliquid:0xvault", "0xvault")
    fee = _fee_row(trade, "hyperliquid", "prototype", "hyperliquid:0xvault", "0xvault")

    assert row["address"] == "0xvault"
    assert row["tx_hash"] == "0xabc"
    assert row["external_id"] == "tid-1"
    assert fee["address"] == "0xvault"
    assert fee["tx_hash"] == "0xabc"
    assert fee["external_id"] == "fee:tid-1"


def test_solana_row_preserves_fee_counterparty_and_nonzero_delta() -> None:
    signature = {"signature": "sig-1", "slot": 123, "blockTime": 1777394472, "err": None}
    tx = {
        "transaction": {
            "message": {
                "accountKeys": ["counterparty", "target"],
                "header": {"numRequiredSignatures": 1},
            }
        },
        "meta": {"fee": 5000},
    }

    row = _tx_row(signature, tx, "target", "prototype", "sol:target", delta=2000000)

    assert row["amount"] == "0.002"
    assert row["counterparty"] == "counterparty"
    assert row["fee_amount"] == "0.000005"
    assert row["fee_symbol"] == "SOL"
