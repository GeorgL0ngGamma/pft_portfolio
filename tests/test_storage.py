from __future__ import annotations

from pathlib import Path

from pft_portfolio.storage import PortfolioStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def test_store_appends_csvs_and_reconstructs_point_in_time_view(tmp_path: Path) -> None:
    store = PortfolioStore(tmp_path / "portfolio-history.jsonl")

    snapshot_count = store.add_snapshot_csv(
        FIXTURES / "test_portfolio_with_portfolio_overview.csv",
        user_id="demo",
        account_ref="manual:cmc",
    )
    transaction_count = store.add_transaction_csv(FIXTURES / "transaction_history_2026-04-22.csv")

    assert snapshot_count == 2
    assert transaction_count == 4
    assert len(store.read_records()) == 6

    portfolio = store.portfolio_at("demo", "2026-04-22T12:00:00Z")
    assert portfolio["latest_snapshot_as_of"] == "2026-04-22T10:01:45Z"
    assert portfolio["overview"]["total_value"] == "78023.63"
    assert len(portfolio["positions"]) == 1
    assert portfolio["positions"][0]["symbol"] == "BTC"
    assert len(portfolio["transactions"]) == 4


def test_store_returns_empty_view_before_first_snapshot(tmp_path: Path) -> None:
    store = PortfolioStore(tmp_path / "portfolio-history.jsonl")
    store.add_snapshot_csv(FIXTURES / "test_portfolio_with_portfolio_overview.csv")

    portfolio = store.portfolio_at("demo", "2026-04-20T00:00:00Z")
    assert portfolio["latest_snapshot_as_of"] is None
    assert portfolio["positions"] == []
    assert portfolio["transactions"] == []
