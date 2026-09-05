#!/usr/bin/env python3
"""Propagate every physically possible n=19 target-42 low-slack corner."""

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


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
DEPTH4_MODULE = HERE.parent / "depth4"
DEPTH5_MODULE = HERE.parent / "depth5"
EQUALITY_LIFT_MODULE = HERE.parent / "equality_lift"
LOW_SLACK_MODULE = HERE.parent / "low_slack"
EQUALITY_SUPPORT_MODULE = HERE.parent / "equality_support"
JOINT_LIFT_MODULE = HERE.parent / "joint_lift"
OUTPUT = HERE / "outputs" / "n19_complete_low_slack_chain.json"

N = 19
TARGET_POPULATION = 189
TARGET_WASTAGE = 42
START_DEPTH = 5
TERMINAL_DEPTH = 9
INF = 30_000
PROGRESS = False
State = tuple[int, int]

for dependency in (
    JOINT_LIFT_MODULE,
    EQUALITY_SUPPORT_MODULE,
    LOW_SLACK_MODULE,
    EQUALITY_LIFT_MODULE,
    DEPTH5_MODULE,
    DEPTH4_MODULE,
):
    if str(dependency) not in sys.path:
        sys.path.insert(0, str(dependency))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_n17_depth6_equality_lift import (  # noqa: E402
    enumerate_full_depth5_corners,
    output_states,
)
from probe_depth5_ring import (  # noqa: E402
    path_matrix,
)
from probe_n16_depth6_low_slack import (  # noqa: E402
    configure,
    edge_payload,
    mask_from_row,
)
from probe_residue1_slack1_lift import (  # noqa: E402
    complete_support_up_to,
)


GridPatch = dict[str, Any]


def progress(message: str) -> None:
    if PROGRESS:
        print(message, file=sys.stderr, flush=True)


def digest_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def edge_digest(edges: Sequence[kernel.Edge]) -> str:
    return hashlib.sha256(
        json.dumps(
            [
                [*edge.source, edge.target[1], int(edge.weight)]
                for edge in edges
            ],
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def minimum_relation(
    physical: Sequence[GridPatch],
) -> list[dict[str, Any]]:
    best: dict[tuple[State, State], tuple[int, tuple[str, ...]]] = {}
    for patch in physical:
        incoming = tuple(patch["incoming"])
        outgoing = tuple(patch["outgoing"])
        candidate = (
            int(patch["cost"]),
            tuple(patch["patch"]),
        )
        key = incoming, outgoing
        incumbent = best.get(key)
        if incumbent is None or candidate < incumbent:
            best[key] = candidate
    return [
        {
            "incoming": list(incoming),
            "outgoing": list(outgoing),
            "cost": cost,
            "representative_patch": list(patch),
        }
        for (incoming, outgoing), (cost, patch) in sorted(best.items())
    ]


def bounded_edge_lift(
    old_depth: int,
    old_edges: Sequence[kernel.Edge],
    maximum_added_charge: int,
) -> tuple[list[State], list[kernel.Edge], dict[str, Any]]:
    new_depth = old_depth + 1
    configure(new_depth)
    lifted: set[tuple[State, State, int]] = set()
    attempted = 0
    valid_added = Counter()
    retained_added = Counter()
    for old_edge in old_edges:
        left_old, middle_old, right_old, old_weight = edge_payload(
            old_edge
        )
        for high_left, high_middle, high_right in product(
            (0, 1),
            repeat=3,
        ):
            attempted += 1
            shift = old_depth + 1
            left = left_old | (high_left << shift)
            middle = middle_old | (high_middle << shift)
            right = right_old | (high_right << shift)
            # ``old_edge`` already certifies the exterior condition, every
            # old block test, and stability at charged depths 1..old_depth.
            # The new high bits can only create a block across the last
            # old/new bit boundary and can only affect the newly charged
            # depth.  Retesting all previous local patterns is equivalent
            # but increasingly expensive at deep lifts.
            if (
                kernel.rows_have_block(left, middle)
                or kernel.rows_have_block(middle, right)
            ):
                continue
            new_pattern = kernel.local_pattern(
                left,
                middle,
                right,
                new_depth,
            )
            if not kernel.is_stable_pattern(new_pattern):
                continue
            added = int(kernel.chu_wastage(new_pattern))
            weight = old_weight + added
            valid_added[added] += 1
            if added > maximum_added_charge:
                continue
            retained_added[added] += 1
            lifted.add(((left, middle), (middle, right), weight))
    edges = [
        kernel.Edge(source, target, weight)
        for source, target, weight in sorted(lifted)
    ]
    nodes = sorted(
        {edge.source for edge in edges}
        | {edge.target for edge in edges}
    )
    return nodes, edges, {
        "old_depth": old_depth,
        "new_depth": new_depth,
        "maximum_added_charge": maximum_added_charge,
        "attempted_high_bit_extensions": attempted,
        "valid_extension_histogram_by_added_charge": {
            str(charge): count
            for charge, count in sorted(valid_added.items())
        },
        "retained_extension_histogram_by_added_charge": {
            str(charge): count
            for charge, count in sorted(retained_added.items())
        },
        "edge_state_count": len(nodes),
        "edge_transition_count": len(edges),
        "edge_sha256": edge_digest(edges),
    }


def one_layer_corner_extension_valid(
    rows: Sequence[int],
    old_depth: int,
) -> bool:
    """Validate only geometry newly exposed by a one-layer corner lift."""

    new_depth = old_depth + 1
    if len(rows) != new_depth + 1:
        return False
    top_position = old_depth
    if (
        sum(
            kernel.row_cell(rows, 0, column)
            for column in range(
                max(0, top_position - 1),
                min(new_depth + 1, top_position + 2),
            )
        )
        == 3
    ):
        return False
    if any(
        kernel.rows_have_block(rows[index], rows[index + 1])
        for index in range(new_depth)
    ):
        return False
    if not all(
        kernel.is_stable_pattern(
            kernel.patch_pattern(
                rows,
                center,
                old_depth,
            )
        )
        for center in range(old_depth)
    ):
        return False
    return kernel.completed_center_row_valid(rows, old_depth)


def bounded_physical_corner_lift(
    old_depth: int,
    old_patches: Sequence[GridPatch],
    old_edges: Sequence[kernel.Edge],
    maximum_added_charge: int,
) -> tuple[list[GridPatch], dict[str, Any]]:
    incoming_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    outgoing_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    for edge in old_edges:
        incoming_edges[edge.target].append(edge)
        outgoing_edges[edge.source].append(edge)

    new_depth = old_depth + 1
    configure(new_depth)
    unique: set[tuple[State, State, int, tuple[str, ...]]] = set()
    attempted = 0
    raw_valid = 0
    valid_added = Counter()
    retained_added = Counter()
    for mapping in old_patches:
        base_rows = [mask_from_row(row) for row in mapping["patch"]]
        incoming = tuple(mapping["incoming"])
        outgoing = tuple(mapping["outgoing"])
        for last_edge, first_edge, diagonal in product(
            incoming_edges.get(incoming, ()),
            outgoing_edges.get(outgoing, ()),
            (0, 1),
        ):
            attempted += 1
            (
                last_left,
                _last_middle,
                _last_right,
                last_weight,
            ) = edge_payload(last_edge)
            (
                _first_left,
                _first_middle,
                first_right,
                first_weight,
            ) = edge_payload(first_edge)
            high = old_depth + 1
            rows = [
                base_rows[row]
                | (((first_right >> row) & 1) << high)
                for row in range(old_depth + 1)
            ]
            rows.append(last_left | (diagonal << high))
            if not one_layer_corner_extension_valid(rows, old_depth):
                continue
            raw_valid += 1
            base_cost = (
                int(mapping["cost"])
                + int(last_weight)
                + int(first_weight)
            )
            added = int(
                kernel.chu_wastage(
                    kernel.patch_pattern(
                        rows,
                        old_depth,
                        old_depth,
                    )
                )
            )
            cost = base_cost + added
            valid_added[added] += 1
            if added > maximum_added_charge:
                continue
            retained_added[added] += 1
            incoming_new, outgoing_new = kernel.corner_states(rows)
            rendered = tuple(kernel.render_rows(rows))
            unique.add(
                (
                    incoming_new,
                    outgoing_new,
                    cost,
                    rendered,
                )
            )
    patches = [
        {
            "incoming": list(incoming),
            "outgoing": list(outgoing),
            "cost": cost,
            "patch": list(rendered),
        }
        for incoming, outgoing, cost, rendered in sorted(unique)
    ]
    return patches, {
        "old_depth": old_depth,
        "new_depth": new_depth,
        "maximum_added_charge": maximum_added_charge,
        "input_physical_patch_count": len(old_patches),
        "attempted_adjacent_edge_and_diagonal_contexts": attempted,
        "raw_valid_context_count": raw_valid,
        "valid_histogram_by_added_charge": {
            str(charge): count
            for charge, count in sorted(valid_added.items())
        },
        "retained_histogram_by_added_charge": {
            str(charge): count
            for charge, count in sorted(retained_added.items())
        },
        "distinct_retained_physical_patch_count": len(patches),
        "physical_patch_sha256": digest_json(patches),
    }


def safe_minimum_test(
    transfer: np.ndarray,
    target: int,
) -> tuple[dict[str, Any], int | None]:
    """Find the true minimum whenever a cycle at most ``target`` exists.

    Only arcs of cost at most floor(target/4) need be anchored.  Arithmetic
    uses a genuine int32 sentinel here: the shared legacy helper replaces
    infinity by 1000 for compact int16 min-plus products, which is harmless
    when a finite return exists but cannot safely reconstruct an empty
    anchored language.
    """

    threshold = target // 4
    matrix = transfer.astype(np.int32, copy=True)
    big = np.int32(100_000_000)
    matrix[matrix >= INF] = big
    anchor_sources, anchor_targets = np.nonzero(matrix <= threshold)
    anchor_count = len(anchor_sources)
    if not anchor_count:
        return {
            "target_cost": target,
            "anchor_threshold_floor_target_over_4": threshold,
            "anchor_arc_count": 0,
            "cycle_at_or_below_target_exists": False,
            "minimum_anchored_four_cycle_cost": INF,
            "proof": (
                "Every four-cycle of total cost at most K has an arc of "
                "cost at most floor(K/4). No such arc exists."
            ),
        }, None

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
        (len(target_subset), matrix.shape[0]),
        big,
        dtype=np.int32,
    )
    for middle in range(matrix.shape[0]):
        candidate = (
            matrix[target_subset, middle, None]
            + matrix[middle, None, :]
        )
        np.minimum(two_step, candidate, out=two_step)

    three_step = np.full(
        (len(target_subset), len(source_subset)),
        big,
        dtype=np.int32,
    )
    for middle in range(matrix.shape[0]):
        candidate = (
            two_step[:, middle, None]
            + matrix[middle, source_subset][None, :]
        )
        np.minimum(three_step, candidate, out=three_step)

    totals = np.fromiter(
        (
            int(matrix[first, second])
            + int(
                three_step[
                    target_position[int(second)],
                    source_position[int(first)],
                ]
            )
            for first, second in zip(
                anchor_sources,
                anchor_targets,
            )
        ),
        dtype=np.int64,
        count=anchor_count,
    )
    minimum_index = int(np.argmin(totals))
    minimum = int(totals[minimum_index])
    finite_return = minimum < int(big)
    result = {
        "target_cost": target,
        "anchor_threshold_floor_target_over_4": threshold,
        "anchor_arc_count": anchor_count,
        "anchor_source_count": len(source_subset),
        "anchor_target_count": len(target_subset),
        "finite_anchor_return_exists": finite_return,
        "minimum_anchored_four_cycle_cost": (
            minimum if finite_return else INF
        ),
        "cycle_at_or_below_target_exists": (
            finite_return and minimum <= target
        ),
        "two_step_matrix_shape": list(two_step.shape),
        "two_step_matrix_sha256": hashlib.sha256(
            two_step.tobytes()
        ).hexdigest(),
        "three_step_matrix_shape": list(three_step.shape),
        "three_step_matrix_sha256": hashlib.sha256(
            three_step.tobytes()
        ).hexdigest(),
        "proof": (
            "Every four-cycle of total cost at most K has an arc of "
            "cost at most floor(K/4). Every such finite anchor and its "
            "exact three-step min-plus return were tested."
        ),
    }
    if not finite_return:
        return result, None

    first = int(anchor_sources[minimum_index])
    second = int(anchor_targets[minimum_index])
    target_row = target_position[second]
    fourth_costs = (
        two_step[target_row, :].astype(np.int64)
        + matrix[:, first].astype(np.int64)
    )
    fourth = int(np.argmin(fourth_costs))
    third_costs = (
        matrix[second, :].astype(np.int64)
        + matrix[:, fourth].astype(np.int64)
    )
    third = int(np.argmin(third_costs))
    cycle = [first, second, third, fourth]
    costs = [
        int(matrix[cycle[index], cycle[(index + 1) % 4]])
        for index in range(4)
    ]
    if any(cost >= int(big) for cost in costs):
        raise AssertionError("finite minimum reconstructed with infinity")
    if sum(costs) != minimum:
        raise AssertionError("failed exact anchored-cycle reconstruction")
    result.update(
        {
            "minimum_anchor_state_indices": [first, second],
            "minimum_anchor_cost": costs[0],
            "minimum_cycle_state_indices": cycle,
            "minimum_cycle_arc_costs": costs,
        }
    )
    return result, minimum


def retain_physical_within_slack(
    physical: Sequence[GridPatch],
    nodes: Sequence[State],
    sources: Sequence[State],
    paths: np.ndarray,
    transfer: np.ndarray,
    support: dict[str, Any],
    slack: int,
) -> tuple[list[GridPatch], dict[str, Any]]:
    """All physical corners that can fit some supported abstract arc."""

    node_index = {state: index for index, state in enumerate(nodes)}
    arcs_by_output: dict[State, list[tuple[int, int]]] = defaultdict(list)
    for source_index, target_index in support["arc_state_indices"]:
        arcs_by_output[sources[target_index]].append(
            (source_index, target_index)
        )

    retained = []
    minimum_excess_histogram = Counter()
    missing_input_state_count = 0
    for patch in physical:
        incoming = tuple(patch["incoming"])
        incoming_index = node_index.get(incoming)
        if incoming_index is None:
            missing_input_state_count += 1
            continue
        outgoing = tuple(patch["outgoing"])
        best_excess = None
        for source_index, target_index in arcs_by_output.get(
            outgoing,
            (),
        ):
            path_cost = int(paths[source_index, incoming_index])
            if path_cost >= INF:
                continue
            physical_arc_cost = path_cost + int(patch["cost"])
            abstract_arc_cost = int(
                transfer[source_index, target_index]
            )
            excess = physical_arc_cost - abstract_arc_cost
            if excess < 0:
                raise AssertionError(
                    "physical realization beats abstract transfer"
                )
            if best_excess is None or excess < best_excess:
                best_excess = excess
        if best_excess is None or best_excess > slack:
            continue
        retained.append(patch)
        minimum_excess_histogram[best_excess] += 1

    retained.sort(
        key=lambda patch: (
            patch["incoming"],
            patch["outgoing"],
            patch["cost"],
            patch["patch"],
        )
    )
    return retained, {
        "input_physical_patch_count": len(physical),
        "supported_arc_count": support["arc_count"],
        "global_slack_allowance": slack,
        "missing_input_state_count": missing_input_state_count,
        "retained_physical_patch_count": len(retained),
        "minimum_arc_excess_histogram": {
            str(excess): count
            for excess, count in sorted(
                minimum_excess_histogram.items()
            )
        },
        "retained_physical_patch_sha256": digest_json(retained),
        "safe_filter": (
            "For a target board, replacing every physical side realization "
            "by its abstract minimum gives a supported cycle of cost at "
            "least the global minimum. Hence total physical excess is at "
            "most target minus global minimum, and each individual corner "
            "realization has excess at most that allowance."
        ),
    }


def zero_length_transfer(
    relation: Sequence[GridPatch],
    sources: Sequence[State],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Exact side transfer when adjacent corners meet with no edge step."""

    source_index = {
        state: index for index, state in enumerate(sources)
    }
    transfer = np.full(
        (len(sources), len(sources)),
        INF,
        dtype=np.int32,
    )
    compatible_mapping_count = 0
    for corner in relation:
        incoming = source_index.get(tuple(corner["incoming"]))
        outgoing = source_index[tuple(corner["outgoing"])]
        if incoming is None:
            continue
        compatible_mapping_count += 1
        cost = int(corner["cost"])
        if cost < transfer[incoming, outgoing]:
            transfer[incoming, outgoing] = cost
    return transfer, {
        "representation": "sparse_identity_path",
        "identity_state_count": len(sources),
        "compatible_corner_mapping_count": compatible_mapping_count,
        "proof": (
            "A path of length zero exists exactly when its source state "
            "equals the corner incoming state, and then has cost zero."
        ),
    }


def retain_zero_length_physical_within_slack(
    physical: Sequence[GridPatch],
    sources: Sequence[State],
    transfer: np.ndarray,
    support: dict[str, Any],
    slack: int,
) -> tuple[list[GridPatch], dict[str, Any]]:
    """Physical target corners for an exact identity side path."""

    source_index = {
        state: index for index, state in enumerate(sources)
    }
    supported_arcs = {
        (int(first), int(second))
        for first, second in support["arc_state_indices"]
    }
    retained = []
    minimum_excess_histogram = Counter()
    missing_input_state_count = 0
    for patch in physical:
        incoming = source_index.get(tuple(patch["incoming"]))
        if incoming is None:
            missing_input_state_count += 1
            continue
        outgoing = source_index[tuple(patch["outgoing"])]
        if (incoming, outgoing) not in supported_arcs:
            continue
        excess = int(patch["cost"]) - int(
            transfer[incoming, outgoing]
        )
        if excess < 0:
            raise AssertionError(
                "physical zero-length corner beats transfer"
            )
        if excess > slack:
            continue
        retained.append(patch)
        minimum_excess_histogram[excess] += 1

    retained.sort(
        key=lambda patch: (
            patch["incoming"],
            patch["outgoing"],
            patch["cost"],
            patch["patch"],
        )
    )
    return retained, {
        "input_physical_patch_count": len(physical),
        "supported_arc_count": support["arc_count"],
        "global_slack_allowance": slack,
        "missing_input_state_count": missing_input_state_count,
        "retained_physical_patch_count": len(retained),
        "minimum_arc_excess_histogram": {
            str(excess): count
            for excess, count in sorted(
                minimum_excess_histogram.items()
            )
        },
        "retained_physical_patch_sha256": digest_json(retained),
        "safe_filter": (
            "At straight length zero, the side path is the identity. "
            "Every physical corner on a supported endpoint arc is retained "
            "when its cost exceeds the minimum endpoint transfer by no "
            "more than the global slack."
        ),
    }


def analyze_depth(
    depth: int,
    nodes: list[State],
    edges: list[kernel.Edge],
    relation: list[dict[str, Any]],
    physical: list[GridPatch],
) -> tuple[dict[str, Any], list[GridPatch], int | None]:
    valid_nodes = set(nodes)
    relation = [
        mapping
        for mapping in relation
        if tuple(mapping["incoming"]) in valid_nodes
        and tuple(mapping["outgoing"]) in valid_nodes
    ]
    sources = output_states(relation)
    edge_length = N - 2 * depth
    if not sources:
        return {
            "depth": depth,
            "edge_length": edge_length,
            "edge_state_count": len(nodes),
            "edge_transition_count": len(edges),
            "corner_mapping_count": 0,
            "corner_output_state_count": 0,
            "target_survives": False,
            "exclusion_stage": "empty_corner_relation",
        }, [], None

    if edge_length == 0:
        paths = None
        transfer, zero_length_statistics = zero_length_transfer(
            relation,
            sources,
        )
    else:
        paths = path_matrix(nodes, edges, sources, edge_length)
        transfer = side_transfer(
            paths,
            relation,
            nodes,
            sources,
        )
        zero_length_statistics = None
    minimum_test, minimum = safe_minimum_test(
        transfer,
        TARGET_WASTAGE,
    )
    base = {
        "depth": depth,
        "edge_length": edge_length,
        "edge_state_count": len(nodes),
        "edge_transition_count": len(edges),
        "edge_sha256": edge_digest(edges),
        "corner_mapping_count": len(relation),
        "corner_output_state_count": len(sources),
        "minimum_relation_sha256": digest_json(relation),
        "physical_candidate_count": len(physical),
        "physical_candidate_sha256": digest_json(physical),
        "path_representation": (
            "sparse_identity" if paths is None else "dense_min_plus"
        ),
        "path_finite_count": (
            len(sources)
            if paths is None
            else int(np.count_nonzero(paths < INF))
        ),
        "path_sha256": (
            digest_json(
                [
                    [index, list(state)]
                    for index, state in enumerate(sources)
                ]
            )
            if paths is None
            else hashlib.sha256(paths.tobytes()).hexdigest()
        ),
        "transfer_finite_count": int(
            np.count_nonzero(transfer < INF)
        ),
        "transfer_sha256": hashlib.sha256(
            transfer.tobytes()
        ).hexdigest(),
        "minimum_test": minimum_test,
    }
    if zero_length_statistics is not None:
        base["zero_length_transfer"] = zero_length_statistics
    if minimum is None or minimum > TARGET_WASTAGE:
        anchor_count = int(
            minimum_test.get("anchor_arc_count", 0)
        )
        base.update(
            {
                "target_survives": False,
                "exclusion_stage": (
                    "no_anchor_arc"
                    if minimum is None and not anchor_count
                    else (
                        "no_finite_anchored_cycle"
                        if minimum is None
                        else "minimum_exceeds_target"
                    )
                ),
            }
        )
        return base, [], minimum

    support, exact_supports = complete_support_up_to(
        transfer,
        sources,
        minimum,
        TARGET_WASTAGE,
    )
    slack = TARGET_WASTAGE - minimum
    if paths is None:
        retained_physical, physical_filter = (
            retain_zero_length_physical_within_slack(
                physical,
                sources,
                transfer,
                support,
                slack,
            )
        )
    else:
        retained_physical, physical_filter = (
            retain_physical_within_slack(
                physical,
                nodes,
                sources,
                paths,
                transfer,
                support,
                slack,
            )
        )
    if not retained_physical:
        base.update(
            {
                "minimum": minimum,
                "global_slack": slack,
                "support_union": support,
                "exact_supports": exact_supports,
                "physical_filter": physical_filter,
                "target_survives": False,
                "exclusion_stage": "no_physical_supported_corner",
            }
        )
        return base, [], minimum
    base.update(
        {
            "minimum": minimum,
            "global_slack": slack,
            "support_union": support,
            "exact_supports": exact_supports,
            "physical_filter": physical_filter,
            "target_survives": True,
            "exclusion_stage": None,
        }
    )
    return base, retained_physical, minimum


def build() -> dict[str, Any]:
    configure(START_DEPTH)
    progress(f"depth {START_DEPTH}: building edge graph")
    nodes, edges = kernel.build_edge_graph()
    initial_edge_state_count = len(nodes)
    initial_edge_transition_count = len(edges)
    initial_edge_sha256 = edge_digest(edges)
    progress(f"depth {START_DEPTH}: enumerating minimum corners")
    relation, relation_statistics = kernel.build_corner_relation(
        set(nodes)
    )
    progress(f"depth {START_DEPTH}: enumerating all physical corners")
    all_physical, physical_statistics = enumerate_full_depth5_corners(
        set(nodes)
    )
    physical = [
        {
            "incoming": list(patch["incoming"]),
            "outgoing": list(patch["outgoing"]),
            "cost": int(patch["cost"]),
            "patch": list(patch["patch"]),
        }
        for patch in all_physical
    ]
    stages = []
    lifts = []
    excluded_at = None

    for depth in range(START_DEPTH, TERMINAL_DEPTH + 1):
        progress(
            f"depth {depth}: analyze nodes={len(nodes)} "
            f"edges={len(edges)} relation={len(relation)} "
            f"physical={len(physical)}"
        )
        stage, retained_physical, minimum = analyze_depth(
            depth,
            nodes,
            edges,
            relation,
            physical,
        )
        progress(
            f"depth {depth}: minimum={minimum} "
            f"slack={stage.get('global_slack')} "
            f"retained_physical={len(retained_physical)} "
            f"survives={stage['target_survives']}"
        )
        stages.append(stage)
        if not stage["target_survives"]:
            excluded_at = depth
            break
        if depth == TERMINAL_DEPTH:
            physical = retained_physical
            break

        slack = TARGET_WASTAGE - int(minimum)
        progress(
            f"depth {depth}->{depth + 1}: lifting "
            f"{len(edges)} edges with slack {slack}"
        )
        nodes_next, edges_next, edge_lift_statistics = (
            bounded_edge_lift(
                depth,
                edges,
                slack,
            )
        )
        progress(
            f"depth {depth}->{depth + 1}: retained "
            f"{len(edges_next)} edges; lifting "
            f"{len(retained_physical)} physical corners"
        )
        physical_next, corner_lift_statistics = (
            bounded_physical_corner_lift(
                depth,
                retained_physical,
                edges,
                slack,
            )
        )
        progress(
            f"depth {depth}->{depth + 1}: retained "
            f"{len(physical_next)} physical corners"
        )
        relation_next = minimum_relation(physical_next)
        lifts.append(
            {
                "from_depth": depth,
                "to_depth": depth + 1,
                "global_slack_allowance": slack,
                "edge_lift": edge_lift_statistics,
                "physical_corner_lift": corner_lift_statistics,
                "next_minimum_relation_count": len(relation_next),
                "next_minimum_relation_sha256": digest_json(
                    relation_next
                ),
            }
        )
        nodes = nodes_next
        edges = edges_next
        physical = physical_next
        relation = relation_next

    excluded = excluded_at is not None
    record = {
        "schema": "n19-complete-all-low-slack-inward-chain-v1",
        "scope": {
            "n": N,
            "target_population": TARGET_POPULATION,
            "target_wastage": TARGET_WASTAGE,
            "start_depth": START_DEPTH,
            "terminal_depth": TERMINAL_DEPTH,
            "whole_board_search": False,
            "minimum_only_physical_corners": False,
        },
        "completeness_invariant": (
            "At each depth, every physical corner that can realize a "
            "supported abstract arc within target minus the global minimum "
            "is retained. Every next-layer edge and corner extension whose "
            "nonnegative added charge fits that same allowance is retained. "
            "This contains the projection of every target board by "
            "induction."
        ),
        "initial_depth5": {
            "edge_state_count": initial_edge_state_count,
            "edge_transition_count": initial_edge_transition_count,
            "edge_sha256": initial_edge_sha256,
            "minimum_corner_relation_statistics": relation_statistics,
            "full_physical_corner_statistics": physical_statistics,
        },
        "stages": stages,
        "lifts": lifts,
        "conclusion": {
            "population_189_excluded": excluded,
            "excluded_at_depth": excluded_at,
            "connected_upper_bound": 188 if excluded else 189,
            "rigorous_interval": [187, 188] if excluded else [187, 189],
            "terminal_target_survives": (
                bool(stages)
                and stages[-1]["depth"] == TERMINAL_DEPTH
                and stages[-1]["target_survives"]
            ),
            "next_step": (
                "test population 188 at total wastage 46"
                if excluded
                else (
                    "assemble every retained terminal physical context "
                    "and verify full boards"
                )
            ),
        },
    }
    if (
        not excluded
        and bool(stages)
        and stages[-1]["depth"] == TERMINAL_DEPTH
        and stages[-1]["target_survives"]
    ):
        record["terminal_physical_patches"] = physical
        record["terminal_physical_patch_count"] = len(physical)
        record["terminal_physical_patch_sha256"] = digest_json(
            physical
        )
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    record = build()
    rendered = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    if args.verify:
        if json.loads(OUTPUT.read_text(encoding="utf-8")) != json.loads(rendered):
            raise SystemExit("stored complete low-slack chain differs")
        print(f"VERIFIED {digest}")
        return

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(PROJECT)),
                "sha256": digest,
                "stages": [
                    {
                        "depth": stage["depth"],
                        "edge_length": stage["edge_length"],
                        "minimum": stage.get("minimum"),
                        "global_slack": stage.get("global_slack"),
                        "support_state_count": stage.get(
                            "support_union",
                            {},
                        ).get("state_count"),
                        "support_arc_count": stage.get(
                            "support_union",
                            {},
                        ).get("arc_count"),
                        "physical_candidate_count": stage.get(
                            "physical_candidate_count"
                        ),
                        "retained_physical_patch_count": stage.get(
                            "physical_filter",
                            {},
                        ).get("retained_physical_patch_count"),
                        "target_survives": stage["target_survives"],
                        "exclusion_stage": stage["exclusion_stage"],
                    }
                    for stage in record["stages"]
                ],
                "lifts": [
                    {
                        "from_depth": lift["from_depth"],
                        "to_depth": lift["to_depth"],
                        "global_slack_allowance": lift[
                            "global_slack_allowance"
                        ],
                        "edge_transition_count": lift["edge_lift"][
                            "edge_transition_count"
                        ],
                        "physical_patch_count": lift[
                            "physical_corner_lift"
                        ][
                            "distinct_retained_physical_patch_count"
                        ],
                        "minimum_relation_count": lift[
                            "next_minimum_relation_count"
                        ],
                    }
                    for lift in record["lifts"]
                ],
                "conclusion": record["conclusion"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
