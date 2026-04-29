"""Reviewer-readable JSONL storage for normalized portfolio history records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .csv_ingest import ingest_portfolio_snapshot_csv, ingest_transaction_history_csv, parse_timestamp


class PortfolioStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def add_snapshot_csv(self, path: str | Path, *, user_id: str = "demo", account_ref: str = "manual:portfolio") -> int:
        document = ingest_portfolio_snapshot_csv(path, user_id=user_id, account_ref=account_ref)
        return self.append_records(_records_from_snapshot_document(document))

    def add_transaction_csv(self, path: str | Path, *, user_id: str = "demo", account_ref: str = "manual:portfolio") -> int:
        document = ingest_transaction_history_csv(path, user_id=user_id, account_ref=account_ref)
        return self.append_records(document["transactions"])

    def append_records(self, records: Iterable[dict[str, Any]]) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing_ids = {record.get("id") for record in self.read_records() if record.get("id")}
        count = 0
        with self.path.open("a", encoding="utf-8") as handle:
            for record in records:
                record_id = record.get("id")
                if record_id and record_id in existing_ids:
                    continue
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                if record_id:
                    existing_ids.add(record_id)
                count += 1
        return count

    def read_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records

    def portfolio_at(self, user_id: str, at: str) -> dict[str, Any]:
        at_rfc3339 = parse_timestamp(at)
        records = [record for record in self.read_records() if record.get("user_id") == user_id]
        snapshot_records = [
            record
            for record in records
            if record.get("input_type") == "portfolio_snapshot" and record.get("as_of") and record["as_of"] <= at_rfc3339
        ]
        asset_snapshots = [record for record in snapshot_records if record.get("asset_name")]
        latest_snapshot_at = max((record["as_of"] for record in asset_snapshots), default=None)
        positions = [record for record in asset_snapshots if record.get("as_of") == latest_snapshot_at]
        overview = next(
            (
                record
                for record in snapshot_records
                if record.get("as_of") == latest_snapshot_at and record.get("total_value") is not None
            ),
            None,
        )
        transactions = [
            record
            for record in records
            if record.get("input_type") == "transaction_history" and record.get("timestamp") and record["timestamp"] <= at_rfc3339
        ]
        return {
            "user_id": user_id,
            "as_of": at_rfc3339,
            "latest_snapshot_as_of": latest_snapshot_at,
            "overview": overview,
            "positions": positions,
            "transactions": sorted(transactions, key=lambda record: (record.get("timestamp"), record.get("id"))),
        }


def _records_from_snapshot_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    overview = document.get("overview")
    if overview:
        records.append(overview)
    records.extend(document.get("positions") or [])
    return records
