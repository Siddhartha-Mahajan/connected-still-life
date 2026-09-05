#!/usr/bin/env python3
"""Run the exact depth-five n=18 boundary ring at target W=36."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BOUNDARY = ROOT / "scripts" / "boundary"
OUTPUT = (
    ROOT / "certificates" / "exact_closures" / "n18" / "depth5_probe.json"
)
if str(BOUNDARY) not in sys.path:
    sys.path.insert(0, str(BOUNDARY))

import certify_depth5_ring as depth5  # noqa: E402


N = 18
TARGET_POPULATION = 171
TARGET_WASTAGE = 36


def build() -> dict:
    record = depth5.build([N])
    record["schema"] = "n18-depth5-global-equality-probe-v1"
    row = record["rows"][0]
    test = row["anchored_four_cycle_test"]
    minimum = test["minimum_anchored_four_cycle_cost"]
    if row["depth4_wastage_target"] != TARGET_WASTAGE:
        raise AssertionError("unexpected n=18 depth-four target")
    record["n18_consequence"] = {
        "target_population": TARGET_POPULATION,
        "target_total_wastage": TARGET_WASTAGE,
        "minimum_depth5_boundary_wastage": minimum,
        "wastage_congruence": "W=720-4L, hence W=0 mod 4",
        "excludes_population_171": minimum > TARGET_WASTAGE,
        "upper_bound_if_excluded": (
            170 if minimum > TARGET_WASTAGE else 171
        ),
        "next_step": (
            "enumerate complete target-36 equality support"
            if minimum == TARGET_WASTAGE
            else (
                "population 171 is excluded by the scalar language"
                if minimum > TARGET_WASTAGE
                else "audit unexpected value below the proved target"
            )
        ),
        "claim_boundary": (
            "Connected population 171 is block-free.  A depth-five minimum "
            "above 36 therefore excludes it globally.  Equality at 36 is "
            "only a boundary necessary condition and requires inward lifts."
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
            raise SystemExit("stored n=18 depth-five probe differs")
        print(
            "VERIFIED",
            record["n18_consequence"],
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
                **record["n18_consequence"],
                "anchored_four_cycle_test": record["rows"][0][
                    "anchored_four_cycle_test"
                ],
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
