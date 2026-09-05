#!/usr/bin/env python3
"""Test every zero-wastage depth-six lift of an n=17 equality boundary.

This is a finite boundary-language certificate.  It deliberately avoids a
full 17x17 board search.  Every physical depth-five corner patch tied at a
supported equality mapping is retained, including ties discarded by the
ordinary min-cost corner transfer.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from itertools import product
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BOUNDARY = ROOT / "scripts" / "boundary"
CERTIFICATES = ROOT / "certificates" / "exact_closures" / "n17"
ORBIT = CERTIFICATES / "depth5_equality_orbits.json"
OUTPUT = CERTIFICATES / "depth6_equality_lift.json"
N = 17
TARGET = 38
INF = 30_000
State = tuple[int, int]

for dependency in (BOUNDARY,):
    if str(dependency) not in sys.path:
        sys.path.insert(0, str(dependency))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from depth6_zero_lift_census import build_filtered_edge_graph  # noqa: E402
from certify_depth5_ring import anchored_four_cycle_test, path_matrix  # noqa: E402


def configure_depth5() -> None:
    kernel.CHARGED_DEPTH = 5
    kernel.MASK_BITS = 6
    kernel.MASK_LIMIT = 64
    kernel.PATCH_SIZE = 6


def configure_depth6() -> None:
    kernel.CHARGED_DEPTH = 6
    kernel.MASK_BITS = 7
    kernel.MASK_LIMIT = 128
    kernel.PATCH_SIZE = 7


def output_states(
    relation: Sequence[dict[str, Any]],
) -> list[State]:
    return sorted({tuple(row["outgoing"]) for row in relation})


def enumerate_full_depth5_corners(
    valid_states: set[State],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Enumerate all physical extendible 6x6 corners, including cost ties."""

    patches: list[dict[str, Any]] = []
    dfs_nodes = Counter()
    valid_patch_count = 0
    extendible_patch_count = 0

    def visit(rows: list[int]) -> None:
        nonlocal valid_patch_count
        nonlocal extendible_patch_count
        dfs_nodes[len(rows)] += 1
        if len(rows) == kernel.PATCH_SIZE:
            valid_patch_count += 1
            incoming, outgoing = kernel.corner_states(rows)
            if incoming not in valid_states or outgoing not in valid_states:
                return
            extendible_patch_count += 1
            patches.append(
                {
                    "incoming": incoming,
                    "outgoing": outgoing,
                    "cost": kernel.patch_cost(rows),
                    "patch": tuple(kernel.render_rows(rows)),
                }
            )
            return
        for following in range(kernel.MASK_LIMIT):
            if not rows and not kernel.north_exterior_valid(following):
                continue
            if rows and kernel.rows_have_block(rows[-1], following):
                continue
            candidate = [*rows, following]
            if len(candidate) >= 2:
                center_row = len(candidate) - 2
                if not kernel.completed_center_row_valid(
                    candidate, center_row
                ):
                    continue
            visit(candidate)

    visit([])
    patches.sort(
        key=lambda row: (
            row["outgoing"],
            row["incoming"],
            row["cost"],
            row["patch"],
        )
    )
    return patches, {
        "dfs_node_counts_by_completed_rows": {
            str(depth): count
            for depth, count in sorted(dfs_nodes.items())
        },
        "valid_patch_count": valid_patch_count,
        "edge_extendible_physical_patch_count": extendible_patch_count,
    }


def equality_mapping_keys(
    orbit: dict[str, Any],
    nodes: list[State],
    relation: list[dict[str, Any]],
    sources: list[State],
    paths: np.ndarray,
    transfer: np.ndarray,
) -> set[tuple[State, State, int]]:
    """All min-cost depth-five corner mappings used by a supported arc."""

    node_index = {state: index for index, state in enumerate(nodes)}
    relation_by_output: dict[State, list[dict[str, Any]]] = defaultdict(list)
    for corner in relation:
        relation_by_output[tuple(corner["outgoing"])].append(corner)
    keys: set[tuple[State, State, int]] = set()
    for first_index, second_index in orbit[
        "complete_equality_support"
    ]["arc_state_indices"]:
        outgoing = sources[second_index]
        side_cost = int(transfer[first_index, second_index])
        for corner in relation_by_output[outgoing]:
            incoming = tuple(corner["incoming"])
            corner_cost = int(corner["cost"])
            path_cost = int(paths[first_index, node_index[incoming]])
            if path_cost + corner_cost == side_cost:
                keys.add((incoming, outgoing, corner_cost))
    if not keys:
        raise AssertionError("equality support has no corner mappings")
    return keys


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


def full_depth6_corner_valid(rows: Sequence[int]) -> bool:
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


def edge_payload(edge: kernel.Edge) -> tuple[int, int, int, int]:
    return (*edge.source, edge.target[1], edge.weight)


def build_complete_depth6_corner_relation(
    equality_patches: Sequence[dict[str, Any]],
    depth5_edges: Sequence[kernel.Edge],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Lift all tied equality patches with a safe adjacent-edge overapprox."""

    incoming_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    outgoing_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    for edge in depth5_edges:
        incoming_edges[edge.target].append(edge)
        outgoing_edges[edge.source].append(edge)

    configure_depth6()
    best: dict[tuple[State, State], dict[str, Any]] = {}
    raw_extension_count = 0
    attempted_combination_count = 0
    patch_extension_histogram = Counter()
    for patch_index, mapping in enumerate(equality_patches):
        base_rows = [
            mask_from_row(row) for row in mapping["patch"]
        ]
        incoming = tuple(mapping["incoming"])
        outgoing = tuple(mapping["outgoing"])
        base_outgoing = (
            column_mask(base_rows, 4, 6),
            column_mask(base_rows, 5, 6),
        )
        if base_outgoing != outgoing:
            raise AssertionError("stored depth-five corner output mismatch")
        extension_count = 0
        for last_edge, first_edge, diagonal in product(
            incoming_edges[incoming],
            outgoing_edges[outgoing],
            (0, 1),
        ):
            attempted_combination_count += 1
            last_left, last_middle, last_right, last_weight = edge_payload(
                last_edge
            )
            first_left, first_middle, first_right, first_weight = edge_payload(
                first_edge
            )
            if (last_middle, last_right) != incoming:
                raise AssertionError("bad incoming-edge index")
            if (first_left, first_middle) != outgoing:
                raise AssertionError("bad outgoing-edge index")
            rows = [
                base_rows[row]
                | (((first_right >> row) & 1) << 6)
                for row in range(6)
            ]
            rows.append(last_left | (diagonal << 6))
            if not full_depth6_corner_valid(rows):
                continue
            if kernel.chu_wastage(
                kernel.patch_pattern(rows, 5, 5)
            ) != 0:
                continue
            cost = kernel.patch_cost(rows)
            expected = (
                int(mapping["cost"]) + last_weight + first_weight
            )
            if cost != expected:
                continue
            incoming6, outgoing6 = kernel.corner_states(rows)
            candidate = {
                "incoming": list(incoming6),
                "outgoing": list(outgoing6),
                "cost": cost,
                "representative_patch": kernel.render_rows(rows),
                "depth5_patch_index": patch_index,
                "last_depth5_edge": list(edge_payload(last_edge)),
                "first_depth5_edge": list(edge_payload(first_edge)),
                "diagonal_halo_bit": diagonal,
            }
            key = (incoming6, outgoing6)
            incumbent = best.get(key)
            if incumbent is None or (
                cost,
                json.dumps(candidate, sort_keys=True),
            ) < (
                int(incumbent["cost"]),
                json.dumps(incumbent, sort_keys=True),
            ):
                best[key] = candidate
            raw_extension_count += 1
            extension_count += 1
        patch_extension_histogram[extension_count] += 1

    relation = [
        {
            "incoming": row["incoming"],
            "outgoing": row["outgoing"],
            "cost": row["cost"],
            "representative_patch": row["representative_patch"],
        }
        for _key, row in sorted(best.items())
    ]
    return relation, {
        "equality_physical_patch_count": len(equality_patches),
        "attempted_adjacent_edge_and_diagonal_combinations": (
            attempted_combination_count
        ),
        "raw_valid_depth6_extension_count": raw_extension_count,
        "minimum_depth6_corner_mapping_count": len(relation),
        "physical_patch_valid_extension_count_histogram": {
            str(count): patches
            for count, patches in sorted(
                patch_extension_histogram.items()
            )
        },
        "relation_sha256": hashlib.sha256(
            json.dumps(
                relation, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
        ).hexdigest(),
    }


def depth6_transfer(
    relation: list[dict[str, Any]],
    edge_length: int,
) -> tuple[
    list[State],
    list[kernel.Edge],
    list[State],
    np.ndarray,
    np.ndarray,
]:
    configure_depth6()
    nodes, edges = build_filtered_edge_graph()
    sources = output_states(relation)
    paths = path_matrix(nodes, edges, sources, edge_length)
    transfer = side_transfer(paths, relation, nodes, sources)
    return nodes, edges, sources, paths, transfer


def build() -> dict[str, Any]:
    orbit = json.loads(ORBIT.read_text(encoding="utf-8"))
    if orbit["n"] != N or orbit["four_side_target"] != TARGET:
        raise ValueError("wrong equality-orbit input")

    configure_depth5()
    nodes5, edges5 = kernel.build_edge_graph()
    relation5, relation5_statistics = kernel.build_corner_relation(
        set(nodes5)
    )
    sources5 = output_states(relation5)
    paths5 = path_matrix(nodes5, edges5, sources5, N - 10)
    transfer5 = side_transfer(
        paths5, relation5, nodes5, sources5
    )
    if hashlib.sha256(transfer5.tobytes()).hexdigest() != orbit[
        "side_transfer"
    ]["sha256"]:
        raise AssertionError("depth-five transfer does not match orbit input")

    mapping_keys = equality_mapping_keys(
        orbit, nodes5, relation5, sources5, paths5, transfer5
    )
    all_patches, full_corner_statistics = enumerate_full_depth5_corners(
        set(nodes5)
    )
    equality_patches = [
        row
        for row in all_patches
        if (row["incoming"], row["outgoing"], row["cost"])
        in mapping_keys
    ]
    represented_keys = {
        (row["incoming"], row["outgoing"], row["cost"])
        for row in equality_patches
    }
    if represented_keys != mapping_keys:
        raise AssertionError("a supported equality mapping has no full patch")

    relation6, lift_statistics = (
        build_complete_depth6_corner_relation(
            equality_patches, edges5
        )
    )
    if not relation6:
        anchored = {
            "cycle_at_or_below_target_exists": False,
            "reason": "no valid zero-new-wastage depth-six corner extension",
        }
        nodes6: list[State] = []
        edges6: list[kernel.Edge] = []
        sources6: list[State] = []
        paths6 = np.zeros((0, 0), dtype=np.int16)
        transfer6 = np.zeros((0, 0), dtype=np.int16)
    else:
        nodes6, edges6, sources6, paths6, transfer6 = depth6_transfer(
            relation6, N - 12
        )
        anchored = anchored_four_cycle_test(transfer6, TARGET)

    equality_lift_exists = bool(
        anchored["cycle_at_or_below_target_exists"]
    )
    return {
        "schema": "n17-complete-depth6-equality-lift-v1",
        "n": N,
        "target_population": 152,
        "target_total_wastage": TARGET,
        "method": (
            "Complete depth-five equality-arc support; every tied physical "
            "6x6 corner patch at a supported minimum mapping; safe all-edge "
            "adjacency overapproximation; exact zero-new-wastage depth-six "
            "straight graph; anchored four-side min-plus exclusion."
        ),
        "depth5": {
            "edge_length": N - 10,
            "edge_state_count": len(nodes5),
            "edge_transition_count": len(edges5),
            "corner_relation_statistics": relation5_statistics,
            "equality_state_count": orbit[
                "complete_equality_support"
            ]["state_count"],
            "equality_arc_count": orbit[
                "complete_equality_support"
            ]["arc_count"],
            "equality_mapping_key_count": len(mapping_keys),
            "equality_mapping_keys_sha256": hashlib.sha256(
                json.dumps(
                    [
                        [*incoming, *outgoing, cost]
                        for incoming, outgoing, cost in sorted(mapping_keys)
                    ],
                    separators=(",", ":"),
                ).encode("ascii")
            ).hexdigest(),
            "full_physical_corner_census": full_corner_statistics,
            "equality_physical_patch_count": len(equality_patches),
            "equality_physical_patches_sha256": hashlib.sha256(
                json.dumps(
                    equality_patches, sort_keys=True, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest(),
        },
        "depth6": {
            "edge_length": N - 12,
            "edge_state_count": len(nodes6),
            "edge_transition_count": len(edges6),
            "corner_output_state_count": len(sources6),
            "corner_lift_statistics": lift_statistics,
            "restricted_path_finite_count": int(
                np.count_nonzero(paths6 < INF)
            ),
            "restricted_path_sha256": hashlib.sha256(
                paths6.tobytes()
            ).hexdigest(),
            "side_transfer_finite_count": int(
                np.count_nonzero(transfer6 < INF)
            ),
            "side_transfer_sha256": hashlib.sha256(
                transfer6.tobytes()
            ).hexdigest(),
            "anchored_four_cycle_test": anchored,
            "zero_additional_wastage_equality_lift_exists": (
                equality_lift_exists
            ),
        },
        "consequence": {
            "depth6_boundary_wastage_strictly_exceeds_38": (
                not equality_lift_exists
            ),
            "population_152_excluded": not equality_lift_exists,
            "connected_optimum": (
                151 if not equality_lift_exists else None
            ),
            "logic": (
                "Any block-free board with total W=38 projects to a "
                "depth-five minimum ring and has zero added sixth-layer "
                "wastage. It must therefore occur in this safe lift "
                "language. If the language has no four-cycle of cost <=38, "
                "no such board exists."
            ),
        },
        "completeness_notes": [
            (
                "A connected still life with more than four cells cannot "
                "contain a live 2x2 block, so the block-free language is "
                "necessary at population 152."
            ),
            (
                "All tied physical depth-five corner patches are enumerated; "
                "the certificate does not rely on one representative patch "
                "per abstract mapping."
            ),
            (
                "All valid adjacent depth-five edges are allowed at every "
                "lifted corner, even when they do not belong to the same "
                "equality path. This enlarges the language and makes a "
                "negative result safe."
            ),
            (
                "The calculation is confined to fixed local boundary "
                "languages and a four-side transfer; it is not a full-board "
                "CP-SAT or brute-force search."
            ),
        ],
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
            raise SystemExit("stored n=17 depth-six lift differs")
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
                    "anchored_four_cycle_test": record["depth6"][
                        "anchored_four_cycle_test"
                    ],
                },
                "consequence": record["consequence"],
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
