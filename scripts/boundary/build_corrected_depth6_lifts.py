#!/usr/bin/env python3
"""Test geometrically correct depth-six lifts of all n=40 equality cycles."""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import product
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CERTIFICATES = ROOT / "certificates" / "upper_bounds"
ORBITS = CERTIFICATES / "residue0_equality_orbits_n40.json"
DECOMPOSITION = CERTIFICATES / "residue0_arc_decomposition_n40.json"
OUTPUT = CERTIFICATES / "corrected_depth6_equality_lifts.json"

import depth4_boundary_census as kernel  # noqa: E402


State = tuple[int, int]


def configure_depth6() -> None:
    kernel.CHARGED_DEPTH = 6
    kernel.MASK_BITS = 7
    kernel.MASK_LIMIT = 128
    kernel.PATCH_SIZE = 7


def mask_from_row(row: str) -> int:
    return sum(
        (character == "1") << column
        for column, character in enumerate(row)
    )


def column_mask(rows: Sequence[int], column: int, height: int) -> int:
    return sum(
        ((rows[row] >> column) & 1) << row
        for row in range(height)
    )


def full_corner_valid(rows: Sequence[int]) -> bool:
    if len(rows) != 7:
        return False
    if not kernel.north_exterior_valid(rows[0]):
        return False
    if any(
        kernel.rows_have_block(rows[index], rows[index + 1])
        for index in range(6)
    ):
        return False
    return all(
        kernel.completed_center_row_valid(rows, center)
        for center in range(6)
    )


def corner_extensions(
    previous: dict[str, Any],
    following: dict[str, Any],
) -> list[dict[str, Any]]:
    """Lift one depth-five corner between two supported side contexts."""
    base_rows = [
        mask_from_row(row)
        for row in previous["corner_representative_patch"]
    ]
    if len(base_rows) != 6:
        raise AssertionError("expected a 6x6 depth-five corner")
    incoming = tuple(previous["corner_incoming"])
    base_outgoing = (
        column_mask(base_rows, 4, 6),
        column_mask(base_rows, 5, 6),
    )
    last_edges = previous["path_support"]["position_edges"]["30"]
    first_edges = following["path_support"]["position_edges"]["1"]
    result: dict[tuple[State, State], dict[str, Any]] = {}
    for last_edge, first_edge, diagonal in product(
        last_edges, first_edges, (0, 1)
    ):
        last_left, last_middle, last_right, last_weight = last_edge
        first_left, first_middle, first_right, first_weight = first_edge
        if (last_middle, last_right) != incoming:
            continue
        if (first_left, first_middle) != base_outgoing:
            continue
        rows = [
            base_rows[row]
            | (((first_right >> row) & 1) << 6)
            for row in range(6)
        ]
        rows.append(last_left | (diagonal << 6))
        if not full_corner_valid(rows):
            continue
        if kernel.chu_wastage(
            kernel.patch_pattern(rows, 5, 5)
        ) != 0:
            continue
        cost = kernel.patch_cost(rows)
        expected = (
            int(previous["corner_cost"])
            + int(last_weight)
            + int(first_weight)
        )
        if cost != expected:
            continue
        incoming6, outgoing6 = kernel.corner_states(rows)
        key = (incoming6, outgoing6)
        candidate = {
            "incoming": list(incoming6),
            "outgoing": list(outgoing6),
            "cost": cost,
            "last_depth5_edge": last_edge,
            "first_depth5_edge": first_edge,
            "diagonal_halo_bit": diagonal,
            "patch": kernel.render_rows(rows),
        }
        incumbent = result.get(key)
        if incumbent is None or json.dumps(
            candidate, sort_keys=True
        ) < json.dumps(incumbent, sort_keys=True):
            result[key] = candidate
    return [result[key] for key in sorted(result)]


def lifted_transition_rows(
    depth5_edges: Iterable[Sequence[int]],
) -> list[tuple[State, State, int]]:
    lifted: set[tuple[State, State, int]] = set()
    for left5, middle5, right5, weight5 in depth5_edges:
        for high_left, high_middle, high_right in product(
            (0, 1), repeat=3
        ):
            left = left5 | (high_left << 6)
            middle = middle5 | (high_middle << 6)
            right = right5 | (high_right << 6)
            if not kernel.transition_valid(left, middle, right):
                continue
            if kernel.chu_wastage(
                kernel.local_pattern(left, middle, right, 6)
            ) != 0:
                continue
            weight6 = kernel.transition_weight(left, middle, right)
            if weight6 != weight5:
                continue
            lifted.add(((left, middle), (middle, right), weight6))
    return sorted(lifted)


def straight_lift_relation(
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    position_edges = context["path_support"]["position_edges"]
    relations: dict[
        tuple[State, State], tuple[int, list[tuple[State, State, int]]]
    ] = {}
    current: dict[
        tuple[State, State], tuple[int, list[tuple[State, State, int]]]
    ] = {}
    for transition in lifted_transition_rows(position_edges["2"]):
        source, target, weight = transition
        current[(source, target)] = (weight, [transition])
    for step in range(3, 30):
        lifted = lifted_transition_rows(position_edges[str(step)])
        following: dict[
            tuple[State, State],
            tuple[int, list[tuple[State, State, int]]],
        ] = {}
        outgoing: dict[State, list[tuple[State, int, Any]]] = defaultdict(list)
        for source, target, weight in lifted:
            outgoing[source].append((target, weight, (source, target, weight)))
        for (start, middle), (cost, path) in current.items():
            for target, weight, transition in outgoing.get(middle, []):
                key = (start, target)
                candidate = (cost + weight, [*path, transition])
                incumbent = following.get(key)
                if incumbent is None or candidate < incumbent:
                    following[key] = candidate
        current = following
        if not current:
            break
    relations.update(current)
    return [
        {
            "start": list(start),
            "end": list(end),
            "cost": cost,
            "representative_path": [
                {
                    "source": list(source),
                    "target": list(target),
                    "weight": weight,
                }
                for source, target, weight in path
            ],
        }
        for (start, end), (cost, path) in sorted(relations.items())
    ]


def compose_macro_relation(
    straight: list[dict[str, Any]],
    corners: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    corners_by_incoming: dict[State, list[dict[str, Any]]] = defaultdict(list)
    for corner in corners:
        corners_by_incoming[tuple(corner["incoming"])].append(corner)
    result: dict[tuple[State, State], dict[str, Any]] = {}
    for path in straight:
        start = tuple(path["start"])
        end = tuple(path["end"])
        for corner in corners_by_incoming.get(end, []):
            following = tuple(corner["outgoing"])
            candidate = {
                "start": list(start),
                "following": list(following),
                "cost": int(path["cost"]) + int(corner["cost"]),
                "path": path,
                "corner": corner,
            }
            key = (start, following)
            incumbent = result.get(key)
            if incumbent is None or (
                candidate["cost"],
                json.dumps(candidate, sort_keys=True),
            ) < (
                incumbent["cost"],
                json.dumps(incumbent, sort_keys=True),
            ):
                result[key] = candidate
    return [result[key] for key in sorted(result)]


def has_closed_four_macro_walk(
    relations: Sequence[list[dict[str, Any]]],
) -> tuple[bool, list[dict[str, Any]] | None]:
    adjacency = []
    for relation in relations:
        by_start: dict[State, list[dict[str, Any]]] = defaultdict(list)
        for row in relation:
            by_start[tuple(row["start"])].append(row)
        adjacency.append(by_start)
    for first in relations[0]:
        initial = tuple(first["start"])
        current = tuple(first["following"])
        for second in adjacency[1].get(current, []):
            current2 = tuple(second["following"])
            for third in adjacency[2].get(current2, []):
                current3 = tuple(third["following"])
                for fourth in adjacency[3].get(current3, []):
                    if tuple(fourth["following"]) == initial:
                        return True, [first, second, third, fourth]
    return False, None


def canonical_cycles(orbit: dict[str, Any]) -> list[list[int]]:
    arcs = {
        tuple(arc)
        for arc in orbit["complete_equality_support"][
            "arc_state_indices"
        ]
    }
    fixed = (805, 784, 861)
    xs = sorted(
        first
        for first, second in arcs
        if second == fixed[0] and (fixed[2], first) in arcs
        and first != fixed[1]
    )
    cycles = [[x, *fixed] for x in xs]
    if len(cycles) != 14:
        raise AssertionError("unexpected equality-cycle classification")
    return cycles


def build() -> dict[str, Any]:
    configure_depth6()
    orbit = json.loads(ORBITS.read_text(encoding="utf-8"))
    decomposition = json.loads(
        DECOMPOSITION.read_text(encoding="utf-8")
    )
    contexts = decomposition["side_arc_path_contexts"]
    contexts_by_arc: dict[
        tuple[int, int], list[dict[str, Any]]
    ] = defaultdict(list)
    for context_index, context in enumerate(contexts):
        enriched = {**context, "context_index": context_index}
        contexts_by_arc[
            (context["source_index"], context["target_index"])
        ].append(enriched)

    straight_cache = {
        context["context_index"]: straight_lift_relation(context)
        for context in (
            {row["context_index"]: row for rows in contexts_by_arc.values()
             for row in rows}.values()
        )
    }
    corner_cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
    cycle_rows = []
    total_context_combinations = 0
    viable_context_combinations = 0
    equality_lift_witness = None
    for cycle in canonical_cycles(orbit):
        arcs = [
            (cycle[index], cycle[(index + 1) % 4])
            for index in range(4)
        ]
        combinations = list(
            product(*(contexts_by_arc[arc] for arc in arcs))
        )
        total_context_combinations += len(combinations)
        viable = 0
        for combination in combinations:
            corner_relations = []
            macro_relations = []
            for index in range(4):
                previous = combination[index]
                following = combination[(index + 1) % 4]
                key = (
                    previous["context_index"],
                    following["context_index"],
                )
                if key not in corner_cache:
                    corner_cache[key] = corner_extensions(
                        previous, following
                    )
                corners = corner_cache[key]
                corner_relations.append(corners)
                macro_relations.append(
                    compose_macro_relation(
                        straight_cache[previous["context_index"]],
                        corners,
                    )
                )
            exists, witness = has_closed_four_macro_walk(
                macro_relations
            )
            if exists:
                viable += 1
                viable_context_combinations += 1
                if equality_lift_witness is None:
                    equality_lift_witness = {
                        "depth5_cycle": cycle,
                        "context_indices": [
                            row["context_index"]
                            for row in combination
                        ],
                        "macro_walk": witness,
                    }
        cycle_rows.append(
            {
                "depth5_cycle": cycle,
                "context_combination_count": len(combinations),
                "viable_depth6_context_combination_count": viable,
            }
        )

    straight_summary = {
        str(index): {
            "relation_count": len(rows),
            "sha256": hashlib.sha256(
                json.dumps(
                    rows, sort_keys=True, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest(),
        }
        for index, rows in sorted(straight_cache.items())
    }
    corner_summary = {
        f"{first},{second}": {
            "relation_count": len(rows),
            "sha256": hashlib.sha256(
                json.dumps(
                    rows, sort_keys=True, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest(),
        }
        for (first, second), rows in sorted(corner_cache.items())
    }
    return {
        "schema": "corrected-depth6-residue0-equality-lift-v1",
        "n": 40,
        "depth5_equality_cycle_count": 14,
        "side_arc_path_context_count": len(contexts),
        "straight_lift_relations": straight_summary,
        "corner_lift_relations": corner_summary,
        "cycle_tests": cycle_rows,
        "total_context_combinations": total_context_combinations,
        "viable_context_combinations": viable_context_combinations,
        "zero_additional_wastage_equality_lift_exists": (
            equality_lift_witness is not None
        ),
        "first_equality_lift_witness": equality_lift_witness,
        "geometry": (
            "A depth-six corner is a depth-five 6x6 corner, the final "
            "depth-five edge transition of the preceding side, the first "
            "transition of the following side, and one new diagonal halo "
            "bit. Only charged cell (5,5) is newly added at the corner."
        ),
        "claim_scope": (
            "Exact corrected lift test for every depth-five equality cycle "
            "at n=40. No all-n recurrence is claimed."
        ),
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
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored corrected lift record differs")
        print("VERIFIED", args.output)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "depth5_equality_cycle_count": record[
                    "depth5_equality_cycle_count"
                ],
                "side_arc_path_context_count": record[
                    "side_arc_path_context_count"
                ],
                "total_context_combinations": record[
                    "total_context_combinations"
                ],
                "viable_context_combinations": record[
                    "viable_context_combinations"
                ],
                "zero_additional_wastage_equality_lift_exists": record[
                    "zero_additional_wastage_equality_lift_exists"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
