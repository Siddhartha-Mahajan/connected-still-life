#!/usr/bin/env python3
"""Count all physical depth-six n=16 belts through total charge 40."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from itertools import product
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BOUNDARY = ROOT / "scripts" / "boundary"
CERTIFICATES = ROOT / "certificates" / "exact_closures" / "n16"
PROBE = CERTIFICATES / "depth6_low_slack_probe.json"
OUTPUT = CERTIFICATES / "depth6_physical_belt_count.json"
N = 16
OLD_DEPTH = 5
NEW_DEPTH = 6
EDGE_LENGTH = 4
TARGET_WASTAGE = 40
MAX_INCREMENT = 2
MAX_TOTAL_ARC_COST = 24
State = tuple[int, int]

for directory in (BOUNDARY, HERE):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import depth4_boundary_census as kernel  # noqa: E402
from probe_depth6_low_slack import (  # noqa: E402
    configure,
    edge_payload,
    enumerate_relevant_depth5_corners,
    full_corner_valid,
    lift_edges,
    mask_from_row,
)


def lift_retained_physical_corners(
    old_patches: Sequence[dict[str, Any]],
    old_edges: Sequence[kernel.Edge],
    retained_outgoing: set[State],
) -> tuple[
    dict[State, list[dict[str, Any]]],
    dict[str, Any],
]:
    incoming_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    outgoing_edges: dict[State, list[kernel.Edge]] = defaultdict(list)
    for edge in old_edges:
        incoming_edges[edge.target].append(edge)
        outgoing_edges[edge.source].append(edge)
    configure(NEW_DEPTH)
    unique: set[tuple[State, State, int, tuple[str, ...]]] = set()
    attempted = 0
    raw_valid = 0
    retained_raw = 0
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
            high = OLD_DEPTH + 1
            rows = [
                base_rows[row]
                | (((first_right >> row) & 1) << high)
                for row in range(OLD_DEPTH + 1)
            ]
            rows.append(last_left | (diagonal << high))
            if not full_corner_valid(rows, NEW_DEPTH):
                continue
            raw_valid += 1
            incoming_new, outgoing_new = kernel.corner_states(rows)
            if outgoing_new not in retained_outgoing:
                continue
            retained_raw += 1
            cost = kernel.patch_cost(rows)
            base = int(mapping["cost"]) + last_weight + first_weight
            if cost < base:
                raise AssertionError("corner charge decreased under lift")
            rendered = tuple(kernel.render_rows(rows))
            unique.add(
                (incoming_new, outgoing_new, int(cost), rendered)
            )
        if patch_number % 10_000 == 0:
            print(
                f"corner patches {patch_number}/{len(old_patches)} "
                f"retained_raw={retained_raw} unique={len(unique)}",
                file=sys.stderr,
                flush=True,
            )

    by_outgoing: dict[State, list[dict[str, Any]]] = defaultdict(list)
    for incoming, outgoing, cost, rendered in sorted(unique):
        by_outgoing[outgoing].append(
            {
                "incoming": incoming,
                "outgoing": outgoing,
                "cost": cost,
                "patch": rendered,
            }
        )
    digest_rows = [
        [
            list(incoming),
            list(outgoing),
            cost,
            list(rendered),
        ]
        for incoming, outgoing, cost, rendered in sorted(unique)
    ]
    return by_outgoing, {
        "attempted_context_count": attempted,
        "raw_valid_context_count": raw_valid,
        "raw_retained_context_count": retained_raw,
        "distinct_retained_physical_corner_count": len(unique),
        "retained_outgoing_state_count": len(by_outgoing),
        "retained_physical_corner_sha256": hashlib.sha256(
            json.dumps(digest_rows, separators=(",", ":")).encode("ascii")
        ).hexdigest(),
    }


def path_counts(
    source: State,
    adjacency: dict[State, list[kernel.Edge]],
) -> Counter[tuple[State, int]]:
    current: Counter[tuple[State, int]] = Counter({(source, 0): 1})
    for _step in range(EDGE_LENGTH):
        following: Counter[tuple[State, int]] = Counter()
        for (state, cost), count in current.items():
            for edge in adjacency[state]:
                total = cost + int(edge.weight)
                if total <= MAX_TOTAL_ARC_COST:
                    following[(edge.target, total)] += count
        current = following
    return current


def convolution_count(
    buckets: Sequence[Counter[int]], allowance: int
) -> tuple[int, Counter[int]]:
    totals: Counter[int] = Counter({0: 1})
    for bucket in buckets:
        following: Counter[int] = Counter()
        for old_increment, old_count in totals.items():
            for increment, count in bucket.items():
                total = old_increment + increment
                if total <= allowance:
                    following[total] += old_count * count
        totals = following
    return sum(totals.values()), totals


def build() -> dict[str, Any]:
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    source_states = [
        tuple(state)
        for state in probe["depth6_language"]["corner_output_states"]
    ]
    supported_arcs = [
        (int(arc[0]), int(arc[1]))
        for arc in probe["supported_directed_arcs"]
    ]
    cycles = [
        (
            tuple(int(value) for value in row["states"]),
            int(row["minimum_charge"]),
        )
        for row in probe["cycles_modulo_rotation"]
    ]
    retained_depth6_outgoing = {
        source_states[target] for _source, target in supported_arcs
    }

    configure(OLD_DEPTH)
    old_nodes, old_edges = kernel.build_edge_graph()
    old_relation, _statistics = kernel.build_corner_relation(set(old_nodes))
    old_sources = sorted(
        {tuple(row["outgoing"]) for row in old_relation}
    )
    cycle5 = json.loads(
        (
            CERTIFICATES / "depth5_low_slack_cycles.json"
        ).read_text(encoding="utf-8")
    )
    retained_depth5_outgoing = {
        old_sources[int(arc[1])]
        for arc in cycle5["supported_directed_arcs"]
    }
    old_patches, old_patch_statistics = (
        enumerate_relevant_depth5_corners(
            set(old_nodes), retained_depth5_outgoing
        )
    )
    nodes, edges, edge_statistics = lift_edges(old_edges)
    by_outgoing, corner_statistics = lift_retained_physical_corners(
        old_patches, old_edges, retained_depth6_outgoing
    )
    if set(by_outgoing) != retained_depth6_outgoing:
        missing = retained_depth6_outgoing - set(by_outgoing)
        raise AssertionError(
            f"retained output states lack physical corners: {missing}"
        )

    adjacency: dict[State, list[kernel.Edge]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source].append(edge)
    for edge_rows in adjacency.values():
        edge_rows.sort(key=lambda edge: (edge.target, edge.weight))
    arcs_by_source: dict[int, list[int]] = defaultdict(list)
    for source, target in supported_arcs:
        arcs_by_source[source].append(target)

    arc_histograms: dict[tuple[int, int], Counter[int]] = {}
    arc_minima: dict[tuple[int, int], int] = {}
    maximum_path_context_count = 0
    for number, source_index in enumerate(sorted(arcs_by_source), start=1):
        counts = path_counts(source_states[source_index], adjacency)
        maximum_path_context_count = max(
            maximum_path_context_count, sum(counts.values())
        )
        by_incoming: dict[State, Counter[int]] = defaultdict(Counter)
        for (incoming, cost), count in counts.items():
            by_incoming[incoming][cost] += count
        for target_index in sorted(arcs_by_source[source_index]):
            outgoing = source_states[target_index]
            totals: Counter[int] = Counter()
            for corner in by_outgoing[outgoing]:
                incoming = tuple(corner["incoming"])
                corner_cost = int(corner["cost"])
                for path_cost, path_count in by_incoming[incoming].items():
                    total = path_cost + corner_cost
                    if total <= MAX_TOTAL_ARC_COST:
                        totals[total] += path_count
            if not totals:
                raise AssertionError(
                    f"supported arc {(source_index, target_index)} "
                    "has no physical realization"
                )
            minimum = min(totals)
            arc = (source_index, target_index)
            arc_minima[arc] = minimum
            arc_histograms[arc] = Counter(
                {
                    total - minimum: count
                    for total, count in totals.items()
                    if total - minimum <= MAX_INCREMENT
                }
            )
        if number % 25 == 0:
            print(
                f"path sources {number}/{len(arcs_by_source)}",
                file=sys.stderr,
                flush=True,
            )

    combination_count = 0
    baseline_histogram: Counter[tuple[int, int]] = Counter()
    increment_histogram: Counter[int] = Counter()
    maximum_one_cycle = 0
    for cycle, saved_baseline in cycles:
        reconstructed_baseline = sum(
            arc_minima[
                (cycle[index], cycle[(index + 1) % 4])
            ]
            for index in range(4)
        )
        if reconstructed_baseline != saved_baseline:
            raise AssertionError(
                "physical arc minima disagree with saved transfer cycle"
            )
        allowance = TARGET_WASTAGE - saved_baseline
        buckets = [
            arc_histograms[
                (cycle[index], cycle[(index + 1) % 4])
            ]
            for index in range(4)
        ]
        count, by_increment = convolution_count(buckets, allowance)
        combination_count += count
        maximum_one_cycle = max(maximum_one_cycle, count)
        baseline_histogram[(saved_baseline, allowance)] += count
        increment_histogram.update(by_increment)

    arc_rows = [
        {
            "source_index": source,
            "target_index": target,
            "minimum_charge": arc_minima[(source, target)],
            "physical_realization_count_by_increment": {
                str(increment): count
                for increment, count in sorted(
                    arc_histograms[(source, target)].items()
                )
            },
        }
        for source, target in sorted(arc_histograms)
    ]
    result = {
        "schema": "n16-depth6-physical-belt-count-v1",
        "n": N,
        "depth": NEW_DEPTH,
        "edge_length": EDGE_LENGTH,
        "target_population": 134,
        "target_total_wastage": TARGET_WASTAGE,
        "depth6_probe_sha256": hashlib.sha256(
            PROBE.read_bytes()
        ).hexdigest(),
        "old_patch_filter": old_patch_statistics,
        "edge_lift": edge_statistics,
        "physical_corner_filter": corner_statistics,
        "abstract_cycle_count_modulo_rotation": len(cycles),
        "supported_directed_arc_count": len(supported_arcs),
        "supported_source_state_count": len(arcs_by_source),
        "maximum_length4_path_context_count_for_one_source": (
            maximum_path_context_count
        ),
        "physical_arc_rows": arc_rows,
        "physical_belt_combination_count_before_deduplication": (
            combination_count
        ),
        "maximum_physical_combinations_for_one_abstract_cycle": (
            maximum_one_cycle
        ),
        "physical_combination_histogram_by_baseline_and_allowance": {
            f"{baseline},{allowance}": count
            for (baseline, allowance), count in sorted(
                baseline_histogram.items()
            )
        },
        "physical_combination_histogram_by_total_increment": {
            str(increment): count
            for increment, count in sorted(increment_histogram.items())
        },
        "claim_scope": (
            "Exact count of distinct physical-corner/edge-path contexts "
            "for every safe depth-six abstract ring through total charge "
            "40. Physical belts are not yet assembled or deduplicated and "
            "the final 2x2 centre is not yet completed."
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
            raise SystemExit("stored depth-six physical count differs")
        print(
            "VERIFIED",
            record[
                "physical_belt_combination_count_before_deduplication"
            ],
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
                "physical_corner_filter": record[
                    "physical_corner_filter"
                ],
                "physical_belt_combinations": record[
                    "physical_belt_combination_count_before_deduplication"
                ],
                "by_baseline": record[
                    "physical_combination_histogram_by_baseline_and_allowance"
                ],
                "maximum_for_one_cycle": record[
                    "maximum_physical_combinations_for_one_abstract_cycle"
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
