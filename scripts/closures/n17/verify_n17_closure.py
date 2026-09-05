#!/usr/bin/env python3
"""Lightweight independent audit of the saved n=17 closure artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
OUTPUTS = PROJECT / "certificates" / "exact_closures" / "n17"
WITNESS = PROJECT / "constructions" / "n17.json"
OUTPUT = OUTPUTS / "closure_certificate.json"
if str(PROJECT / "verifiers") not in sys.path:
    sys.path.insert(0, str(PROJECT / "verifiers"))

from life import verify_payload  # noqa: E402


EXPECTED_RECORD_HASHES = {
    "depth5_probe.json": (
        "24de0ddca95bf34fc903b32b829ead89eb66f815a00f25c7f6c987291b5e2afa"
    ),
    "depth5_equality_orbits.json": (
        "7c1eac915dced1484d99754ed3cda38c0f90e699df15f04a5e9a4dd9ccc68a4e"
    ),
    "depth6_equality_lift.json": (
        "9bbb37f0d7b126ebd2547075d60a9d05b1ff1a4ae87fe9d7df220c4bf713446b"
    ),
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_record_hash(record: dict[str, Any]) -> str:
    copy = dict(record)
    stored = copy.pop("record_sha256_excluding_this_field")
    copy["record_sha256_excluding_this_field"] = None
    digest = hashlib.sha256(
        json.dumps(copy, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    if digest != stored:
        raise AssertionError("record self-hash mismatch")
    return digest


def build() -> dict[str, Any]:
    records = {
        name: load(OUTPUTS / name)
        for name in EXPECTED_RECORD_HASHES
    }
    observed_hashes = {
        name: canonical_record_hash(record)
        for name, record in records.items()
    }
    if observed_hashes != EXPECTED_RECORD_HASHES:
        raise AssertionError(
            "saved component record hash mismatch: "
            f"observed={observed_hashes!r}"
        )

    depth5 = records["depth5_probe.json"]
    orbit = records["depth5_equality_orbits.json"]
    depth6 = records["depth6_equality_lift.json"]
    if depth5["n17_consequence"]["minimum_depth5_boundary_wastage"] != 38:
        raise AssertionError("depth-five minimum is not 38")
    if orbit["complete_equality_support"]["state_count"] != 21:
        raise AssertionError("wrong equality state count")
    if orbit["complete_equality_support"]["arc_count"] != 50:
        raise AssertionError("wrong equality arc count")
    lift_test = depth6["depth6"]["anchored_four_cycle_test"]
    if lift_test["cycle_at_or_below_target_exists"]:
        raise AssertionError("target-38 depth-six lift exists")
    if lift_test["minimum_anchored_four_cycle_cost"] != 39:
        raise AssertionError("depth-six minimum is not 39")
    if depth6["depth5"]["equality_physical_patch_count"] != 27:
        raise AssertionError("wrong full physical equality-patch count")

    witness_payload = load(WITNESS)
    verification = verify_payload(witness_payload)
    if not verification.valid or verification.population != 151:
        raise AssertionError("saved 151-cell witness is invalid")

    return {
        "schema": "n17-connected-still-life-closure-v1",
        "n": 17,
        "lower_certificate": {
            "witness": str(WITNESS.relative_to(PROJECT)),
            "verification": verification.to_dict(),
            "witness_file_sha256": hashlib.sha256(
                WITNESS.read_bytes()
            ).hexdigest(),
        },
        "upper_certificate": {
            "target_population_excluded": 152,
            "target_total_wastage": 38,
            "depth5_minimum": 38,
            "depth5_equality_state_count": 21,
            "depth5_equality_arc_count": 50,
            "full_physical_equality_corner_patch_count": 27,
            "safe_depth6_minimum": 39,
            "component_record_hashes": observed_hashes,
            "proof": (
                "Connected population 152 implies block-free. Its exact "
                "wastage is W=2*17^2+4*17-4*152=38. Nonnegative local "
                "wastage forces its depth-five projection to be a minimum "
                "target-38 equality ring and its sixth layer to add zero. "
                "The complete tied-patch safe lift language has minimum "
                "four-side cost 39, a contradiction."
            ),
        },
        "theorem": "C(17)=151",
        "uses_full_board_search": False,
        "record_sha256_excluding_this_field": None,
    }


def finalize(record: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record["record_sha256_excluding_this_field"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = finalize(build())
    if args.verify:
        existing = load(args.output)
        existing_canonical = json.dumps(
            existing, sort_keys=True, separators=(",", ":")
        )
        rebuilt_canonical = json.dumps(
            record, sort_keys=True, separators=(",", ":")
        )
        if existing_canonical != rebuilt_canonical:
            raise SystemExit("stored n=17 closure certificate differs")
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
