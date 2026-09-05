#!/usr/bin/env python3
"""Run the exact depth-five boundary ring at n=17 and target W=38."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BOUNDARY = ROOT / "scripts" / "boundary"
OUTPUT = (
    ROOT / "certificates" / "exact_closures" / "n17" / "depth5_probe.json"
)
if str(BOUNDARY) not in sys.path:
    sys.path.insert(0, str(BOUNDARY))

import certify_depth5_ring as depth5  # noqa: E402


def build() -> dict:
    record = depth5.build([17])
    record["schema"] = "n17-depth5-exact-closure-probe-v1"
    row = record["rows"][0]
    test = row["anchored_four_cycle_test"]
    minimum = test["minimum_anchored_four_cycle_cost"]
    record["n17_consequence"] = {
        "target_population": 152,
        "target_total_wastage": 38,
        "minimum_depth5_boundary_wastage": minimum,
        "wastage_congruence": "W=646-4L, hence W=2 mod 4",
        "excludes_population_152": minimum > 38,
        "proved_exact_value": (
            "C(17)=151" if minimum > 38 else None
        ),
    }
    record["record_sha256_excluding_this_field"] = None
    canonical = json.dumps(
        record, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    record["record_sha256_excluding_this_field"] = hashlib.sha256(
        canonical
    ).hexdigest()
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = build()
    if args.verify:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored n=17 depth-five probe differs")
        print(
            "VERIFIED",
            record["n17_consequence"],
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
                **record["n17_consequence"],
                "record_sha256": record[
                    "record_sha256_excluding_this_field"
                ],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
