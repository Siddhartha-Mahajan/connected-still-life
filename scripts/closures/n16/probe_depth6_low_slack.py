#!/usr/bin/env python3
"""Build a complete safe depth-six n=16 low-slack annulus language."""

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
CYCLES5 = CERTIFICATES / "depth5_low_slack_cycles.json"
OUTPUT = CERTIFICATES / "depth6_low_slack_probe.json"
N = 16
OLD_DEPTH = 5
NEW_DEPTH = 6
TARGET_WASTAGE = 40
INF = 30_000
State = tuple[int, int]

for directory in (BOUNDARY, HERE):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_depth5_ring import path_matrix  # noqa: E402
from enumerate_depth5_cycles import enumerate_cycles  # noqa: E402


def configure(depth: int) -> None:
    kernel.CHARGED_DEPTH = depth
    kernel.MASK_BITS = depth + 1
    kernel.MASK_LIMIT = 1 << (depth + 1)
    kernel.PATCH_SIZE = depth + 1


def mask_from_row(row: str) -> int:
    return sum(
        (character == "1") << column
        for column, character in enumerate(row)
    )


def column_mask(
    rows: Sequence[int], column: int, height: int
) -> int:
    return sum(
        ((rows[row] >> column) & 1) << row for row in range(height)
    )


def full_corner_valid(rows: Sequence[int], depth: int) -> bool:
    if len(rows) != depth + 1:
        return False
    if not kernel.north_exterior_valid(rows[0]):
        return False
    if any(
        kernel.rows_have_block(rows[index], rows[index + 1])
        for index in range(depth)
    ):
        return False
    return all(
        kernel.completed_center_row_valid(rows, center)
        for center in range(depth)
    )


def edge_payload(edge: kernel.Edge) -> tuple[int, int, int, int]:
    return (*edge.source, edge.target[1], int(edge.weight))


def enumerate_relevant_depth5_corners(
    valid_states: set[State], retained_outgoing: set[State]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    configure(OLD_DEPTH)
    patches = []
    valid_patch_count = 0
    extendible_patch_count = 0

    def visit(rows: list[int]) -> None:
        nonlocal valid_patch_count, extendible_patch_count
        if len(rows) == OLD_DEPTH + 1:
            valid_patch_count += 1
            incoming, outgoing = kernel.corner_states(rows)
            if incoming not in valid_states or outgoing not in valid_states:
                return
            extendible_patch_count += 1
            if outgoing not in retained_outgoing:
                return
            patches.append(
                {
                    "incoming": incoming,
                    "outgoing": outgoing,
                    "cost": kernel.patch_cost(rows),
                    "patch": tuple(kernel.render_rows(rows)),
                }
            )
            return
        for following in range(kernel.MASK_LIMIT):
            if not rows and not kernel.north_exterior_valid(following):
                continue
            if rows and kernel.rows_have_block(rows[-1], following):
                continue
            candidate = [*rows, following]
            if len(candidate) >= 2:
                center = len(candidate) - 2
                if not kernel.completed_center_row_valid(
                    candidate, center
                ):
                    continue
            visit(candidate)

    visit([])
    patches.sort(
        key=lambda row: (
            row["incoming"],
            row["outgoing"],
            row["cost"],
            row["patch"],
        )
    )
    return patches, {
        "valid_physical_depth5_patch_count": valid_patch_count,
        "extendible_physical_depth5_patch_count": extendible_patch_count,
        "retained_relevant_depth5_patch_count": len(patches),
        "retained_depth5_patch_sha256": hashlib.sha256(
            json.dumps(
                patches, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
        ).hexdigest(),
    }


def lift_edges(
    old_edges: Sequence[kernel.Edge],
) -> tuple[list[State], list[kernel.Edge], dict[str, Any]]:
    configure(NEW_DEPTH)
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
            shift = OLD_DEPTH + 1
            left = left_old | (high_left << shift)
            middle = middle_old | (high_middle << shift)
            right = right_old | (high_right << shift)
            if not kernel.transition_valid(left, middle, right):
                continue
            new_weight = kernel.transition_weight(left, middle, right)
            added = new_weight - old_weight
            if added < 0:
                raise AssertionError("depth lift reduced an edge charge")
            q_histogram[added] += 1
            lifted.add(
                ((left, middle), (middle, right), int(new_weight))
            )
    edges = [
        kernel.Edge(source, target, weight)
        for source, target, weight in sorted(lifted)
    ]
    nodes = sorted(
        {edge.source for edge in edges}
        | {edge.target for edge in edges}
    )
    payload = [
        [*edge.source, edge.target[1], edge.weight] for edge in edges
    ]
    return nodes, edges, {
        "attempted_high_bit_extensions": attempted,
        "raw_valid_extension_histogram_by_added_charge": {
            str(charge): count
            for charge, count in sorted(q_histogram.items())
        },
        "lifted_edge_state_count": len(nodes),
        "lifted_edge_transition_count": len(edges),
        "lifted_edge_sha256": hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode("ascii")
        ).hexdigest(),
    }


def lift_corners(
    old_patches: Sequence[dict[str, Any]],
    old_edges: Sequence[kernel.Edge],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    incoming_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    outgoing_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    for edge in old_edges:
        incoming_edges[edge.target].append(edge)
        outgoing_edges[edge.source].append(edge)
    configure(NEW_DEPTH)
    best: dict[tuple[State, State], tuple[int, tuple[str, ...]]] = {}
    attempted = 0
    valid = 0
    added_histogram = Counter()
    physical_digest = hashlib.sha256()
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
            if (last_middle, last_right) != incoming:
                raise AssertionError("bad incoming edge")
            if (first_left, first_middle) != outgoing:
                raise AssertionError("bad outgoing edge")
            high = OLD_DEPTH + 1
            rows = [
                base_rows[row]
                | (((first_right >> row) & 1) << high)
                for row in range(OLD_DEPTH + 1)
            ]
            rows.append(last_left | (diagonal << high))
            if not full_corner_valid(rows, NEW_DEPTH):
                continue
            cost = kernel.patch_cost(rows)
            base = int(mapping["cost"]) + last_weight + first_weight
            added = cost - base
            if added < 0:
                raise AssertionError("corner lift reduced charge")
            valid += 1
            added_histogram[added] += 1
            incoming_new, outgoing_new = kernel.corner_states(rows)
            rendered = tuple(kernel.render_rows(rows))
            physical_digest.update(
                json.dumps(
                    [
                        list(incoming_new),
                        list(outgoing_new),
                        cost,
                        list(rendered),
                    ],
                    separators=(",", ":"),
                ).encode("ascii")
            )
            key = (incoming_new, outgoing_new)
            candidate = (cost, rendered)
            incumbent = best.get(key)
            if incumbent is None or candidate < incumbent:
                best[key] = candidate
        if patch_number % 10_000 == 0:
            print(
                f"corner patches {patch_number}/{len(old_patches)} "
                f"attempted={attempted} valid={valid}",
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
        "raw_valid_physical_depth6_corner_count": valid,
        "raw_valid_histogram_by_added_corner_charge": {
            str(charge): count
            for charge, count in sorted(added_histogram.items())
        },
        "minimum_depth6_corner_mapping_count": len(relation),
        "minimum_depth6_corner_output_state_count": len(
            {tuple(row["outgoing"]) for row in relation}
        ),
        "raw_physical_stream_sha256": physical_digest.hexdigest(),
        "minimum_relation_sha256": hashlib.sha256(
            json.dumps(
                relation, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
        ).hexdigest(),
    }


def build() -> dict[str, Any]:
    cycle5 = json.loads(CYCLES5.read_text(encoding="utf-8"))
    configure(OLD_DEPTH)
    old_nodes, old_edges = kernel.build_edge_graph()
    old_relation, _statistics = kernel.build_corner_relation(set(old_nodes))
    old_sources = sorted(
        {tuple(row["outgoing"]) for row in old_relation}
    )
    retained_outgoing = {
        old_sources[int(arc[1])]
        for arc in cycle5["supported_directed_arcs"]
    }
    old_patches, patch_statistics = enumerate_relevant_depth5_corners(
        set(old_nodes), retained_outgoing
    )
    nodes, edges, edge_statistics = lift_edges(old_edges)
    relation, corner_statistics = lift_corners(old_patches, old_edges)
    sources = sorted({tuple(row["outgoing"]) for row in relation})
    missing = set(sources) - set(nodes)
    if missing:
        raise AssertionError("lifted corner output absent from edge graph")
    edge_length = N - 2 * NEW_DEPTH
    paths = path_matrix(nodes, edges, sources, edge_length)
    transfer = side_transfer(paths, relation, nodes, sources)
    cycles, anchor = enumerate_cycles(transfer)
    arcs = {
        (cycle[index], cycle[(index + 1) % 4])
        for cycle in cycles
        for index in range(4)
    }
    charge_histogram = Counter(cycles.values())
    result = {
        "schema": "n16-depth6-low-slack-safe-probe-v1",
        "n": N,
        "depth": NEW_DEPTH,
        "edge_length": edge_length,
        "target_population": 134,
        "target_total_wastage": TARGET_WASTAGE,
        "depth5_cycle_certificate_sha256": hashlib.sha256(
            CYCLES5.read_bytes()
        ).hexdigest(),
        "depth5_physical_corner_filter": patch_statistics,
        "depth6_edge_lift": edge_statistics,
        "depth6_corner_lift": corner_statistics,
        "depth6_language": {
            "edge_state_count": len(nodes),
            "edge_transition_count": len(edges),
            "corner_output_state_count": len(sources),
            "minimum_corner_mapping_count": len(relation),
            "corner_output_states": [list(state) for state in sources],
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
        "cycle_count_modulo_rotation_at_most_40": len(cycles),
        "cycle_minimum_charge_histogram": {
            str(charge): count
            for charge, count in sorted(charge_histogram.items())
        },
        "supported_directed_arc_count": len(arcs),
        "supported_directed_arcs": [list(arc) for arc in sorted(arcs)],
        "cycles_modulo_rotation": [
            {"states": list(cycle), "minimum_charge": charge}
            for cycle, charge in sorted(cycles.items())
        ],
        "population_134_excluded_by_safe_depth6_probe": not bool(cycles),
        "claim_scope": (
            "Every depth-six ring of total charge <=40 projects to a "
            "depth-five ring in the complete saved <=40 support. All "
            "physical depth-five corners with a supported outgoing state "
            "and all adjacent edges are allowed, so this is a safe "
            "overapproximation. If cycles survive, physical compatibility "
            "and the central 2x2 remain unresolved."
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
            raise SystemExit("stored depth-six probe differs")
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
                "language": record["depth6_language"],
                "corner_lift": record["depth6_corner_lift"],
                "cycles": record[
                    "cycle_count_modulo_rotation_at_most_40"
                ],
                "charge_histogram": record[
                    "cycle_minimum_charge_histogram"
                ],
                "population_134_excluded": record[
                    "population_134_excluded_by_safe_depth6_probe"
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
