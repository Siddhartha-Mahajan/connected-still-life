#!/usr/bin/env python3
"""Probe exact low-cost depth-five square rings in residues zero and five."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import numpy as np


HERE = Path(__file__).resolve().parent
DEPTH4_MODULE = HERE.parent / "depth4"
CENSUS = HERE / "outputs" / "depth5_boundary_census.json"
OUTPUT = HERE / "outputs" / "depth5_residue05_probe.json"
INF = 30_000
if str(DEPTH4_MODULE) not in sys.path:
    sys.path.insert(0, str(DEPTH4_MODULE))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402


DEPTH4_RESIDUE_VECTOR = (18, 23, 18, 23, 20, 15, 26, 11)


def depth4_population_upper(n: int) -> int:
    return (
        4 * n * n
        + 5 * n
        - DEPTH4_RESIDUE_VECTOR[n % 8]
    ) // 8


def depth4_wastage(n: int) -> int:
    return 2 * n * n + 4 * n - 4 * depth4_population_upper(n)


def configure_kernel() -> None:
    kernel.CHARGED_DEPTH = 5
    kernel.MASK_BITS = 6
    kernel.MASK_LIMIT = 64
    kernel.PATCH_SIZE = 6


def output_states(
    relation: Sequence[dict[str, Any]],
) -> list[tuple[int, int]]:
    return sorted({tuple(row["outgoing"]) for row in relation})


def path_matrix(
    nodes: Sequence[tuple[int, int]],
    edges: Sequence[kernel.Edge],
    sources: Sequence[tuple[int, int]],
    length: int,
) -> np.ndarray:
    node_index = {state: index for index, state in enumerate(nodes)}
    distance = np.full(
        (len(sources), len(nodes)), INF, dtype=np.int16
    )
    for source_index, state in enumerate(sources):
        distance[source_index, node_index[state]] = 0
    incoming_by_target: list[list[tuple[int, int]]] = [
        [] for _state in nodes
    ]
    for edge in edges:
        incoming_by_target[node_index[edge.target]].append(
            (node_index[edge.source], edge.weight)
        )
    for _step in range(length):
        following = np.full_like(distance, INF)
        for target, incoming in enumerate(incoming_by_target):
            for source, weight in incoming:
                np.minimum(
                    following[:, target],
                    distance[:, source] + weight,
                    out=following[:, target],
                )
        distance = following
    return distance


def reciprocal_witness(
    transfer: np.ndarray,
) -> dict[str, Any]:
    diagonal = np.diag(transfer).astype(np.int32)
    self_index = int(np.argmin(diagonal))
    reciprocal = (
        transfer.astype(np.int32) + transfer.T.astype(np.int32)
    )
    flat = int(np.argmin(reciprocal))
    first, second = divmod(flat, transfer.shape[0])
    return {
        "minimum_four_equal_sides": int(4 * diagonal[self_index]),
        "self_state_index": self_index,
        "minimum_alternating_two_state_ring": int(
            2 * reciprocal[first, second]
        ),
        "alternating_state_indices": [first, second],
        "directed_side_costs": [
            int(transfer[first, second]),
            int(transfer[second, first]),
        ],
    }


def anchored_four_cycle_test(
    transfer: np.ndarray,
    target: int,
) -> dict[str, Any]:
    """Exactly test every four-cycle of total cost at most ``target``.

    Any such cycle has an arc of cost at most floor(target/4).  Anchor every
    one of those arcs, compute exact two- and three-step returns between the
    resulting endpoint subsets, and test the anchored cycle totals.
    """
    threshold = target // 4
    short_inf = np.int16(1_000)
    compact = np.where(
        transfer < INF, transfer, short_inf
    ).astype(np.int16)
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

    # two_step[b,d] = min_c T[b,c] + T[c,d]
    two_step = np.full(
        (len(target_subset), transfer.shape[0]),
        short_inf,
        dtype=np.int16,
    )
    for middle in range(transfer.shape[0]):
        candidate = (
            compact[target_subset, middle, None]
            + compact[middle, None, :]
        )
        np.minimum(two_step, candidate, out=two_step)

    # three_step[b,a] = min_d two_step[b,d] + T[d,a]
    three_step = np.full(
        (len(target_subset), len(source_subset)),
        short_inf,
        dtype=np.int16,
    )
    for middle in range(transfer.shape[0]):
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
    minimum_index = int(np.argmin(totals))
    first = int(anchor_sources[minimum_index])
    second = int(anchor_targets[minimum_index])
    minimum = int(totals[minimum_index])
    target_row = target_position[second]
    source_column = source_position[first]
    fourth = int(
        np.argmin(
            two_step[target_row, :].astype(np.int32)
            + compact[:, first].astype(np.int32)
        )
    )
    third = int(
        np.argmin(
            compact[second, :].astype(np.int32)
            + compact[:, fourth].astype(np.int32)
        )
    )
    cycle_states = [first, second, third, fourth]
    cycle_costs = [
        int(compact[cycle_states[index], cycle_states[(index + 1) % 4]])
        for index in range(4)
    ]
    if sum(cycle_costs) != minimum:
        raise AssertionError("failed to reconstruct anchored four-cycle")
    return {
        "target_cost": target,
        "anchor_threshold_floor_target_over_4": threshold,
        "anchor_arc_count": len(anchor_sources),
        "anchor_source_count": len(source_subset),
        "anchor_target_count": len(target_subset),
        "minimum_anchored_four_cycle_cost": minimum,
        "minimum_anchor_state_indices": [first, second],
        "minimum_anchor_cost": int(compact[first, second]),
        "minimum_three_step_return_cost": int(
            three_step[
                target_position[second], source_position[first]
            ]
        ),
        "minimum_cycle_state_indices": cycle_states,
        "minimum_cycle_arc_costs": cycle_costs,
        "two_step_matrix_shape": list(two_step.shape),
        "two_step_matrix_sha256": hashlib.sha256(
            two_step.tobytes()
        ).hexdigest(),
        "three_step_matrix_shape": list(three_step.shape),
        "three_step_matrix_sha256": hashlib.sha256(
            three_step.tobytes()
        ).hexdigest(),
        "cycle_at_or_below_target_exists": minimum <= target,
        "proof": (
            "Every four-cycle of total cost <=K has at least one arc "
            "of cost <=floor(K/4). All such arcs are anchors. Exact "
            "two-step and three-step min-plus returns test every cycle "
            "containing an anchor."
        ),
    }


def build(ns: Sequence[int]) -> dict[str, Any]:
    configure_kernel()
    stored = json.loads(CENSUS.read_text(encoding="utf-8"))
    nodes, edges = kernel.build_edge_graph()
    relation, corner_statistics = kernel.build_corner_relation(set(nodes))
    relation_digest = hashlib.sha256(
        json.dumps(
            relation, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
    ).hexdigest()
    if not (
        len(nodes) == stored["edge_graph"]["state_count"]
        and len(edges) == stored["edge_graph"]["transition_count"]
        and len(relation)
        == stored["corner_relation"]["minimum_cost_transition_count"]
        and corner_statistics["valid_patch_count"]
        == stored["corner_relation"]["valid_patch_count"]
        and relation_digest
        == stored["corner_relation"]["relation_sha256"]
    ):
        raise AssertionError("regenerated depth-five language differs")
    sources = output_states(relation)
    rows = []
    previous_by_residue: dict[
        int, tuple[int, np.ndarray, np.ndarray]
    ] = {}
    for n in ns:
        if n < 12:
            raise ValueError("depth-five square decomposition needs n>=12")
        length = n - 10
        paths = path_matrix(nodes, edges, sources, length)
        transfer = side_transfer(paths, relation, nodes, sources)
        finite = transfer < INF
        finite_values = transfer[finite]
        unique_costs, cost_counts = np.unique(
            finite_values, return_counts=True
        )
        reciprocal = reciprocal_witness(transfer)
        strict_average_threshold = (
            depth4_wastage(n) - 1
        ) // 4
        strict_average_arcs = (
            finite & (transfer <= strict_average_threshold)
        )
        low_sources, low_targets = np.nonzero(strict_average_arcs)
        anchored_test = anchored_four_cycle_test(
            transfer, depth4_wastage(n)
        )
        recurrence = None
        prior = previous_by_residue.get(n % 8)
        if prior is not None and prior[0] == n - 8:
            old = prior[1]
            old_paths = prior[2]
            old_finite = old < INF
            new_finite = transfer < INF
            old_path_finite = old_paths < INF
            new_path_finite = paths < INF
            recurrence = {
                "previous_n": n - 8,
                "restricted_path_finite_support_equal": bool(
                    np.array_equal(
                        old_path_finite, new_path_finite
                    )
                ),
                "every_restricted_path_entry_increases_by_3": bool(
                    np.array_equal(
                        paths[new_path_finite],
                        old_paths[new_path_finite] + 3,
                    )
                )
                if np.array_equal(
                    old_path_finite, new_path_finite
                )
                else False,
                "changed_restricted_path_entry_count_after_plus_3": int(
                    np.count_nonzero(
                        paths[new_path_finite]
                        != old_paths[new_path_finite] + 3
                    )
                )
                if np.array_equal(
                    old_path_finite, new_path_finite
                )
                else None,
                "finite_support_equal": bool(
                    np.array_equal(old_finite, new_finite)
                ),
                "every_finite_entry_increases_by_3": bool(
                    np.array_equal(
                        transfer[new_finite],
                        old[new_finite] + 3,
                    )
                )
                if np.array_equal(old_finite, new_finite)
                else False,
                "changed_finite_entry_count_after_plus_3": int(
                    np.count_nonzero(
                        transfer[new_finite]
                        != old[new_finite] + 3
                    )
                )
                if np.array_equal(old_finite, new_finite)
                else None,
                "inducts_for_all_later_lengths": bool(
                    np.array_equal(
                        old_path_finite, new_path_finite
                    )
                    and np.array_equal(
                        paths[new_path_finite],
                        old_paths[new_path_finite] + 3,
                    )
                ),
                "induction": (
                    "D[L+1]=D[L] min-plus E on the fixed edge graph; "
                    "a complete restricted path-matrix equality "
                    "D[L+8]=D[L]+3 propagates to every later L"
                ),
            }
        previous_by_residue[n % 8] = (n, transfer, paths)
        rows.append(
            {
                "n": n,
                "edge_length": length,
                "depth4_wastage_target": depth4_wastage(n),
                "side_transfer_finite_count": int(finite.sum()),
                "side_transfer_minimum": int(transfer[finite].min()),
                "side_transfer_maximum": int(transfer[finite].max()),
                "side_transfer_cost_histogram": {
                    str(int(cost)): int(count)
                    for cost, count in zip(unique_costs, cost_counts)
                },
                "side_transfer_sha256": hashlib.sha256(
                    transfer.tobytes()
                ).hexdigest(),
                "restricted_path_finite_count": int(
                    np.count_nonzero(paths < INF)
                ),
                "restricted_path_sha256": hashlib.sha256(
                    paths.tobytes()
                ).hexdigest(),
                "strict_improvement_anchor": {
                    "threshold": strict_average_threshold,
                    "arc_count": int(strict_average_arcs.sum()),
                    "distinct_source_count": int(
                        np.unique(low_sources).size
                    ),
                    "distinct_target_count": int(
                        np.unique(low_targets).size
                    ),
                },
                **reciprocal,
                "alternating_ring_matches_depth4": (
                    reciprocal["minimum_alternating_two_state_ring"]
                    == depth4_wastage(n)
                ),
                "alternating_states": [
                    list(sources[index])
                    for index in reciprocal[
                        "alternating_state_indices"
                    ]
                ],
                "anchored_four_cycle_test": anchored_test,
                "depth5_wastage_strictly_exceeds_depth4": (
                    not anchored_test[
                        "cycle_at_or_below_target_exists"
                    ]
                ),
                "comparison_to_n_minus_8": recurrence,
            }
        )
    by_n = {row["n"]: row for row in rows}
    residue5_bases = (21, 29, 37, 45)
    residue0_bases = (16, 24, 32, 40)
    residue5_finite = all(
        n in by_n
        and by_n[n]["anchored_four_cycle_test"][
            "minimum_anchored_four_cycle_cost"
        ]
        == by_n[n]["depth4_wastage_target"] + 1
        for n in residue5_bases
    )
    residue0_finite = all(
        n in by_n
        and by_n[n]["anchored_four_cycle_test"][
            "minimum_anchored_four_cycle_cost"
        ]
        == by_n[n]["depth4_wastage_target"]
        for n in residue0_bases
    )
    residue5_recurrence = bool(
        53 in by_n
        and by_n[53]["comparison_to_n_minus_8"]
        and by_n[53]["comparison_to_n_minus_8"][
            "inducts_for_all_later_lengths"
        ]
    )
    residue0_recurrence = bool(
        48 in by_n
        and by_n[48]["comparison_to_n_minus_8"]
        and by_n[48]["comparison_to_n_minus_8"][
            "inducts_for_all_later_lengths"
        ]
    )
    return {
        "schema": "depth5-residue05-ring-probe-v1",
        "status": (
            "exact side matrices and anchored exhaustive tests of every "
            "four-state ring at or below the depth-four target"
        ),
        "edge_state_count": len(nodes),
        "edge_transition_count": len(edges),
        "corner_transition_count": len(relation),
        "corner_output_state_count": len(sources),
        "rows": rows,
        "all_n_consequences": {
            "depth5_projection_lower_bound": (
                "Deleting the fifth charged layer from any valid "
                "depth-five square ring gives a valid depth-four ring. "
                "The removed Chu--Stuckey wastage is nonnegative, so "
                "B5(n)>=B4(n)."
            ),
            "residue_5": {
                "domain": "n>=21 and n mod 8=5",
                "finite_bases": list(residue5_bases),
                "each_finite_base_has_B5_equals_B4_plus_1": (
                    residue5_finite
                ),
                "complete_matrix_recurrence_at_45_to_53": (
                    residue5_recurrence
                ),
                "certified": (
                    residue5_finite and residue5_recurrence
                ),
                "consequence": (
                    "B5(n)=B4(n)+1 and "
                    "C(n)<=U4(n)-1=U3(n)-1"
                ),
            },
            "residue_0": {
                "domain": "n>=16 and n mod 8=0",
                "finite_bases": list(residue0_bases),
                "each_finite_base_has_B5_equals_B4": (
                    residue0_finite
                ),
                "complete_matrix_recurrence_at_40_to_48": (
                    residue0_recurrence
                ),
                "certified": (
                    residue0_finite and residue0_recurrence
                ),
                "consequence": (
                    "B5(n)=B4(n); depth five gives no population "
                    "improvement in this residue"
                ),
            },
            "new_exact_value": {
                "statement": "C(21)=230",
                "lower_witness_population": 230,
                "depth5_population_upper": 230,
                "certified": (
                    residue5_finite and residue5_recurrence
                ),
            },
        },
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
    parser.add_argument(
        "--n",
        type=int,
        nargs="+",
        default=[16, 21, 24, 29, 32, 37, 40, 45, 48, 53],
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = finalize(build(args.n))
    if args.verify:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored depth-five ring probe differs")
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
