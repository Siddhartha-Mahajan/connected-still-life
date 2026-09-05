#!/usr/bin/env python3
"""Enumerate every physical depth-four n=14 belt of total charge <=36.

Unlike enumerate_minimum_belts.py, this expands all tied minimum realizations
and every realization up to two charge units above an abstract arc minimum.
That is complete because the global depth-four lower bound is 34 and a
103-cell n=14 still life has total Chu--Stuckey wastage 36.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BOUNDARY = ROOT / "scripts" / "boundary"
CERTIFICATES = ROOT / "certificates" / "exact_closures" / "n14"
OUTPUT = CERTIFICATES / "all_low_slack_belt_census.json"
WITNESS = CERTIFICATES / "population103_candidate.json"
N = 14
DEPTH = 4
EDGE_LENGTH = 6
TARGET = 103
TOTAL_WASTAGE = 36
INF = 10**7
State = tuple[int, int]

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(BOUNDARY) not in sys.path:
    sys.path.insert(0, str(BOUNDARY))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import (  # noqa: E402
    restricted_path_matrices,
    side_transfer,
)
from enumerate_minimum_belts import (  # noqa: E402
    assemble,
    audit_belt,
    canonical_rotation,
    connected_components,
    enumerate_cycles,
    fill_mask,
    frame_key,
    grid_digest,
    stable_center_masks,
    verify_grid,
)


def full_corner_patches(
    valid_states: set[State],
) -> dict[State, list[dict[str, Any]]]:
    """All 14,225 extendible physical corner patches, without collapsing."""

    by_outgoing: dict[State, list[dict[str, Any]]] = defaultdict(list)

    def visit(rows: list[int]) -> None:
        if len(rows) == kernel.PATCH_SIZE:
            incoming, outgoing = kernel.corner_states(rows)
            if incoming in valid_states and outgoing in valid_states:
                by_outgoing[outgoing].append(
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
                center_row = len(candidate) - 2
                if not kernel.completed_center_row_valid(
                    candidate, center_row
                ):
                    continue
            visit(candidate)

    visit([])
    for patches in by_outgoing.values():
        patches.sort(
            key=lambda row: (row["cost"], row["incoming"], row["patch"])
        )
    return by_outgoing


def dense_suffix_layers(
    nodes: list[State],
    edges: list[kernel.Edge],
) -> list[np.ndarray]:
    """Exact length-r all-pairs costs, r=0..6, in about nine MiB."""

    node_index = {state: index for index, state in enumerate(nodes)}
    zero = np.full((len(nodes), len(nodes)), 1000, dtype=np.int16)
    np.fill_diagonal(zero, 0)
    layers = [zero]
    indexed_edges = [
        (node_index[edge.source], node_index[edge.target], edge.weight)
        for edge in edges
    ]
    for _ in range(EDGE_LENGTH):
        previous = layers[-1]
        following = np.full_like(previous, 1000)
        for source, target, weight in indexed_edges:
            np.minimum(
                following[source, :],
                previous[target, :] + weight,
                out=following[source, :],
            )
        layers.append(following)
    return layers


class FullArcEnumerator:
    def __init__(
        self,
        nodes: list[State],
        edges: list[kernel.Edge],
        sources: list[State],
        paths: np.ndarray,
        transfer: np.ndarray,
        corners: dict[State, list[dict[str, Any]]],
        suffix: list[np.ndarray],
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.sources = sources
        self.paths = paths
        self.transfer = transfer
        self.corners = corners
        self.suffix = suffix
        self.node_index = {
            state: index for index, state in enumerate(nodes)
        }
        self.adjacency: dict[State, list[kernel.Edge]] = defaultdict(list)
        for edge in edges:
            self.adjacency[edge.source].append(edge)
        for rows in self.adjacency.values():
            rows.sort(key=lambda edge: (edge.target, edge.weight))
        self.path_cache: dict[
            tuple[State, State, int], tuple[tuple[tuple[int, ...], int], ...]
        ] = {}
        self.arc_cache: dict[
            tuple[int, int, int], tuple[dict[str, Any], ...]
        ] = {}

    def paths_at_most(
        self,
        source: State,
        target: State,
        maximum: int,
    ) -> tuple[tuple[tuple[int, ...], int], ...]:
        key = (source, target, maximum)
        if key in self.path_cache:
            return self.path_cache[key]
        target_index = self.node_index[target]
        results: list[tuple[tuple[int, ...], int]] = []

        def visit(
            state: State,
            remaining: int,
            cost: int,
            masks: tuple[int, ...],
        ) -> None:
            state_index = self.node_index[state]
            lower = int(
                self.suffix[remaining][state_index, target_index]
            )
            if cost + lower > maximum:
                return
            if remaining == 0:
                if state == target:
                    results.append((masks, cost))
                return
            for edge in self.adjacency[state]:
                following_lower = int(
                    self.suffix[remaining - 1][
                        self.node_index[edge.target], target_index
                    ]
                )
                if cost + edge.weight + following_lower > maximum:
                    continue
                visit(
                    edge.target,
                    remaining - 1,
                    cost + edge.weight,
                    (*masks, edge.target[1]),
                )

        visit(source, EDGE_LENGTH, 0, (source[0], source[1]))
        value = tuple(results)
        self.path_cache[key] = value
        return value

    def realizations(
        self,
        source_index: int,
        target_index: int,
        slack: int,
    ) -> tuple[dict[str, Any], ...]:
        key = (source_index, target_index, slack)
        if key in self.arc_cache:
            return self.arc_cache[key]
        source = self.sources[source_index]
        outgoing = self.sources[target_index]
        arc_minimum = int(self.transfer[source_index, target_index])
        maximum = arc_minimum + slack
        results = []
        for corner in self.corners[outgoing]:
            incoming = corner["incoming"]
            minimum_path = int(
                self.paths[
                    source_index, self.node_index[incoming]
                ]
            )
            if minimum_path >= INF:
                continue
            maximum_path = maximum - int(corner["cost"])
            if minimum_path > maximum_path:
                continue
            for masks, path_cost in self.paths_at_most(
                source, incoming, maximum_path
            ):
                cost = path_cost + int(corner["cost"])
                results.append(
                    {
                        "masks": masks,
                        "path_cost": path_cost,
                        "corner_cost": int(corner["cost"]),
                        "corner_patch": corner["patch"],
                        "arc_cost": cost,
                        "increment": cost - arc_minimum,
                    }
                )
        results.sort(
            key=lambda row: (
                row["increment"],
                row["masks"],
                row["corner_patch"],
            )
        )
        value = tuple(results)
        self.arc_cache[key] = value
        return value


def convolution_count(
    buckets: list[Counter[int]],
    allowance: int,
) -> int:
    totals = Counter({0: 1})
    for bucket in buckets:
        following = Counter()
        for old_cost, old_count in totals.items():
            for increment, count in bucket.items():
                if old_cost + increment <= allowance:
                    following[old_cost + increment] += old_count * count
        totals = following
    return sum(totals.values())


def build(
    *,
    census_only: bool,
    max_physical_belts: int | None,
) -> tuple[dict[str, Any], list[list[int]] | None]:
    nodes, edges = kernel.build_edge_graph()
    minimum_relation, _statistics = kernel.build_corner_relation(set(nodes))
    sources = sorted(
        {tuple(row["outgoing"]) for row in minimum_relation}
    )
    path_matrices, _period = restricted_path_matrices(
        nodes,
        edges,
        sources,
        {EDGE_LENGTH},
        period_search_limit=EDGE_LENGTH,
    )
    paths = path_matrices[EDGE_LENGTH]
    transfer = side_transfer(
        paths, minimum_relation, nodes, sources
    )
    cycles = enumerate_cycles(transfer)
    corners = full_corner_patches(set(nodes))
    corner_count = sum(map(len, corners.values()))
    if corner_count != 14225:
        raise AssertionError(
            f"full corner census has {corner_count}, expected 14225"
        )
    suffix = dense_suffix_layers(nodes, edges)
    enumerator = FullArcEnumerator(
        nodes, edges, sources, paths, transfer, corners, suffix
    )

    arc_keys = {
        (cycle[index], cycle[(index + 1) % 4])
        for cycle in cycles
        for index in range(4)
    }
    arc_variant_histograms: dict[tuple[int, int], Counter[int]] = {}
    for number, arc in enumerate(sorted(arc_keys), start=1):
        variants = enumerator.realizations(*arc, 2)
        histogram = Counter(
            int(row["increment"]) for row in variants
        )
        arc_variant_histograms[arc] = histogram
        if number % 500 == 0:
            print(
                f"arc {number}/{len(arc_keys)} "
                f"path-cache={len(enumerator.path_cache)}",
                file=sys.stderr,
                flush=True,
            )

    physical_combination_count = 0
    combination_histogram = Counter()
    for cycle, baseline in cycles.items():
        allowance = TOTAL_WASTAGE - baseline
        buckets = [
            arc_variant_histograms[
                (cycle[index], cycle[(index + 1) % 4])
            ]
            for index in range(4)
        ]
        count = convolution_count(buckets, allowance)
        physical_combination_count += count
        combination_histogram[(baseline, allowance)] += count

    distinct_belts: set[str] = set()
    stable_completions = 0
    connected_completions = 0
    component_histogram: Counter[tuple[int, ...]] = Counter()
    stable_grid_digests: list[str] = []
    stable_samples: list[dict[str, Any]] = []
    frame_cache: dict[tuple[tuple[int, ...], int], list[int]] = {}
    processed_combinations = 0
    witness = None
    stopped_at_limit = False

    if not census_only:
        for cycle_number, (cycle, baseline) in enumerate(
            sorted(cycles.items()), start=1
        ):
            allowance = TOTAL_WASTAGE - baseline
            side_variants = [
                enumerator.realizations(
                    cycle[index],
                    cycle[(index + 1) % 4],
                    allowance,
                )
                for index in range(4)
            ]
            for contexts in itertools.product(*side_variants):
                increment = sum(
                    int(context["increment"]) for context in contexts
                )
                if increment > allowance:
                    continue
                processed_combinations += 1
                if (
                    max_physical_belts is not None
                    and processed_combinations > max_physical_belts
                ):
                    stopped_at_limit = True
                    break
                belt = assemble(list(contexts))
                charge = baseline + increment
                audit_belt(belt, charge)
                digest = grid_digest(belt)
                if digest in distinct_belts:
                    continue
                distinct_belts.add(digest)
                belt_population = sum(
                    value
                    for row in belt
                    for value in row
                    if value >= 0
                )
                required = TARGET - belt_population
                key = (frame_key(belt), required)
                if key not in frame_cache:
                    frame_cache[key] = stable_center_masks(
                        belt, required
                    )
                for mask in frame_cache[key]:
                    stable_completions += 1
                    grid = fill_mask(belt, mask)
                    check = verify_grid(grid, claimed_cells=TARGET)
                    if not check.stable or check.population != TARGET:
                        raise AssertionError(check.to_dict())
                    components = connected_components(grid)
                    sizes = tuple(
                        sorted(
                            (
                                len(component)
                                for component in components
                            ),
                            reverse=True,
                        )
                    )
                    component_histogram[sizes] += 1
                    completion_digest = grid_digest(grid)
                    stable_grid_digests.append(completion_digest)
                    if len(stable_samples) < 12:
                        stable_samples.append(
                            {
                                "sha256": completion_digest,
                                "component_sizes": list(sizes),
                                "grid": [
                                    "".join(map(str, row))
                                    for row in grid
                                ],
                            }
                        )
                    if len(components) == 1:
                        connected_completions += 1
                        witness = grid
                        break
                if witness is not None:
                    break
            if (
                witness is not None
                or stopped_at_limit
            ):
                break
            if cycle_number % 100 == 0:
                print(
                    f"cycle {cycle_number}/{len(cycles)} "
                    f"physical={processed_combinations} "
                    f"belts={len(distinct_belts)} "
                    f"stable={stable_completions}",
                    file=sys.stderr,
                    flush=True,
                )

    variant_count_histogram = Counter()
    for histogram in arc_variant_histograms.values():
        variant_count_histogram[
            (
                histogram.get(0, 0),
                histogram.get(1, 0),
                histogram.get(2, 0),
            )
        ] += 1
    record = {
        "schema": "n14-all-depth4-belts-charge-at-most36-v1",
        "n": N,
        "target_population": TARGET,
        "target_total_wastage": TOTAL_WASTAGE,
        "language": {
            "edge_states": len(nodes),
            "edge_transitions": len(edges),
            "full_corner_patches": corner_count,
            "corner_output_states": len(sources),
            "edge_length": EDGE_LENGTH,
        },
        "abstract_cycles_mod_rotation": len(cycles),
        "abstract_cycle_baseline_histogram": {
            str(cost): count
            for cost, count in sorted(Counter(cycles.values()).items())
        },
        "supported_arc_count": len(arc_keys),
        "arc_variant_count_triples_increment_0_1_2": {
            ",".join(map(str, counts)): multiplicity
            for counts, multiplicity in sorted(
                variant_count_histogram.items()
            )
        },
        "physical_belt_combination_count_before_deduplication": (
            physical_combination_count
        ),
        "physical_combination_histogram_by_baseline_and_allowance": {
            f"{baseline},{allowance}": count
            for (baseline, allowance), count in sorted(
                combination_histogram.items()
            )
        },
        "census_only": census_only,
        "maximum_physical_belts": max_physical_belts,
        "processed_physical_combinations": processed_combinations,
        "stopped_at_limit": stopped_at_limit,
        "distinct_physical_belts_processed": len(distinct_belts),
        "distinct_frame_population_keys": len(frame_cache),
        "stable_population_103_completions_examined": stable_completions,
        "stable_completion_component_size_histogram": {
            ",".join(map(str, sizes)): count
            for sizes, count in sorted(component_histogram.items())
        },
        "stable_completion_grid_digest_sha256": hashlib.sha256(
            "".join(sorted(stable_grid_digests)).encode("ascii")
        ).hexdigest(),
        "stable_completion_samples": stable_samples,
        "connected_population_103_completions": connected_completions,
        "connected_witness_found": witness is not None,
        "completeness": (
            "Every physical depth-four belt of charge <=36 maps to an "
            "abstract minimum cycle of baseline >=34. For each supported "
            "arc, every length-six edge path and every one of the 14,225 "
            "physical corner patches through baseline+2 is enumerated. "
            "The four increments are retained exactly when their sum fits "
            "the global charge-36 budget. The remaining 4x4 centre is "
            "enumerated by an exact four-row transfer that validates all "
            "six affected rows; every stable completion is independently "
            "checked on the full board and classified by 8-connectivity."
        ),
        "record_sha256_excluding_this_field": None,
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record["record_sha256_excluding_this_field"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return record, witness


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--witness", type=Path, default=WITNESS)
    parser.add_argument("--census-only", action="store_true")
    parser.add_argument("--max-physical-belts", type=int)
    args = parser.parse_args()
    record, witness = build(
        census_only=args.census_only,
        max_physical_belts=args.max_physical_belts,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if witness is not None:
        args.witness.write_text(
            json.dumps(
                {
                    "n": N,
                    "claimed_cells": TARGET,
                    "grid": witness,
                    "source": (
                        "The complete low-slack depth-four belt "
                        "enumeration"
                    ),
                    "verification": verify_grid(
                        witness, claimed_cells=TARGET
                    ).to_dict(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps(record, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
