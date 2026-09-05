#!/usr/bin/env python3
"""Verify the complete construction archive against the bounds ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from life import verify_file  # noqa: E402


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def build_report() -> dict[str, Any]:
    ledger_path = ROOT / "data" / "bounds.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    rows = []
    accepted = True
    for bound in ledger["bounds"]:
        n = int(bound["n"])
        if n == 1:
            rows.append(
                {
                    "n": 1,
                    "population": 0,
                    "accepted": (
                        bound["lower_bound"] == 0
                        and bound["upper_bound"] == 0
                    ),
                    "convention": "empty box",
                }
            )
            accepted &= rows[-1]["accepted"]
            continue
        path = ROOT / bound["witness"]
        check = verify_file(path)
        row = {
            "n": n,
            "path": str(path.relative_to(ROOT)),
            "file_sha256": file_digest(path),
            "grid_sha256": check.grid_sha256,
            "population": check.population,
            "stable": check.stable,
            "connected": check.connected,
            "components": check.components,
            "full_ring_violation_count": len(check.violations),
            "matches_lower_bound": (
                check.population == bound["lower_bound"]
            ),
            "accepted": (
                check.valid
                and check.population == bound["lower_bound"]
            ),
        }
        rows.append(row)
        accepted &= row["accepted"]
    exact_rows = [
        row["n"]
        for row, bound in zip(rows, ledger["bounds"], strict=True)
        if bound["exact"]
    ]
    return {
        "schema": "connected-still-life-archive-audit-v1",
        "accepted": accepted,
        "ledger_sha256": file_digest(ledger_path),
        "construction_count": len(rows) - 1,
        "range": [1, 50],
        "exact_indices": exact_rows,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report()
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = args.output
        if not target.is_absolute():
            target = ROOT / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding="utf-8")
        print(target)
    else:
        print(encoded, end="")
    raise SystemExit(0 if report["accepted"] else 1)


if __name__ == "__main__":
    main()
