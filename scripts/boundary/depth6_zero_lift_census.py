#!/usr/bin/env python3
"""Enumerate zero-additional-wastage depth-six edge and corner languages."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = (
    ROOT
    / "certificates"
    / "upper_bounds"
    / "depth6_zero_lift_census.json"
)

import depth4_boundary_census as kernel  # noqa: E402


CHARGED_DEPTH = 6
State = tuple[int, int]


def configure_kernel() -> None:
    kernel.CHARGED_DEPTH = CHARGED_DEPTH
    kernel.MASK_BITS = CHARGED_DEPTH + 1
    kernel.MASK_LIMIT = 1 << kernel.MASK_BITS
    kernel.PATCH_SIZE = kernel.MASK_BITS


def build_filtered_edge_graph() -> tuple[list[State], list[kernel.Edge]]:
    edges: list[kernel.Edge] = []
    for left in range(kernel.MASK_LIMIT):
        for middle in range(kernel.MASK_LIMIT):
            for right in range(kernel.MASK_LIMIT):
                if not kernel.transition_valid(left, middle, right):
                    continue
                new_wastage = kernel.chu_wastage(
                    kernel.local_pattern(
                        left, middle, right, CHARGED_DEPTH
                    )
                )
                if new_wastage != 0:
                    continue
                edges.append(
                    kernel.Edge(
                        (left, middle),
                        (middle, right),
                        kernel.transition_weight(left, middle, right),
                    )
                )
    nodes = sorted(
        {edge.source for edge in edges}
        | {edge.target for edge in edges}
    )
    return nodes, edges


def new_corner_layer_zero(
    rows: Sequence[int],
    center_row: int,
) -> bool:
    inner = CHARGED_DEPTH - 1
    return (
        center_row != inner
        or kernel.chu_wastage(
            kernel.patch_pattern(rows, inner, inner)
        )
        == 0
    )


def build_filtered_corner_relation(
    valid_states: set[State],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    original = kernel.completed_center_row_valid

    def filtered(
        rows: Sequence[int], center_row: int
    ) -> bool:
        return original(rows, center_row) and new_corner_layer_zero(
            rows, center_row
        )

    kernel.completed_center_row_valid = filtered
    try:
        return kernel.build_corner_relation(valid_states)
    finally:
        kernel.completed_center_row_valid = original


def build_language() -> tuple[
    list[State],
    list[kernel.Edge],
    list[dict[str, Any]],
    dict[str, Any],
]:
    configure_kernel()
    nodes, edges = build_filtered_edge_graph()
    relation, statistics = build_filtered_corner_relation(set(nodes))
    return nodes, edges, relation, statistics


def build() -> dict[str, Any]:
    nodes, edges, relation, corner_statistics = build_language()
    edge_payload = [
        [*edge.source, edge.target[1], edge.weight]
        for edge in edges
    ]
    return {
        "schema": "depth6-zero-additional-wastage-lift-census-v1",
        "charged_depth": CHARGED_DEPTH,
        "halo_depth": CHARGED_DEPTH + 1,
        "filter": (
            "Chu--Stuckey wastage zero on every new straight depth-six "
            "cell and on the one genuinely new inward cell per corner"
        ),
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
                json.dumps(nodes, separators=(",", ":")).encode("ascii")
            ).hexdigest(),
            "transition_sha256": hashlib.sha256(
                json.dumps(edge_payload, separators=(",", ":")).encode(
                    "ascii"
                )
            ).hexdigest(),
        },
        "corner_relation": {
            **corner_statistics,
            "corner_output_state_count": len(
                {tuple(row["outgoing"]) for row in relation}
            ),
            "relation_sha256": hashlib.sha256(
                json.dumps(
                    relation, sort_keys=True, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest(),
        },
        "projection_logic": (
            "Any depth-six ring at the depth-five minimum must project "
            "to a depth-five equality ring and have zero wastage on "
            "every newly charged cell; hence it occurs in this language."
        ),
        "claim_scope": (
            "Exact filtered local language only. No four-side exclusion "
            "or residue-zero upper is claimed by this census alone."
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
            raise SystemExit("stored depth-six lift census differs")
        print("VERIFIED", args.output)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
