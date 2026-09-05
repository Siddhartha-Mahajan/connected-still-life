#!/usr/bin/env python3
"""Enumerate the complete n=18 depth-five target-36 equality support."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
N17 = ROOT / "scripts" / "closures" / "n17"
OUTPUT = (
    ROOT
    / "certificates"
    / "exact_closures"
    / "n18"
    / "depth5_equality_orbits.json"
)
N = 18
TARGET = 36

if str(N17) not in sys.path:
    sys.path.insert(0, str(N17))

import enumerate_equality_orbits as generic  # noqa: E402


def build() -> dict:
    # The generic equality-lift implementation is generic except for its deliberate
    # fixed-certificate guard.  Reset that guard, then relabel the record.
    generic.N = N
    generic.TARGET = TARGET
    record = generic.build(N, TARGET)
    record["schema"] = "n18-depth5-equality-orbit-support-v1"
    record["claim_scope"] = (
        "Complete state/arc support of depth-five target-36 cycles at "
        "n=18. This is a boundary transfer certificate, not a full-board "
        "search."
    )
    record["record_sha256_excluding_this_field"] = None
    return generic.finalize(record)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = build()
    if args.verify:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored n=18 equality support differs")
        print(
            "VERIFIED",
            record["record_sha256_excluding_this_field"],
        )
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "anchor_enumeration": record["anchor_enumeration"],
                "complete_equality_support": {
                    key: record["complete_equality_support"][key]
                    for key in ("state_count", "arc_count")
                },
                "states": record["complete_equality_support"]["states"],
                "arc_state_indices": record[
                    "complete_equality_support"
                ]["arc_state_indices"],
                "record_sha256": record[
                    "record_sha256_excluding_this_field"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
