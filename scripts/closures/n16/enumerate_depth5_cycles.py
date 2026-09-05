#!/usr/bin/env python3
"""Enumerate every abstract depth-five n=16 ring of charge at most 40."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BOUNDARY = ROOT / "scripts" / "boundary"
OUTPUT = (
    ROOT
    / "certificates"
    / "exact_closures"
    / "n16"
    / "depth5_low_slack_cycles.json"
)
N = 16
DEPTH = 5
EDGE_LENGTH = N - 2 * DEPTH
TARGET_WASTAGE = 40
INF = 30_000
SHORT_INF = np.int16(1_000)

for directory in (BOUNDARY,):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_depth5_ring import path_matrix  # noqa: E402


def configure() -> None:
    kernel.CHARGED_DEPTH = DEPTH
    kernel.MASK_BITS = DEPTH + 1
    kernel.MASK_LIMIT = 1 << (DEPTH + 1)
    kernel.PATCH_SIZE = DEPTH + 1


def canonical_rotation(
    cycle: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    return min(cycle[index:] + cycle[:index] for index in range(4))


def enumerate_cycles(
    transfer: np.ndarray,
) -> tuple[dict[tuple[int, int, int, int], int], dict[str, Any]]:
    """Complete anchored enumeration of every four-cycle at cost <=40."""

    compact = np.where(
        transfer < INF, transfer, SHORT_INF
    ).astype(np.int16)
    threshold = TARGET_WASTAGE // 4
    anchor_sources, anchor_targets = np.nonzero(compact <= threshold)
    target_subset = np.unique(anchor_targets)
    target_position = {
        int(state): index for index, state in enumerate(target_subset)
    }

    # two_step[b,d] = min_c T[b,c]+T[c,d], only for possible anchor
    # targets b.  It is an exact pruning bound, not a restriction on c.
    two_step = np.full(
        (len(target_subset), transfer.shape[0]),
        SHORT_INF,
        dtype=np.int16,
    )
    for middle in range(transfer.shape[0]):
        candidate = (
            compact[target_subset, middle, None]
            + compact[middle, None, :]
        )
        np.minimum(two_step, candidate, out=two_step)

    cycles: dict[tuple[int, int, int, int], int] = {}
    expanded_opposites = 0
    expanded_intermediates = 0
    for anchor_number, (first_raw, second_raw) in enumerate(
        zip(anchor_sources, anchor_targets), start=1
    ):
        first = int(first_raw)
        second = int(second_raw)
        anchor_cost = int(compact[first, second])
        allowance = TARGET_WASTAGE - anchor_cost
        row = target_position[second]
        fourth_candidates = np.flatnonzero(
            two_step[row, :].astype(np.int32)
            + compact[:, first].astype(np.int32)
            <= allowance
        )
        expanded_opposites += len(fourth_candidates)
        for fourth_raw in fourth_candidates:
            fourth = int(fourth_raw)
            remaining = allowance - int(compact[fourth, first])
            third_candidates = np.flatnonzero(
                compact[second, :].astype(np.int32)
                + compact[:, fourth].astype(np.int32)
                <= remaining
            )
            expanded_intermediates += len(third_candidates)
            for third_raw in third_candidates:
                third = int(third_raw)
                charge = (
                    anchor_cost
                    + int(compact[second, third])
                    + int(compact[third, fourth])
                    + int(compact[fourth, first])
                )
                if charge > TARGET_WASTAGE:
                    raise AssertionError("pruned cycle exceeds target")
                cycle = canonical_rotation(
                    (first, second, third, fourth)
                )
                old = cycles.get(cycle)
                if old is not None and old != charge:
                    raise AssertionError("cycle charge is inconsistent")
                cycles[cycle] = charge
        if anchor_number % 5_000 == 0:
            print(
                f"anchors {anchor_number}/{len(anchor_sources)} "
                f"cycles={len(cycles)}",
                file=sys.stderr,
                flush=True,
            )

    return cycles, {
        "threshold": threshold,
        "candidate_anchor_count": len(anchor_sources),
        "anchor_source_count": len(np.unique(anchor_sources)),
        "anchor_target_count": len(target_subset),
        "expanded_anchor_opposite_count": expanded_opposites,
        "expanded_anchor_intermediate_count": expanded_intermediates,
        "two_step_matrix_shape": list(two_step.shape),
        "two_step_matrix_sha256": hashlib.sha256(
            two_step.tobytes()
        ).hexdigest(),
        "completeness": (
            "Every four-cycle of total cost <=40 has an arc of cost <=10. "
            "Every such arc was anchored; exact two-step lower bounds only "
            "pruned impossible opposites, and every feasible intermediate "
            "state was expanded."
        ),
    }


def build() -> dict[str, Any]:
    configure()
    nodes, edges = kernel.build_edge_graph()
    relation, corner_statistics = kernel.build_corner_relation(set(nodes))
    sources = sorted({tuple(row["outgoing"]) for row in relation})
    paths = path_matrix(nodes, edges, sources, EDGE_LENGTH)
    transfer = side_transfer(paths, relation, nodes, sources)
    cycles, anchor = enumerate_cycles(transfer)
    arcs = {
        (cycle[index], cycle[(index + 1) % 4])
        for cycle in cycles
        for index in range(4)
    }
    charge_histogram = Counter(cycles.values())
    arc_minimum_histogram = Counter(
        int(transfer[source, target]) for source, target in arcs
    )
    cycle_rows = [
        {"states": list(cycle), "minimum_charge": charge}
        for cycle, charge in sorted(cycles.items())
    ]
    result = {
        "schema": "n16-depth5-low-slack-abstract-cycles-v1",
        "n": N,
        "depth": DEPTH,
        "edge_length": EDGE_LENGTH,
        "target_population": 134,
        "target_total_wastage": TARGET_WASTAGE,
        "language": {
            "edge_state_count": len(nodes),
            "edge_transition_count": len(edges),
            "corner_output_state_count": len(sources),
            "minimum_corner_mapping_count": len(relation),
            "valid_physical_corner_patch_count": int(
                corner_statistics["valid_patch_count"]
            ),
        },
        "path_matrix_finite_count": int(np.count_nonzero(paths < INF)),
        "path_matrix_sha256": hashlib.sha256(paths.tobytes()).hexdigest(),
        "side_transfer_finite_count": int(
            np.count_nonzero(transfer < INF)
        ),
        "side_transfer_sha256": hashlib.sha256(
            transfer.tobytes()
        ).hexdigest(),
        "anchor_enumeration": anchor,
        "cycle_count_modulo_rotation": len(cycles),
        "cycle_minimum_charge_histogram": {
            str(charge): count
            for charge, count in sorted(charge_histogram.items())
        },
        "supported_directed_arc_count": len(arcs),
        "supported_arc_minimum_charge_histogram": {
            str(charge): count
            for charge, count in sorted(arc_minimum_histogram.items())
        },
        "supported_directed_arcs": [list(arc) for arc in sorted(arcs)],
        "cycles_modulo_rotation": cycle_rows,
        "claim_scope": (
            "Complete abstract minimum-transfer depth-five cycle census "
            "through charge 40. Physical tied/nonminimum realizations and "
            "the central 4x4 completion are not yet expanded."
        ),
        "record_sha256_excluding_this_field": None,
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["record_sha256_excluding_this_field"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = build()
    if args.verify:
        old = json.loads(args.output.read_text(encoding="utf-8"))
        if old != record:
            raise SystemExit("stored n=16 abstract cycle census differs")
        print(
            "VERIFIED",
            record["cycle_count_modulo_rotation"],
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
                "cycle_count_modulo_rotation": record[
                    "cycle_count_modulo_rotation"
                ],
                "cycle_minimum_charge_histogram": record[
                    "cycle_minimum_charge_histogram"
                ],
                "supported_directed_arc_count": record[
                    "supported_directed_arc_count"
                ],
                "record_sha256": record[
                    "record_sha256_excluding_this_field"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
