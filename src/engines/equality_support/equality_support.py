"""Exact anchored support of minimum-cost four-cycles in a transfer matrix."""

from __future__ import annotations

import hashlib
from typing import Any, Sequence

import numpy as np


INF = 30_000
SHORT_INF = np.int16(1_000)


def complete_equality_support(
    transfer: np.ndarray,
    sources: Sequence[tuple[int, int]],
    target: int,
) -> dict[str, Any]:
    """Return every state/arc occurring in a target-cost four-cycle."""

    compact = np.where(transfer < INF, transfer, SHORT_INF).astype(
        np.int16
    )
    threshold = target // 4
    anchor_sources, anchor_targets = np.nonzero(compact <= threshold)
    source_subset = np.unique(anchor_sources)
    target_subset = np.unique(anchor_targets)
    source_position = {
        int(state): index for index, state in enumerate(source_subset)
    }
    target_position = {
        int(state): index for index, state in enumerate(target_subset)
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
            for first, second in zip(anchor_sources, anchor_targets)
        ),
        dtype=np.int32,
        count=len(anchor_sources),
    )
    equality_indices = np.flatnonzero(totals == target)
    state_support: set[int] = set()
    arc_support: set[tuple[int, int]] = set()
    anchor_cycle_count = 0
    sample_cycles = []
    cost_vector_histogram: dict[str, int] = {}

    for equality_index in equality_indices:
        first = int(anchor_sources[equality_index])
        second = int(anchor_targets[equality_index])
        first_cost = int(compact[first, second])
        return_cost = target - first_cost
        target_row = target_position[second]
        fourth_candidates = np.flatnonzero(
            two_step[target_row, :].astype(np.int32)
            + compact[:, first].astype(np.int32)
            == return_cost
        )
        for fourth_raw in fourth_candidates:
            fourth = int(fourth_raw)
            two_cost = int(two_step[target_row, fourth])
            third_candidates = np.flatnonzero(
                compact[second, :].astype(np.int32)
                + compact[:, fourth].astype(np.int32)
                == two_cost
            )
            for third_raw in third_candidates:
                third = int(third_raw)
                cycle = (first, second, third, fourth)
                costs = tuple(
                    int(
                        compact[
                            cycle[index],
                            cycle[(index + 1) % 4],
                        ]
                    )
                    for index in range(4)
                )
                if sum(costs) != target:
                    raise AssertionError("bad equality-cycle recovery")
                state_support.update(cycle)
                arc_support.update(
                    (cycle[index], cycle[(index + 1) % 4])
                    for index in range(4)
                )
                key = ",".join(map(str, costs))
                cost_vector_histogram[key] = (
                    cost_vector_histogram.get(key, 0) + 1
                )
                anchor_cycle_count += 1
                if len(sample_cycles) < 32:
                    sample_cycles.append(
                        {
                            "state_indices": list(cycle),
                            "arc_costs": list(costs),
                        }
                    )

    supported_states = sorted(state_support)
    supported_arcs = [list(arc) for arc in sorted(arc_support)]
    return {
        "target": target,
        "anchor": {
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
        "state_count": len(supported_states),
        "arc_count": len(supported_arcs),
        "state_indices": supported_states,
        "states": [list(sources[index]) for index in supported_states],
        "arc_state_indices": supported_arcs,
        "arc_states": [
            [list(sources[first]), list(sources[second])]
            for first, second in sorted(arc_support)
        ],
        "anchor_labelled_cost_vector_histogram": dict(
            sorted(cost_vector_histogram.items())
        ),
        "sample_anchor_labelled_cycles": sample_cycles,
        "completeness": (
            "Every target-cost four-cycle has an arc of cost at most "
            "floor(target/4). Every such anchor and every minimizing "
            "two-/three-step return were exhaustively expanded."
        ),
    }

