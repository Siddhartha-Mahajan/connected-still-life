#!/usr/bin/env python3
"""Enumerate the exact depth-four block-free edge and corner languages."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence


HERE = Path(__file__).resolve().parent
LOCAL_WASTAGE_MODULE = HERE.parent / "local_wastage"
OUTPUT = HERE / "outputs" / "depth4_boundary_census.json"
if str(LOCAL_WASTAGE_MODULE) not in sys.path:
    sys.path.insert(0, str(LOCAL_WASTAGE_MODULE))

from certify_blockfree_edge import (  # noqa: E402
    chu_wastage,
    is_stable_pattern,
)


CHARGED_DEPTH = 4
MASK_BITS = CHARGED_DEPTH + 1
MASK_LIMIT = 1 << MASK_BITS
PATCH_SIZE = MASK_BITS
State = tuple[int, int]


@dataclass(frozen=True)
class Edge:
    source: State
    target: State
    weight: int


def bit(column: int, depth: int) -> int:
    return (column >> (depth - 1)) & 1 if depth >= 1 else 0


def local_pattern(
    left: int,
    middle: int,
    right: int,
    depth: int,
) -> tuple[int, ...]:
    return tuple(
        bit(column, row)
        for row in (depth - 1, depth, depth + 1)
        for column in (left, middle, right)
    )


def rows_have_block(first: int, second: int) -> bool:
    return bool(
        first
        & second
        & (first >> 1)
        & (second >> 1)
    )


def transition_valid(left: int, middle: int, right: int) -> bool:
    if bit(left, 1) + bit(middle, 1) + bit(right, 1) > 2:
        return False
    if rows_have_block(left, middle) or rows_have_block(middle, right):
        return False
    return all(
        is_stable_pattern(
            local_pattern(left, middle, right, depth)
        )
        for depth in range(1, CHARGED_DEPTH + 1)
    )


def transition_weight(left: int, middle: int, right: int) -> int:
    return (1 - bit(middle, 1)) + sum(
        chu_wastage(
            local_pattern(left, middle, right, depth)
        )
        for depth in range(1, CHARGED_DEPTH + 1)
    )


def build_edge_graph() -> tuple[list[State], list[Edge]]:
    edges = []
    for left in range(MASK_LIMIT):
        for middle in range(MASK_LIMIT):
            for right in range(MASK_LIMIT):
                if transition_valid(left, middle, right):
                    edges.append(
                        Edge(
                            (left, middle),
                            (middle, right),
                            transition_weight(left, middle, right),
                        )
                    )
    nodes = sorted(
        {edge.source for edge in edges}
        | {edge.target for edge in edges}
    )
    return nodes, edges


def row_cell(rows: Sequence[int], row: int, column: int) -> int:
    if row < 0 or column < 0:
        return 0
    return (rows[row] >> column) & 1


def patch_pattern(
    rows: Sequence[int],
    row: int,
    column: int,
) -> tuple[int, ...]:
    return tuple(
        row_cell(rows, row + dr, column + dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
    )


def north_exterior_valid(first_row: int) -> bool:
    return all(
        sum(
            (first_row >> column) & 1
            for column in range(
                max(0, position - 1),
                min(PATCH_SIZE, position + 2),
            )
        )
        != 3
        for position in range(CHARGED_DEPTH)
    )


def completed_center_row_valid(
    rows: Sequence[int],
    center_row: int,
) -> bool:
    if not all(
        is_stable_pattern(
            patch_pattern(rows, center_row, column)
        )
        for column in range(CHARGED_DEPTH)
    ):
        return False
    west_neighbours = sum(
        row_cell(rows, row, 0)
        for row in range(
            max(0, center_row - 1),
            min(len(rows), center_row + 2),
        )
    )
    return west_neighbours != 3


def patch_cost(rows: Sequence[int]) -> int:
    interior = sum(
        chu_wastage(patch_pattern(rows, row, column))
        for row in range(CHARGED_DEPTH)
        for column in range(CHARGED_DEPTH)
    )
    exterior = sum(
        1 - row_cell(rows, 0, column)
        for column in range(CHARGED_DEPTH)
    )
    exterior += sum(
        1 - row_cell(rows, row, 0)
        for row in range(CHARGED_DEPTH)
    )
    return interior + exterior


def column_mask(rows: Sequence[int], column: int) -> int:
    return sum(
        row_cell(rows, row, column) << row
        for row in range(PATCH_SIZE)
    )


def corner_states(rows: Sequence[int]) -> tuple[State, State]:
    incoming = (rows[CHARGED_DEPTH], rows[CHARGED_DEPTH - 1])
    outgoing = (
        column_mask(rows, CHARGED_DEPTH - 1),
        column_mask(rows, CHARGED_DEPTH),
    )
    return incoming, outgoing


def render_rows(rows: Sequence[int]) -> list[str]:
    return [
        "".join(
            "1" if (row >> column) & 1 else "0"
            for column in range(PATCH_SIZE)
        )
        for row in rows
    ]


def build_corner_relation(
    valid_states: set[State],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    best: dict[tuple[State, State], tuple[int, list[int]]] = {}
    valid_patch_count = 0
    extendible_patch_count = 0
    dfs_node_counts = Counter()
    pruned_block = 0
    pruned_stability_or_west_birth = 0

    def visit(rows: list[int]) -> None:
        nonlocal valid_patch_count
        nonlocal extendible_patch_count
        nonlocal pruned_block
        nonlocal pruned_stability_or_west_birth
        dfs_node_counts[len(rows)] += 1
        if len(rows) == PATCH_SIZE:
            valid_patch_count += 1
            incoming, outgoing = corner_states(rows)
            if (
                incoming not in valid_states
                or outgoing not in valid_states
            ):
                return
            extendible_patch_count += 1
            cost = patch_cost(rows)
            key = (incoming, outgoing)
            rendered = render_rows(rows)
            incumbent = best.get(key)
            if incumbent is None or (cost, rendered) < (
                incumbent[0],
                render_rows(incumbent[1]),
            ):
                best[key] = (cost, rows[:])
            return

        for following in range(MASK_LIMIT):
            if not rows and not north_exterior_valid(following):
                continue
            if rows and rows_have_block(rows[-1], following):
                pruned_block += 1
                continue
            candidate = [*rows, following]
            if len(candidate) >= 2:
                center_row = len(candidate) - 2
                if not completed_center_row_valid(
                    candidate, center_row
                ):
                    pruned_stability_or_west_birth += 1
                    continue
            visit(candidate)

    visit([])
    relation = [
        {
            "incoming": list(incoming),
            "outgoing": list(outgoing),
            "cost": cost,
            "representative_patch": render_rows(rows),
        }
        for (incoming, outgoing), (cost, rows) in sorted(best.items())
    ]
    return relation, {
        "naive_patch_count": 1 << (PATCH_SIZE * PATCH_SIZE),
        "dfs_node_counts_by_completed_rows": {
            str(depth): count
            for depth, count in sorted(dfs_node_counts.items())
        },
        "pruned_live_block_extensions": pruned_block,
        "pruned_stability_or_west_birth_extensions": (
            pruned_stability_or_west_birth
        ),
        "valid_patch_count": valid_patch_count,
        "edge_extendible_patch_count": extendible_patch_count,
        "minimum_cost_transition_count": len(relation),
        "minimum_corner_cost": min(
            row["cost"] for row in relation
        ),
        "maximum_corner_cost": max(
            row["cost"] for row in relation
        ),
    }


def build() -> dict[str, Any]:
    nodes, edges = build_edge_graph()
    relation, corner_statistics = build_corner_relation(set(nodes))
    edge_payload = [
        [
            *edge.source,
            edge.target[1],
            edge.weight,
        ]
        for edge in edges
    ]
    edge_digest = hashlib.sha256(
        json.dumps(
            edge_payload, separators=(",", ":")
        ).encode("ascii")
    ).hexdigest()
    relation_digest = hashlib.sha256(
        json.dumps(
            relation, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
    ).hexdigest()
    return {
        "schema": "depth4-boundary-census-v1",
        "charged_depth": CHARGED_DEPTH,
        "halo_depth": CHARGED_DEPTH + 1,
        "edge_graph": {
            "state_count": len(nodes),
            "transition_count": len(edges),
            "weight_histogram": {
                str(weight): count
                for weight, count in sorted(
                    Counter(edge.weight for edge in edges).items()
                )
            },
            "state_sha256": hashlib.sha256(
                json.dumps(
                    nodes, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest(),
            "transition_sha256": edge_digest,
        },
        "corner_relation": {
            **corner_statistics,
            "relation_sha256": relation_digest,
            "relation": relation,
        },
        "claim_scope": (
            "Exact local depth-four block-free edge and corner languages. "
            "No four-side minimum or connectivity partition is claimed."
        ),
        "record_sha256_excluding_this_field": None,
    }


def finalize(record: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record["record_sha256_excluding_this_field"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return record


def summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "edge_graph": record["edge_graph"],
        "corner_relation": {
            key: record["corner_relation"][key]
            for key in (
                "naive_patch_count",
                "dfs_node_counts_by_completed_rows",
                "valid_patch_count",
                "edge_extendible_patch_count",
                "minimum_cost_transition_count",
                "minimum_corner_cost",
                "maximum_corner_cost",
            )
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = finalize(build())
    if args.verify:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored depth-four census differs")
        print("VERIFIED", args.output)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary(record), indent=2))


if __name__ == "__main__":
    main()
