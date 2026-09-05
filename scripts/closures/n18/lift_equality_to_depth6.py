#!/usr/bin/env python3
"""Lift every n=18 target-36 depth-five equality boundary to depth six."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
N17 = ROOT / "scripts" / "closures" / "n17"
CERTIFICATES = ROOT / "certificates" / "exact_closures" / "n18"
ORBIT = CERTIFICATES / "depth5_equality_orbits.json"
OUTPUT = CERTIFICATES / "depth6_equality_lift.json"
N = 18
TARGET = 36
TARGET_POPULATION = 171

if str(N17) not in sys.path:
    sys.path.insert(0, str(N17))

import certify_depth6_equality_lift as generic  # noqa: E402


def build() -> dict:
    generic.N = N
    generic.TARGET = TARGET
    generic.ORBIT = ORBIT
    record = generic.build()
    survives = record["depth6"][
        "zero_additional_wastage_equality_lift_exists"
    ]
    record["schema"] = "n18-complete-depth6-equality-lift-v1"
    record["target_population"] = TARGET_POPULATION
    record["consequence"] = {
        "depth6_boundary_wastage_strictly_exceeds_36": not survives,
        "population_171_excluded": not survives,
        "connected_upper_bound": 170 if not survives else 171,
        "logic": (
            "Any connected population-171 board is block-free and has total "
            "W=36.  It projects to the complete depth-five target-36 "
            "equality support and must add zero sixth-layer wastage.  The "
            "safe lifted language contains every such projection."
        ),
        "next_step": (
            "global population 171 excluded"
            if not survives
            else "enumerate complete depth-six target-36 equality support"
        ),
    }
    record["completeness_notes"] = [
        note.replace("population 152", "population 171")
        .replace("n=17", "n=18")
        .replace("W=38", "W=36")
        .replace("cost <=38", "cost <=36")
        for note in record["completeness_notes"]
    ]
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
            raise SystemExit("stored n=18 depth-six lift differs")
        print(
            "VERIFIED",
            record["consequence"],
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
                "depth5": {
                    "equality_mapping_key_count": record["depth5"][
                        "equality_mapping_key_count"
                    ],
                    "equality_physical_patch_count": record["depth5"][
                        "equality_physical_patch_count"
                    ],
                },
                "depth6": {
                    "corner_output_state_count": record["depth6"][
                        "corner_output_state_count"
                    ],
                    "corner_lift_statistics": record["depth6"][
                        "corner_lift_statistics"
                    ],
                    "anchored_four_cycle_test": record["depth6"][
                        "anchored_four_cycle_test"
                    ],
                },
                "consequence": record["consequence"],
                "record_sha256": record[
                    "record_sha256_excluding_this_field"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
