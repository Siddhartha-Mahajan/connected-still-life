#!/usr/bin/env python3
"""Certify the four-corner block-free boundary-ring relaxation.

The independent-side relaxation treats each side independently and discards three columns at both
ends.  This script restores those discarded corners exactly.

For the canonical north-west corner, enumerate every 4 by 4 binary patch.
The outer 3 by 3 square is charged; the fourth row and column supply every
neighbour needed by the charged cells and the two incident edge states.
Each accepted patch:

* is stable on the charged 3 by 3 square with dead north/west exterior;
* creates no birth in the three charged north/west exterior positions;
* contains no live 2 by 2 block;
* has exact Chu--Stuckey interior plus exterior wastage; and
* maps the incoming clockwise edge state to the outgoing edge state.

Let A_L be the exact min-plus path matrix for L=n-6 transitions of the
Phase-012 block-free edge graph, and K the corner relation.  Then

    T_L = A_L K

maps one corner output to the next.  The exact boundary-ring relaxation is
the minimum diagonal entry of T_L^4.

This charges every cell in the depth-three boundary belt and all 4n
orthogonal exterior cells exactly once.  Uncharged interior wastage is
nonnegative, so the result is a rigorous lower bound on total wastage and
hence an upper bound on connected population.  No full-board optimization is
performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any, Sequence

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

from certify_depth3_edge import (  # noqa: E402
    State,
    build_graph,
    chu_wastage,
    has_block_between,
    is_stable_pattern,
)


DEFAULT_OUTPUT = (
    ROOT / "certificates" / "upper_bounds" / "depth3_ring_certificate.json"
)
PATCH_SIZE = 4
CHARGED_SIZE = 3
INF = 10**7


Grid = list[list[int]]


def patch_from_bits(value: int) -> Grid:
    return [
        [
            (value >> (row * PATCH_SIZE + column)) & 1
            for column in range(PATCH_SIZE)
        ]
        for row in range(PATCH_SIZE)
    ]


def cell(grid: Sequence[Sequence[int]], row: int, column: int) -> int:
    if row < 0 or column < 0:
        return 0
    return grid[row][column]


def local_pattern(grid: Grid, row: int, column: int) -> tuple[int, ...]:
    return tuple(
        cell(grid, row + dr, column + dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
    )


def mask_column(grid: Grid, column: int) -> int:
    return sum(grid[depth][column] << depth for depth in range(PATCH_SIZE))


def mask_row(grid: Grid, row: int) -> int:
    return sum(grid[row][depth] << depth for depth in range(PATCH_SIZE))


def corner_valid(grid: Grid) -> bool:
    if not all(
        is_stable_pattern(local_pattern(grid, row, column))
        for row in range(CHARGED_SIZE)
        for column in range(CHARGED_SIZE)
    ):
        return False

    # The three exterior cells immediately north and west of the charged
    # corner would be born exactly when their three adjacent edge cells live.
    for position in range(CHARGED_SIZE):
        north_neighbours = sum(
            grid[0][column]
            for column in range(max(0, position - 1), position + 2)
        )
        west_neighbours = sum(
            grid[row][0]
            for row in range(max(0, position - 1), position + 2)
        )
        if north_neighbours == 3 or west_neighbours == 3:
            return False

    row_masks = [mask_row(grid, row) for row in range(PATCH_SIZE)]
    return not any(
        has_block_between(row_masks[row], row_masks[row + 1])
        for row in range(PATCH_SIZE - 1)
    )


def corner_cost(grid: Grid) -> int:
    interior = sum(
        chu_wastage(local_pattern(grid, row, column))
        for row in range(CHARGED_SIZE)
        for column in range(CHARGED_SIZE)
    )
    exterior = sum(1 - grid[0][column] for column in range(CHARGED_SIZE))
    exterior += sum(1 - grid[row][0] for row in range(CHARGED_SIZE))
    return interior + exterior


def corner_states(grid: Grid) -> tuple[State, State]:
    """Return incoming-left and outgoing-top clockwise edge states.

    The clockwise left edge approaches the north-west corner from below, so
    its final masks are rows 3 then 2.  The clockwise top edge leaves toward
    the right with initial masks columns 2 then 3.
    """

    incoming = (mask_row(grid, 3), mask_row(grid, 2))
    outgoing = (mask_column(grid, 2), mask_column(grid, 3))
    return incoming, outgoing


def build_corner_relation(
    valid_edge_states: set[State],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    best: dict[tuple[State, State], tuple[int, Grid]] = {}
    valid_patch_count = 0
    extendible_patch_count = 0
    for value in range(1 << (PATCH_SIZE * PATCH_SIZE)):
        grid = patch_from_bits(value)
        if not corner_valid(grid):
            continue
        valid_patch_count += 1
        incoming, outgoing = corner_states(grid)
        if incoming not in valid_edge_states or outgoing not in valid_edge_states:
            continue
        extendible_patch_count += 1
        cost = corner_cost(grid)
        key = (incoming, outgoing)
        incumbent = best.get(key)
        rendered = ["".join(map(str, row)) for row in grid]
        if incumbent is None or (cost, rendered) < (
            incumbent[0],
            ["".join(map(str, row)) for row in incumbent[1]],
        ):
            best[key] = (cost, grid)

    relation = []
    for (incoming, outgoing), (cost, grid) in sorted(best.items()):
        relation.append(
            {
                "incoming": list(incoming),
                "outgoing": list(outgoing),
                "cost": cost,
                "representative_patch": [
                    "".join(map(str, row)) for row in grid
                ],
            }
        )
    statistics = {
        "enumerated_patch_count": 1 << (PATCH_SIZE * PATCH_SIZE),
        "valid_patch_count": valid_patch_count,
        "edge_extendible_patch_count": extendible_patch_count,
        "distinct_corner_transition_count": len(relation),
        "minimum_corner_cost": min(row["cost"] for row in relation),
        "maximum_corner_cost": max(row["cost"] for row in relation),
    }
    return relation, statistics


def edge_path_matrices(
    nodes: list[State],
    edges: Sequence[Any],
    lengths: set[int],
    *,
    period_search_limit: int = 512,
) -> tuple[dict[int, np.ndarray], dict[str, Any]]:
    index = {state: position for position, state in enumerate(nodes)}
    size = len(nodes)
    distance = np.full((size, size), INF, dtype=np.int32)
    np.fill_diagonal(distance, 0)
    result = {0: distance.copy()} if 0 in lengths else {}
    history: deque[tuple[int, np.ndarray]] = deque(
        [(0, distance.copy())], maxlen=9
    )
    period_certificate: dict[str, Any] | None = None
    last_required = max(lengths)
    for length in range(1, max(last_required, period_search_limit) + 1):
        following = np.full_like(distance, INF)
        for edge in edges:
            source = index[edge.source]
            target = index[edge.target]
            np.minimum(
                following[:, target],
                distance[:, source] + edge.weight,
                out=following[:, target],
            )
        distance = following
        if length in lengths:
            result[length] = distance.copy()
        history.append((length, distance.copy()))
        if len(history) == 9 and period_certificate is None:
            old_length, old = history[0]
            old_finite = old < INF
            new_finite = distance < INF
            periodic = np.array_equal(old_finite, new_finite) and np.array_equal(
                distance[new_finite], old[new_finite] + 3
            )
            if periodic:
                period_certificate = {
                    "start_length": old_length,
                    "period": 8,
                    "weight_increment": 3,
                    "finite_entry_count": int(new_finite.sum()),
                    "matrix_sha256_at_start": hashlib.sha256(
                        old.tobytes()
                    ).hexdigest(),
                    "matrix_sha256_after_period": hashlib.sha256(
                        distance.tobytes()
                    ).hexdigest(),
                    "induction": (
                        "A[L+1]=A[L] min-plus E; therefore one full "
                        "matrix equality A[M+8]=A[M]+3 implies the same "
                        "equality for every L>=M"
                    ),
                }
        if length >= last_required and period_certificate is not None:
            break
    if period_certificate is None:
        raise AssertionError(
            f"no full edge-matrix period found through {period_search_limit}"
        )
    return result, period_certificate


def side_to_side_matrix(
    edge_paths: np.ndarray,
    relation: list[dict[str, Any]],
    node_index: dict[State, int],
) -> np.ndarray:
    size = len(node_index)
    result = np.full((size, size), INF, dtype=np.int32)
    for corner in relation:
        incoming = node_index[tuple(corner["incoming"])]
        outgoing = node_index[tuple(corner["outgoing"])]
        np.minimum(
            result[:, outgoing],
            edge_paths[:, incoming] + int(corner["cost"]),
            out=result[:, outgoing],
        )
    return result


def four_side_minimum(matrix: np.ndarray) -> tuple[int, tuple[int, int]]:
    size = matrix.shape[0]
    square = np.full_like(matrix, INF)
    for middle in range(size):
        np.minimum(
            square,
            matrix[:, middle, None] + matrix[middle, None, :],
            out=square,
        )
    candidates = square + square.T
    flat = int(np.argmin(candidates))
    first, opposite = divmod(flat, size)
    return int(candidates[first, opposite]), (first, opposite)


def population_upper(n: int, wastage_lower: int) -> int:
    return (2 * n * n + 4 * n - wastage_lower) // 4


def certify(n_min: int, n_max: int) -> dict[str, Any]:
    if n_min < 6 or n_max < n_min:
        raise ValueError("require 6 <= n_min <= n_max")
    nodes, edges = build_graph(blockfree=True)
    relation, corner_statistics = build_corner_relation(set(nodes))
    node_index = {state: position for position, state in enumerate(nodes)}
    lengths = {n - 6 for n in range(n_min, n_max + 1)}
    path_matrices, edge_period = edge_path_matrices(nodes, edges, lengths)

    rows = []
    for n in range(n_min, n_max + 1):
        length = n - 6
        transfer = side_to_side_matrix(
            path_matrices[length], relation, node_index
        )
        wastage, minimizer = four_side_minimum(transfer)
        rows.append(
            {
                "n": n,
                "edge_length": length,
                "boundary_wastage_lower_bound": wastage,
                "connected_population_upper_bound": population_upper(
                    n, wastage
                ),
                "two_opposite_state_minimizer_indices": list(minimizer),
                "two_opposite_state_minimizer": [
                    list(nodes[index]) for index in minimizer
                ],
            }
        )

    recurrences = []
    by_n = {row["n"]: row for row in rows}
    for n in range(n_min, n_max - 7):
        left = by_n[n]
        right = by_n[n + 8]
        recurrences.append(
            {
                "n": n,
                "wastage_increment": (
                    right["boundary_wastage_lower_bound"]
                    - left["boundary_wastage_lower_bound"]
                ),
                "population_upper_increment": (
                    right["connected_population_upper_bound"]
                    - left["connected_population_upper_bound"]
                ),
            }
        )

    return {
        "schema": "blockfree-four-corner-ring-certificate-v1",
        "status": "rigorous boundary relaxation",
        "charged_region": (
            "depth-three boundary belt plus all 4n orthogonal exterior cells"
        ),
        "edge_graph": {
            "state_count": len(nodes),
            "transition_count": len(edges),
            "states": [list(state) for state in nodes],
            "full_min_plus_matrix_period": edge_period,
        },
        "corner": {
            **corner_statistics,
            "relation": relation,
        },
        "range": {"n_min": n_min, "n_max": n_max},
        "rows": rows,
        "recurrence_differences": recurrences,
        "eventual_ring_recurrence": {
            "first_n": edge_period["start_length"] + 6,
            "wastage": "B(n+8)=B(n)+12",
            "population_upper": "U(n+8)=U(n)+8*n+37",
            "proof": (
                "Each of four side matrices gains 3 under n->n+8; "
                "corner relation K is fixed, so every four-side closed "
                "walk gains exactly 12"
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-min", type=int, default=10)
    parser.add_argument("--n-max", type=int, default=64)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = certify(args.n_min, args.n_max)
    if args.verify:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored corner-ring certificate differs")
        print("VERIFIED", args.output)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record["corner"] | {"relation": "omitted"}, indent=2))
    print("n wastage_lower population_upper")
    for row in record["rows"]:
        print(
            row["n"],
            row["boundary_wastage_lower_bound"],
            row["connected_population_upper_bound"],
        )


if __name__ == "__main__":
    main()
