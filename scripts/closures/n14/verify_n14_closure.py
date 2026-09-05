#!/usr/bin/env python3
"""Verify the saved structural certificate proving C(14)=102."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
BOUNDARY = PROJECT / "scripts" / "boundary"
CERTIFICATES = PROJECT / "certificates" / "exact_closures" / "n14"
DEFAULT_CENSUS = CERTIFICATES / "all_low_slack_belt_census.json"
DEFAULT_OUTPUT = CERTIFICATES / "closure_certificate.json"
LOWER_WITNESS = PROJECT / "constructions" / "n14.json"
RING_CERTIFICATE = (
    PROJECT / "certificates" / "upper_bounds" / "depth4_ring_certificate.json"
)

for directory in (PROJECT / "verifiers", BOUNDARY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from certify_depth3_edge import chu_wastage  # noqa: E402
from life import connected_components, verify_grid  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record_hash(record: dict[str, Any]) -> str:
    copy = dict(record)
    copy["record_sha256_excluding_this_field"] = None
    canonical = json.dumps(copy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def wastage(grid: list[list[int]]) -> int:
    n = len(grid)

    def value(row: int, column: int) -> int:
        if 0 <= row < n and 0 <= column < n:
            return grid[row][column]
        return 0

    total = 0
    for row in range(n):
        for column in range(n):
            pattern = tuple(
                value(row + dr, column + dc)
                for dr in (-1, 0, 1)
                for dc in (-1, 0, 1)
            )
            total += chu_wastage(pattern)
    total += sum(1 - grid[0][column] for column in range(n))
    total += sum(1 - grid[-1][column] for column in range(n))
    total += sum(1 - grid[row][0] for row in range(n))
    total += sum(1 - grid[row][-1] for row in range(n))
    return total


def has_live_block(grid: list[list[int]]) -> bool:
    n = len(grid)
    return any(
        grid[row][column]
        and grid[row + 1][column]
        and grid[row][column + 1]
        and grid[row + 1][column + 1]
        for row in range(n - 1)
        for column in range(n - 1)
    )


def verify(
    census_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    census = json.loads(census_path.read_text(encoding="utf-8"))
    if census["record_sha256_excluding_this_field"] != record_hash(census):
        raise AssertionError("low-slack census record hash mismatch")
    expected = {
        "n": 14,
        "target_population": 103,
        "target_total_wastage": 36,
        "abstract_cycles_mod_rotation": 2664,
        "supported_arc_count": 694,
        "physical_belt_combination_count_before_deduplication": 261225,
        "processed_physical_combinations": 261225,
        "distinct_physical_belts_processed": 261225,
        "distinct_frame_population_keys": 34490,
        "stable_population_103_completions_examined": 224,
        "connected_population_103_completions": 0,
    }
    for key, value in expected.items():
        if census.get(key) != value:
            raise AssertionError(
                f"census {key}={census.get(key)!r}, expected {value!r}"
            )
    if (
        census["census_only"]
        or census["stopped_at_limit"]
        or census["connected_witness_found"]
    ):
        raise AssertionError("low-slack census was not a complete UNSAT run")
    if census["abstract_cycle_baseline_histogram"] != {
        "34": 105,
        "35": 274,
        "36": 2285,
    }:
        raise AssertionError("abstract cycle histogram mismatch")
    if census[
        "physical_combination_histogram_by_baseline_and_allowance"
    ] != {
        "34,2": 72193,
        "35,1": 87672,
        "36,0": 101360,
    }:
        raise AssertionError("physical belt histogram mismatch")
    if sum(
        census["stable_completion_component_size_histogram"].values()
    ) != 224:
        raise AssertionError("stable component histogram does not sum to 224")
    if any(
        len(key.split(",")) == 1
        for key in census[
            "stable_completion_component_size_histogram"
        ]
    ):
        raise AssertionError("certificate contains a connected completion")

    sample_results = []
    for sample in census["stable_completion_samples"]:
        grid = [[int(value) for value in row] for row in sample["grid"]]
        check = verify_grid(grid, claimed_cells=103)
        components = connected_components(grid)
        sizes = sorted(
            (len(component) for component in components), reverse=True
        )
        digest = hashlib.sha256(
            "".join(str(value) for row in grid for value in row).encode(
                "ascii"
            )
        ).hexdigest()
        if (
            not check.stable
            or check.population != 103
            or check.connected
            or sizes != sample["component_sizes"]
            or digest != sample["sha256"]
            or wastage(grid) != 36
        ):
            raise AssertionError(
                {
                    "sample": sample["sha256"],
                    "verification": check.to_dict(),
                    "sizes": sizes,
                    "digest": digest,
                    "wastage": wastage(grid),
                    "has_live_block": has_live_block(grid),
                }
            )
        sample_results.append(
            {
                "sha256": digest,
                "population": check.population,
                "wastage": 36,
                "component_sizes": sizes,
                "block_free": not has_live_block(grid),
            }
        )

    lower = json.loads(LOWER_WITNESS.read_text(encoding="utf-8"))
    lower_grid = lower["grid"]
    lower_check = verify_grid(lower_grid, claimed_cells=102)
    if not lower_check.valid or has_live_block(lower_grid):
        raise AssertionError(lower_check.to_dict())
    lower_wastage = wastage(lower_grid)
    if lower_wastage != 40:
        raise AssertionError(f"102 witness wastage is {lower_wastage}, not 40")

    ring = json.loads(RING_CERTIFICATE.read_text(encoding="utf-8"))
    n14_rows = [row for row in ring["rows"] if row["n"] == 14]
    if len(n14_rows) != 1:
        raise AssertionError("depth-four certificate lacks unique n=14 row")
    n14_ring = n14_rows[0]
    if (
        n14_ring["boundary_wastage_lower_bound"] != 34
        or n14_ring["population_upper_bound"] != 103
    ):
        raise AssertionError("unexpected n=14 boundary theorem row")

    files = [
        census_path,
        HERE / "enumerate_all_low_slack_belts.py",
        HERE / "enumerate_minimum_belts.py",
        LOWER_WITNESS,
        RING_CERTIFICATE,
        PROJECT
        / "certificates"
        / "upper_bounds"
        / "depth4_boundary_census.json",
    ]
    result = {
        "schema": "connected-still-life-n14-closure-certificate-v1",
        "claim": "C(14)=102",
        "lower_bound": {
            "population": 102,
            "full_exterior_ring_verified": True,
            "eight_connected": True,
            "block_free": True,
            "wastage": lower_wastage,
            "witness_sha256": sha256(LOWER_WITNESS),
        },
        "upper_and_exclusion": {
            "depth4_population_upper": 103,
            "population_103_total_wastage": 36,
            "abstract_cycles_mod_rotation": 2664,
            "all_physical_belts_charge_at_most_36": 261225,
            "stable_population_103_completions": 224,
            "connected_population_103_completions": 0,
            "component_size_histogram": census[
                "stable_completion_component_size_histogram"
            ],
            "stable_grid_digest_sha256": census[
                "stable_completion_grid_digest_sha256"
            ],
        },
        "proof_logic": [
            (
                "A connected still life with more than four cells contains "
                "no live 2x2 block, since such a block is an isolated "
                "8-connected component."
            ),
            (
                "The Chu--Stuckey identity gives total wastage "
                "2*n^2+4*n-4*population=36 at n=14, population 103."
            ),
            (
                "All local wastage terms are nonnegative, so the physical "
                "depth-four boundary belt of such a board has charge <=36."
            ),
            (
                "The complete block-free boundary language enumerates all "
                "2,664 abstract cycle orbits and all 261,225 physical "
                "low-slack belts admitted by that charge budget."
            ),
            (
                "Exact completion of each remaining 4x4 centre produces "
                "224 stable population-103 boards, all disconnected."
            ),
            (
                "The independently verified connected 102 witness supplies "
                "the matching lower bound, hence C(14)=102."
            ),
        ],
        "sample_rechecks": sample_results,
        "file_sha256": {
            str(path.relative_to(PROJECT)): sha256(path) for path in files
        },
        "record_sha256_excluding_this_field": None,
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["record_sha256_excluding_this_field"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = verify(args.census, args.output)
    print(
        "VERIFIED",
        result["claim"],
        result["record_sha256_excluding_this_field"],
    )


if __name__ == "__main__":
    main()
