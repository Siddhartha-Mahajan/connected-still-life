#!/usr/bin/env python3
"""Assemble and verify the connected n=18 upper certificate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUTPUTS = ROOT / "certificates" / "exact_closures" / "n18"
OUTPUT = OUTPUTS / "population171_exclusion_certificate.json"

INPUTS = (
    "depth5_probe.json",
    "depth5_equality_orbits.json",
    "depth6_equality_lift.json",
    "depth6_equality_orbits.json",
    "depth7_equality_lift.json",
)


def load(name: str) -> dict[str, Any]:
    return json.loads((OUTPUTS / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, Any]:
    probe5 = load(INPUTS[0])
    orbit5 = load(INPUTS[1])
    lift6 = load(INPUTS[2])
    orbit6 = load(INPUTS[3])
    lift7 = load(INPUTS[4])

    checks = {
        "n_is_18": (
            probe5["rows"][0]["n"] == 18
            and all(
                record["n"] == 18
                for record in (orbit5, lift6, orbit6, lift7)
            )
        ),
        "target_population_is_171": (
            probe5["n18_consequence"]["target_population"] == 171
            and lift6["target_population"] == 171
            and orbit6["target_population"] == 171
            and lift7["target_population"] == 171
        ),
        "target_wastage_is_36": (
            probe5["n18_consequence"]["target_total_wastage"] == 36
            and orbit5["four_side_target"] == 36
            and lift6["target_total_wastage"] == 36
            and orbit6["target_total_wastage"] == 36
            and lift7["target_total_wastage"] == 36
        ),
        "depth5_minimum_is_36": (
            probe5["n18_consequence"][
                "minimum_depth5_boundary_wastage"
            ]
            == 36
        ),
        "depth5_equality_support_is_complete": (
            orbit5["complete_equality_support"]["state_count"] == 4
            and orbit5["complete_equality_support"]["arc_count"] == 8
        ),
        "depth6_safe_lift_survives_at_36": (
            not lift6["consequence"][
                "depth6_boundary_wastage_strictly_exceeds_36"
            ]
        ),
        "depth6_equality_support_is_complete": (
            orbit6["complete_equality_support"]["state_count"] == 4
            and orbit6["complete_equality_support"]["arc_count"] == 4
        ),
        "all_depth6_equality_mappings_have_physical_representatives": (
            lift7["depth6"]["equality_mapping_key_count"] == 4
            and lift7["depth6"]["physical_equality_patch_count"] == 8
        ),
        "depth7_target36_support_is_empty": (
            lift7["depth7"]["complete_equality_support"]["state_count"] == 0
            and lift7["depth7"]["complete_equality_support"]["arc_count"] == 0
            and lift7["depth7"]["complete_equality_support"]["anchor"][
                "equality_anchor_count"
            ]
            == 0
        ),
        "connected_population_171_excluded": lift7["consequence"][
            "connected_population_171_excluded"
        ],
        "connected_upper_bound_is_170": (
            lift7["consequence"]["connected_upper_bound"] == 170
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise AssertionError(f"failed closure checks: {failed}")

    record: dict[str, Any] = {
        "schema": "connected-n18-population171-exclusion-v1",
        "theorem": "C(18)<=170",
        "n": 18,
        "target_population_excluded": 171,
        "target_total_wastage": 36,
        "proof_scope": (
            "Every connected still life with more than four cells is "
            "block-free. A hypothetical connected 171-cell n=18 board "
            "would therefore lie in the complete block-free depth-five "
            "target-36 language. Every inward charge is nonnegative, so "
            "such a board must remain in the complete zero-added-wastage "
            "equality support at depths six and seven. The exact safe "
            "depth-seven support is empty."
        ),
        "does_not_claim": (
            "This bound concerns connected patterns. Unrestricted population "
            "171 remains possible."
        ),
        "checks": checks,
        "summary": {
            "depth5_minimum": 36,
            "depth5_equality_states": 4,
            "depth5_equality_arcs": 8,
            "depth6_equality_states": 4,
            "depth6_equality_arcs": 4,
            "depth6_physical_equality_patches": 8,
            "depth7_equality_states": 0,
            "depth7_equality_arcs": 0,
        },
        "inputs": {
            f"n18_{name}": {
                "sha256": sha256(OUTPUTS / name),
                "record_sha256": load(name).get(
                    "record_sha256_excluding_this_field"
                ),
            }
            for name in INPUTS
        },
        "record_sha256_excluding_this_field": None,
    }
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
        stored = json.loads(args.output.read_text(encoding="utf-8"))
        if stored != record:
            raise SystemExit("stored closure certificate differs")
        print(
            "VERIFIED",
            record["theorem"],
            record["record_sha256_excluding_this_field"],
        )
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        record["theorem"],
        record["record_sha256_excluding_this_field"],
    )


if __name__ == "__main__":
    main()
