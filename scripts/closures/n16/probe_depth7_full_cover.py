#!/usr/bin/env python3
"""Lift the complete low-slack n=16 language to a depth-seven full cover."""

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
CERTIFICATES = ROOT / "certificates" / "exact_closures" / "n16"
PROBE6 = CERTIFICATES / "depth6_low_slack_probe.json"
COUNT6 = CERTIFICATES / "depth6_physical_belt_count.json"
CYCLES5 = CERTIFICATES / "depth5_low_slack_cycles.json"
OUTPUT = CERTIFICATES / "depth7_full_cover_probe.json"
N = 16
TARGET_WASTAGE = 40
OLD_DEPTH = 6
NEW_DEPTH = 7
INF = 30_000
State = tuple[int, int]

for directory in (BOUNDARY, HERE):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_depth5_ring import path_matrix  # noqa: E402
from count_depth6_physical_belts import (  # noqa: E402
    lift_retained_physical_corners,
    path_counts,
)
from enumerate_depth5_cycles import enumerate_cycles  # noqa: E402
from probe_depth6_low_slack import (  # noqa: E402
    configure,
    edge_payload,
    enumerate_relevant_depth5_corners,
    full_corner_valid,
    lift_edges,
    mask_from_row,
)


def filter_arc_feasible_depth6_corners(
    by_outgoing: dict[State, list[dict[str, Any]]],
    edges: Sequence[kernel.Edge],
    source_states: Sequence[State],
    arc_rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    adjacency: dict[State, list[kernel.Edge]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source].append(edge)
    by_target: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for row in arc_rows:
        by_target[int(row["target_index"])].append(
            (int(row["source_index"]), int(row["minimum_charge"]))
        )
    path_minimum: dict[int, dict[State, int]] = {}
    for number, source_index in enumerate(
        sorted({source for rows in by_target.values() for source, _ in rows}),
        start=1,
    ):
        counts = path_counts(source_states[source_index], adjacency)
        minimum: dict[State, int] = {}
        for (state, cost), count in counts.items():
            if not count:
                continue
            incumbent = minimum.get(state)
            if incumbent is None or cost < incumbent:
                minimum[state] = cost
        path_minimum[source_index] = minimum
        if number % 50 == 0:
            print(
                f"path minima {number}/{len(path_minimum) + 1}",
                file=sys.stderr,
                flush=True,
            )

    state_index = {state: index for index, state in enumerate(source_states)}
    retained = []
    rejected = 0
    key_set: set[tuple[State, State, int]] = set()
    for outgoing, patches in by_outgoing.items():
        target_index = state_index[outgoing]
        target_arcs = by_target[target_index]
        for patch in patches:
            incoming = tuple(patch["incoming"])
            corner_cost = int(patch["cost"])
            feasible = any(
                path_minimum[source].get(incoming, INF) + corner_cost
                <= arc_minimum + 2
                for source, arc_minimum in target_arcs
            )
            if not feasible:
                rejected += 1
                continue
            retained.append(patch)
            key_set.add((incoming, outgoing, corner_cost))
    retained.sort(
        key=lambda row: (
            row["incoming"],
            row["outgoing"],
            row["cost"],
            row["patch"],
        )
    )
    return retained, {
        "input_distinct_physical_corner_count": sum(
            len(rows) for rows in by_outgoing.values()
        ),
        "rejected_by_all_supported_arc_budgets": rejected,
        "retained_arc_feasible_physical_corner_count": len(retained),
        "retained_endpoint_cost_key_count": len(key_set),
        "retained_physical_corner_sha256": hashlib.sha256(
            json.dumps(
                retained, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
        ).hexdigest(),
        "safe_filter": (
            "A full ring of depth-six charge <=40 has abstract baseline "
            "at least 38, so no one side realization can exceed its "
            "minimum by more than two. A corner is retained whenever any "
            "supported incoming side source can reach it within that "
            "two-unit allowance."
        ),
    }


def lift_edges_generic(
    old_depth: int, old_edges: Sequence[kernel.Edge]
) -> tuple[list[State], list[kernel.Edge], dict[str, Any]]:
    new_depth = old_depth + 1
    configure(new_depth)
    lifted: set[tuple[State, State, int]] = set()
    attempted = 0
    q_histogram = Counter()
    for old_edge in old_edges:
        left_old, middle_old, right_old, old_weight = edge_payload(
            old_edge
        )
        for high_left, high_middle, high_right in product(
            (0, 1), repeat=3
        ):
            attempted += 1
            shift = old_depth + 1
            left = left_old | (high_left << shift)
            middle = middle_old | (high_middle << shift)
            right = right_old | (high_right << shift)
            if not kernel.transition_valid(left, middle, right):
                continue
            weight = int(
                kernel.transition_weight(left, middle, right)
            )
            added = weight - old_weight
            if added < 0:
                raise AssertionError("edge charge decreased under lift")
            q_histogram[added] += 1
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
        "attempted_high_bit_extensions": attempted,
        "valid_extension_histogram_by_added_charge": {
            str(charge): count
            for charge, count in sorted(q_histogram.items())
        },
        "edge_state_count": len(nodes),
        "edge_transition_count": len(edges),
        "edge_sha256": hashlib.sha256(
            json.dumps(
                [
                    [*edge.source, edge.target[1], edge.weight]
                    for edge in edges
                ],
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest(),
    }


def lift_minimum_corners_generic(
    old_depth: int,
    old_patches: Sequence[dict[str, Any]],
    old_edges: Sequence[kernel.Edge],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    incoming_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    outgoing_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    for edge in old_edges:
        incoming_edges[edge.target].append(edge)
        outgoing_edges[edge.source].append(edge)
    new_depth = old_depth + 1
    configure(new_depth)
    best: dict[tuple[State, State], tuple[int, tuple[str, ...]]] = {}
    attempted = 0
    valid = 0
    added_histogram = Counter()
    for patch_number, mapping in enumerate(old_patches, start=1):
        base_rows = [mask_from_row(row) for row in mapping["patch"]]
        incoming = tuple(mapping["incoming"])
        outgoing = tuple(mapping["outgoing"])
        for last_edge, first_edge, diagonal in product(
            incoming_edges[incoming],
            outgoing_edges[outgoing],
            (0, 1),
        ):
            attempted += 1
            last_left, last_middle, last_right, last_weight = edge_payload(
                last_edge
            )
            first_left, first_middle, first_right, first_weight = (
                edge_payload(first_edge)
            )
            high = old_depth + 1
            rows = [
                base_rows[row]
                | (((first_right >> row) & 1) << high)
                for row in range(old_depth + 1)
            ]
            rows.append(last_left | (diagonal << high))
            if not full_corner_valid(rows, new_depth):
                continue
            cost = int(kernel.patch_cost(rows))
            base = int(mapping["cost"]) + last_weight + first_weight
            added = cost - base
            if added < 0:
                raise AssertionError("corner charge decreased under lift")
            valid += 1
            added_histogram[added] += 1
            incoming_new, outgoing_new = kernel.corner_states(rows)
            rendered = tuple(kernel.render_rows(rows))
            key = (incoming_new, outgoing_new)
            candidate = (cost, rendered)
            incumbent = best.get(key)
            if incumbent is None or candidate < incumbent:
                best[key] = candidate
        if patch_number % 10_000 == 0:
            print(
                f"depth7 corner lift {patch_number}/{len(old_patches)} "
                f"attempted={attempted} valid={valid} maps={len(best)}",
                file=sys.stderr,
                flush=True,
            )
    relation = [
        {
            "incoming": list(incoming),
            "outgoing": list(outgoing),
            "cost": cost,
            "representative_patch": list(rendered),
        }
        for (incoming, outgoing), (cost, rendered) in sorted(best.items())
    ]
    return relation, {
        "attempted_adjacent_edge_and_diagonal_combinations": attempted,
        "raw_valid_physical_corner_count": valid,
        "valid_histogram_by_added_corner_charge": {
            str(charge): count
            for charge, count in sorted(added_histogram.items())
        },
        "minimum_corner_mapping_count": len(relation),
        "minimum_corner_output_state_count": len(
            {tuple(row["outgoing"]) for row in relation}
        ),
        "minimum_relation_sha256": hashlib.sha256(
            json.dumps(
                relation, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
        ).hexdigest(),
    }


def build() -> dict[str, Any]:
    probe6 = json.loads(PROBE6.read_text(encoding="utf-8"))
    count6 = json.loads(COUNT6.read_text(encoding="utf-8"))
    source_states6 = [
        tuple(state)
        for state in probe6["depth6_language"]["corner_output_states"]
    ]
    supported_outgoing6 = {
        source_states6[int(arc[1])]
        for arc in probe6["supported_directed_arcs"]
    }

    configure(5)
    nodes5, edges5 = kernel.build_edge_graph()
    relation5, _statistics = kernel.build_corner_relation(set(nodes5))
    sources5 = sorted(
        {tuple(row["outgoing"]) for row in relation5}
    )
    cycles5 = json.loads(CYCLES5.read_text(encoding="utf-8"))
    retained_outgoing5 = {
        sources5[int(arc[1])]
        for arc in cycles5["supported_directed_arcs"]
    }
    patches5, patch5_statistics = enumerate_relevant_depth5_corners(
        set(nodes5), retained_outgoing5
    )
    nodes6, edges6, edge6_statistics = lift_edges(edges5)
    by_outgoing6, physical6_statistics = (
        lift_retained_physical_corners(
            patches5, edges5, supported_outgoing6
        )
    )
    patches6, feasible6_statistics = (
        filter_arc_feasible_depth6_corners(
            by_outgoing6,
            edges6,
            source_states6,
            count6["physical_arc_rows"],
        )
    )

    nodes7, edges7, edge7_statistics = lift_edges_generic(
        OLD_DEPTH, edges6
    )
    relation7, corner7_statistics = lift_minimum_corners_generic(
        OLD_DEPTH, patches6, edges6
    )
    sources7 = sorted(
        {tuple(row["outgoing"]) for row in relation7}
    )
    if set(sources7) - set(nodes7):
        raise AssertionError("depth-seven corner output absent from edge graph")
    edge_length = N - 2 * NEW_DEPTH
    paths7 = path_matrix(nodes7, edges7, sources7, edge_length)
    transfer7 = side_transfer(paths7, relation7, nodes7, sources7)
    cycles7, anchor7 = enumerate_cycles(transfer7)
    arcs7 = {
        (cycle[index], cycle[(index + 1) % 4])
        for cycle in cycles7
        for index in range(4)
    }
    charge_histogram = Counter(cycles7.values())
    result = {
        "schema": "n16-depth7-full-cover-safe-probe-v1",
        "n": N,
        "depth": NEW_DEPTH,
        "edge_length": edge_length,
        "unresolved_centre_side": N - 2 * (NEW_DEPTH + 1),
        "target_population": 134,
        "target_total_wastage": TARGET_WASTAGE,
        "depth5_patch_filter": patch5_statistics,
        "depth6_edge_rebuild": edge6_statistics,
        "depth6_supported_physical_corner_rebuild": physical6_statistics,
        "depth6_arc_feasible_corner_filter": feasible6_statistics,
        "depth7_edge_lift": edge7_statistics,
        "depth7_corner_lift": corner7_statistics,
        "depth7_language": {
            "edge_state_count": len(nodes7),
            "edge_transition_count": len(edges7),
            "corner_output_state_count": len(sources7),
            "corner_output_states": [list(state) for state in sources7],
            "minimum_corner_mapping_count": len(relation7),
        },
        "path_matrix_finite_count": int(np.count_nonzero(paths7 < INF)),
        "path_matrix_sha256": hashlib.sha256(paths7.tobytes()).hexdigest(),
        "side_transfer_finite_count": int(
            np.count_nonzero(transfer7 < INF)
        ),
        "side_transfer_sha256": hashlib.sha256(
            transfer7.tobytes()
        ).hexdigest(),
        "anchor_enumeration": anchor7,
        "cycle_count_modulo_rotation_at_most_40": len(cycles7),
        "cycle_minimum_charge_histogram": {
            str(charge): count
            for charge, count in sorted(charge_histogram.items())
        },
        "supported_directed_arc_count": len(arcs7),
        "supported_directed_arcs": [list(arc) for arc in sorted(arcs7)],
        "cycles_modulo_rotation": [
            {"states": list(cycle), "minimum_charge": charge}
            for cycle, charge in sorted(cycles7.items())
        ],
        "population_134_excluded_by_safe_depth7_full_cover": not bool(
            cycles7
        ),
        "claim_scope": (
            "Depth seven plus its halo covers all 16 board cells. Every "
            "charge<=40 board projects to a supported depth-six ring and "
            "uses only corners retained by the safe per-arc two-slack "
            "filter. Adjacent edges are deliberately overapproximated. "
            "If abstract cycles survive, their physical compatibility and "
            "connectivity still require expansion."
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
            raise SystemExit("stored depth-seven full-cover probe differs")
        print(
            "VERIFIED",
            record["cycle_count_modulo_rotation_at_most_40"],
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
                "depth6_feasible_corner_filter": record[
                    "depth6_arc_feasible_corner_filter"
                ],
                "depth7_language": record["depth7_language"],
                "depth7_corner_lift": record["depth7_corner_lift"],
                "cycles": record[
                    "cycle_count_modulo_rotation_at_most_40"
                ],
                "charge_histogram": record[
                    "cycle_minimum_charge_histogram"
                ],
                "population_134_excluded": record[
                    "population_134_excluded_by_safe_depth7_full_cover"
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
