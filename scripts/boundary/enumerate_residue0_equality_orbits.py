#!/usr/bin/env python3
"""Enumerate the complete depth-five residue-zero equality-cycle support."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = (
    ROOT
    / "certificates"
    / "upper_bounds"
    / "residue0_equality_orbits_n40.json"
)
INF = 30_000
SHORT_INF = np.int16(1_000)
N = 40
TARGET = 72
import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_depth5_ring import path_matrix  # noqa: E402
from certify_depth5_ring import depth4_wastage  # noqa: E402


def configure_depth5() -> None:
    kernel.CHARGED_DEPTH = 5
    kernel.MASK_BITS = 6
    kernel.MASK_LIMIT = 64
    kernel.PATCH_SIZE = 6


def output_states(
    relation: list[dict[str, Any]],
) -> list[tuple[int, int]]:
    return sorted({tuple(row["outgoing"]) for row in relation})


def build(n: int) -> dict[str, Any]:
    if n < 16 or n % 8 != 0:
        raise ValueError("n must be >=16 and congruent to zero mod 8")
    target = depth4_wastage(n)
    configure_depth5()
    nodes, edges = kernel.build_edge_graph()
    relation, _statistics = kernel.build_corner_relation(set(nodes))
    sources = output_states(relation)
    paths = path_matrix(nodes, edges, sources, n - 10)
    transfer = side_transfer(paths, relation, nodes, sources)
    compact = np.where(
        transfer < INF, transfer, SHORT_INF
    ).astype(np.int16)

    threshold = target // 4
    anchor_sources, anchor_targets = np.nonzero(
        compact <= threshold
    )
    source_subset = np.unique(anchor_sources)
    target_subset = np.unique(anchor_targets)
    source_position = {
        int(state): index
        for index, state in enumerate(source_subset)
    }
    target_position = {
        int(state): index
        for index, state in enumerate(target_subset)
    }

    two_step = np.full(
        (len(target_subset), len(sources)),
        SHORT_INF,
        dtype=np.int16,
    )
    for middle in range(len(sources)):
        candidate = (
            compact[target_subset, middle, None]
            + compact[middle, None, :]
        )
        np.minimum(two_step, candidate, out=two_step)

    three_step = np.full(
        (len(target_subset), len(source_subset)),
        SHORT_INF,
        dtype=np.int16,
    )
    for middle in range(len(sources)):
        candidate = (
            two_step[:, middle, None]
            + compact[middle, source_subset][None, :]
        )
        np.minimum(three_step, candidate, out=three_step)

    totals = np.fromiter(
        (
            int(compact[first, second])
            + int(
                three_step[
                    target_position[int(second)],
                    source_position[int(first)],
                ]
            )
            for first, second in zip(
                anchor_sources, anchor_targets
            )
        ),
        dtype=np.int32,
        count=len(anchor_sources),
    )
    equality_indices = np.flatnonzero(totals == target)

    state_support: set[int] = set()
    arc_support: set[int] = set()
    anchor_cycle_count = 0
    sample_cycles: list[list[int]] = []
    dimension = len(sources)
    for equality_index in equality_indices:
        first = int(anchor_sources[equality_index])
        second = int(anchor_targets[equality_index])
        first_cost = int(compact[first, second])
        return_cost = target - first_cost
        target_row = target_position[second]
        opposite_candidates = np.flatnonzero(
            two_step[target_row, :].astype(np.int32)
            + compact[:, first].astype(np.int32)
            == return_cost
        )
        for fourth in opposite_candidates:
            two_cost = int(two_step[target_row, fourth])
            middle_candidates = np.flatnonzero(
                compact[second, :].astype(np.int32)
                + compact[:, fourth].astype(np.int32)
                == two_cost
            )
            for third in middle_candidates:
                cycle = [
                    first,
                    second,
                    int(third),
                    int(fourth),
                ]
                costs = [
                    int(
                        compact[
                            cycle[index],
                            cycle[(index + 1) % 4],
                        ]
                    )
                    for index in range(4)
                ]
                if sum(costs) != target:
                    raise AssertionError("bad equality-cycle recovery")
                state_support.update(cycle)
                arc_support.update(
                    cycle[index] * dimension
                    + cycle[(index + 1) % 4]
                    for index in range(4)
                )
                anchor_cycle_count += 1
                if len(sample_cycles) < 16:
                    sample_cycles.append(cycle)

    supported_arcs = [
        [encoded // dimension, encoded % dimension]
        for encoded in sorted(arc_support)
    ]
    supported_states = sorted(state_support)
    source_payload = [list(state) for state in sources]
    return {
        "schema": "depth5-residue0-equality-orbit-support-v1",
        "n": n,
        "edge_length": n - 10,
        "four_side_target": target,
        "language": {
            "edge_state_count": len(nodes),
            "edge_transition_count": len(edges),
            "corner_transition_count": len(relation),
            "corner_output_state_count": len(sources),
        },
        "side_transfer": {
            "finite_count": int(np.count_nonzero(transfer < INF)),
            "sha256": hashlib.sha256(transfer.tobytes()).hexdigest(),
        },
        "anchor_enumeration": {
            "threshold": threshold,
            "candidate_anchor_count": len(anchor_sources),
            "equality_anchor_count": len(equality_indices),
            "anchor_labelled_equality_cycle_count": anchor_cycle_count,
            "two_step_matrix_shape": list(two_step.shape),
            "two_step_matrix_sha256": hashlib.sha256(
                two_step.tobytes()
            ).hexdigest(),
            "three_step_matrix_shape": list(three_step.shape),
            "three_step_matrix_sha256": hashlib.sha256(
                three_step.tobytes()
            ).hexdigest(),
        },
        "complete_equality_support": {
            "state_count": len(supported_states),
            "arc_count": len(supported_arcs),
            "state_indices": supported_states,
            "states": [
                source_payload[index] for index in supported_states
            ],
            "arc_state_indices": supported_arcs,
            "sample_anchor_labelled_cycles": sample_cycles,
            "completeness": (
                "Every target-cost four-cycle has an arc of cost at most "
                "floor(target/4). "
                "Every such anchor and every minimizing two-/three-step "
                "return were exhaustively enumerated."
            ),
        },
        "claim_scope": (
            "Complete state/arc support of depth-five residue-zero "
            "equality cycles at the recurrent n=40 base. No depth-six "
            "lift or stronger population upper is claimed."
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
    parser.add_argument("--n", type=int, default=N)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = finalize(build(args.n))
    if args.verify:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored equality-orbit support differs")
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
                "language": record["language"],
                "anchor_enumeration": record["anchor_enumeration"],
                "complete_equality_support": {
                    key: record["complete_equality_support"][key]
                    for key in ("state_count", "arc_count")
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
