"""Command line helpers for CSV-first portfolio history ingestion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .canonical import canonical_json
from .csv_ingest import ingest_portfolio_snapshot_csv, ingest_transaction_history_csv
from .storage import PortfolioStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pft-portfolio")
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser("normalize", help="normalize a dated CSV")
    normalize.add_argument("input_type", choices=["snapshot", "transactions"])
    normalize.add_argument("path")
    normalize.add_argument("--user-id", default="demo")
    normalize.add_argument("--account-ref", default="manual:portfolio")

    store = subparsers.add_parser("store-add", help="append a dated CSV to JSONL storage")
    store.add_argument("store_path")
    store.add_argument("input_type", choices=["snapshot", "transactions"])
    store.add_argument("path")
    store.add_argument("--user-id", default="demo")
    store.add_argument("--account-ref", default="manual:portfolio")

    point_in_time = subparsers.add_parser("portfolio-at", help="read a point-in-time portfolio view from JSONL storage")
    point_in_time.add_argument("store_path")
    point_in_time.add_argument("user_id")
    point_in_time.add_argument("timestamp")

    args = parser.parse_args(argv)
    if args.command == "normalize":
        document = _normalize(args.input_type, args.path, args.user_id, args.account_ref)
        print(canonical_json(document))
        return 0
    if args.command == "store-add":
        store_obj = PortfolioStore(args.store_path)
        if args.input_type == "snapshot":
            count = store_obj.add_snapshot_csv(args.path, user_id=args.user_id, account_ref=args.account_ref)
        else:
            count = store_obj.add_transaction_csv(args.path, user_id=args.user_id, account_ref=args.account_ref)
        print(json.dumps({"stored": count, "store_path": str(Path(args.store_path))}, sort_keys=True))
        return 0
    if args.command == "portfolio-at":
        print(canonical_json(PortfolioStore(args.store_path).portfolio_at(args.user_id, args.timestamp)))
        return 0
    return 2


def _normalize(input_type: str, path: str, user_id: str, account_ref: str) -> dict[str, object]:
    if input_type == "snapshot":
        return ingest_portfolio_snapshot_csv(path, user_id=user_id, account_ref=account_ref)
    return ingest_transaction_history_csv(path, user_id=user_id, account_ref=account_ref)


if __name__ == "__main__":
    raise SystemExit(main())
