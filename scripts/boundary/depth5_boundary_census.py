#!/usr/bin/env python3
"""Enumerate the exact depth-five block-free edge and corner languages."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = (
    ROOT
    / "certificates"
    / "upper_bounds"
    / "depth5_boundary_census.json"
)

import depth4_boundary_census as kernel  # noqa: E402


CHARGED_DEPTH = 5


def configure_kernel() -> None:
    """Specialize the tested Phase-030 local kernel to depth five."""
    kernel.CHARGED_DEPTH = CHARGED_DEPTH
    kernel.MASK_BITS = CHARGED_DEPTH + 1
    kernel.MASK_LIMIT = 1 << kernel.MASK_BITS
    kernel.PATCH_SIZE = kernel.MASK_BITS


def build() -> dict[str, Any]:
    configure_kernel()
    nodes, edges = kernel.build_edge_graph()
    relation, corner_statistics = kernel.build_corner_relation(set(nodes))
    edge_payload = [
        [*edge.source, edge.target[1], edge.weight]
        for edge in edges
    ]
    return {
        "schema": "depth5-boundary-census-v1",
        "charged_depth": CHARGED_DEPTH,
        "halo_depth": CHARGED_DEPTH + 1,
        "kernel": "scripts/boundary/depth4_boundary_census.py",
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
            "relation_sha256": hashlib.sha256(
                json.dumps(
                    relation, sort_keys=True, separators=(",", ":")
                ).encode("ascii")
            ).hexdigest(),
        },
        "claim_scope": (
            "Exact local depth-five block-free edge and corner languages. "
            "The 179,476-row relation is deterministically regenerated "
            "rather than embedded, keeping the portable record compact. "
            "No four-side minimum, recurrence, or connectivity partition "
            "is claimed by this census alone."
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
    corner = record["corner_relation"]
    return {
        "edge_graph": record["edge_graph"],
        "corner_relation": {
            key: corner[key]
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
            raise SystemExit("stored depth-five census differs")
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
