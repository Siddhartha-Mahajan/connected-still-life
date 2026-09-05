#!/usr/bin/env python3
"""Reconstruct and fill all minimum-representative n=14 low-charge belts.

The depth-four theorem leaves only a 4 x 4 centre.  This script enumerates
every abstract four-side cycle whose *minimum* physical boundary charge is at
most 36, quotients cyclic rotations, reconstructs a deterministic minimum
physical representative of every arc, and exhausts the 16 centre bits.

This is a witness search over the complete minimum-cost abstract cycle
support.  It is not yet an impossibility proof because an abstract arc can
have additional non-minimum physical realizations within the global charge
budget.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
BOUNDARY = PROJECT / "scripts" / "boundary"
CERTIFICATES = PROJECT / "certificates" / "exact_closures" / "n14"
OUTPUT = CERTIFICATES / "minimum_belt_census.json"
WITNESS = CERTIFICATES / "population103_candidate.json"
N = 14
DEPTH = 4
HALO = DEPTH + 1
EDGE_LENGTH = N - 2 * DEPTH
TARGET = 103
TOTAL_WASTAGE = 2 * N * N + 4 * N - 4 * TARGET
UNKNOWN = -1
INF = 10**7
State = tuple[int, int]
Grid = list[list[int]]

if str(BOUNDARY) not in sys.path:
    sys.path.insert(0, str(BOUNDARY))
if str(PROJECT / "verifiers") not in sys.path:
    sys.path.insert(0, str(PROJECT / "verifiers"))

from depth4_boundary_census import (  # noqa: E402
    Edge,
    build_corner_relation,
    build_edge_graph,
)
from certify_depth4_ring import (  # noqa: E402
    restricted_path_matrices,
    side_transfer,
)
from depth4_boundary_census import (  # noqa: E402
    chu_wastage,
    is_stable_pattern,
)
from life import connected_components, verify_grid  # noqa: E402


def canonical_rotation(cycle: tuple[int, ...]) -> tuple[int, ...]:
    return min(cycle[index:] + cycle[:index] for index in range(len(cycle)))


def enumerate_cycles(transfer: np.ndarray) -> dict[tuple[int, ...], int]:
    """All min-transfer four-cycles of charge at most TOTAL_WASTAGE."""

    finite = np.where(transfer < INF, transfer, 1000).astype(np.int32)
    cycles: dict[tuple[int, ...], int] = {}
    dimension = len(finite)

    # Every four-cycle of total cost <=36 has an arc of cost <=9.  Anchor
    # that arc, and use the exact two-arc return minimum to avoid scanning
    # the enormous Cartesian product of all intermediate states.
    two_step = np.full_like(finite, 1000)
    for middle in range(dimension):
        np.minimum(
            two_step,
            finite[:, middle, None] + finite[middle, None, :],
            out=two_step,
        )
    anchor_sources, anchor_targets = np.nonzero(finite <= 9)
    for first, second in zip(anchor_sources, anchor_targets):
        anchor_cost = int(finite[first, second])
        allowance = TOTAL_WASTAGE - anchor_cost
        opposite_candidates = np.flatnonzero(
            finite[second, :] + two_step[:, first] <= allowance
        )
        for opposite in opposite_candidates:
            remaining = allowance - int(finite[second, opposite])
            fourth_candidates = np.flatnonzero(
                finite[opposite, :] + finite[:, first] <= remaining
            )
            for fourth in fourth_candidates:
                charge = (
                    anchor_cost
                    + int(finite[second, opposite])
                    + int(finite[opposite, fourth])
                    + int(finite[fourth, first])
                )
                cycle = canonical_rotation(
                    (
                        int(first),
                        int(second),
                        int(opposite),
                        int(fourth),
                    )
                )
                old = cycles.get(cycle)
                if old is not None and old != charge:
                    raise AssertionError("cycle charge is inconsistent")
                cycles[cycle] = charge
    return cycles


def suffix_distances(
    nodes: list[State],
    edges: list[Edge],
    target: State,
) -> list[dict[State, int]]:
    incoming: dict[State, list[Edge]] = defaultdict(list)
    for edge in edges:
        incoming[edge.target].append(edge)
    distance: list[dict[State, int]] = [{target: 0}]
    for _ in range(EDGE_LENGTH):
        following: dict[State, int] = {}
        for reached, cost in distance[-1].items():
            for edge in incoming[reached]:
                candidate = cost + edge.weight
                incumbent = following.get(edge.source, INF)
                if candidate < incumbent:
                    following[edge.source] = candidate
        distance.append(following)
    return distance


class ArcReconstructor:
    def __init__(
        self,
        nodes: list[State],
        edges: list[Edge],
        relation: list[dict[str, Any]],
        sources: list[State],
        paths: np.ndarray,
        transfer: np.ndarray,
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.relation = relation
        self.sources = sources
        self.paths = paths
        self.transfer = transfer
        self.node_index = {
            state: index for index, state in enumerate(nodes)
        }
        self.outgoing_relation: dict[State, list[dict[str, Any]]] = (
            defaultdict(list)
        )
        for row in relation:
            self.outgoing_relation[tuple(row["outgoing"])].append(row)
        self.adjacency: dict[State, list[Edge]] = defaultdict(list)
        for edge in edges:
            self.adjacency[edge.source].append(edge)
        for rows in self.adjacency.values():
            rows.sort(key=lambda edge: (edge.target, edge.weight))
        self.arc_cache: dict[tuple[int, int], dict[str, Any]] = {}

    def reconstruct(self, source_index: int, target_index: int) -> dict[str, Any]:
        key = (source_index, target_index)
        if key in self.arc_cache:
            return self.arc_cache[key]
        source = self.sources[source_index]
        outgoing = self.sources[target_index]
        optimum = int(self.transfer[source_index, target_index])
        candidates = []
        for corner in self.outgoing_relation[outgoing]:
            incoming = tuple(corner["incoming"])
            path_cost = int(
                self.paths[source_index, self.node_index[incoming]]
            )
            if path_cost + int(corner["cost"]) == optimum:
                candidates.append(
                    (
                        tuple(corner["representative_patch"]),
                        incoming,
                        path_cost,
                        corner,
                    )
                )
        if not candidates:
            raise AssertionError("no minimizing corner decomposition")
        _patch_key, incoming, path_cost, corner = min(candidates)
        # Keep this arc-local.  Caching one seven-layer dictionary for every
        # possible incoming state costs far more memory than recomputing the
        # tiny six-step reverse recurrence when a new arc is first seen.
        suffix = suffix_distances(self.nodes, self.edges, incoming)
        masks = [source[0], source[1]]
        current = source
        cost = 0
        for step in range(EDGE_LENGTH):
            remaining = EDGE_LENGTH - step
            choices = [
                edge
                for edge in self.adjacency[current]
                if edge.target in suffix[remaining - 1]
                and edge.weight + suffix[remaining - 1][edge.target]
                == suffix[remaining][current]
            ]
            if not choices:
                raise AssertionError("minimum path reconstruction failed")
            edge = choices[0]
            masks.append(edge.target[1])
            current = edge.target
            cost += edge.weight
        if current != incoming or cost != path_cost:
            raise AssertionError("reconstructed path has wrong endpoint/cost")
        result = {
            "source_index": source_index,
            "target_index": target_index,
            "masks": masks,
            "path_cost": path_cost,
            "corner_cost": int(corner["cost"]),
            "corner_patch": list(corner["representative_patch"]),
            "arc_cost": optimum,
        }
        self.arc_cache[key] = result
        return result


def rotate_coordinate(
    row: int, column: int, quarter_turns: int
) -> tuple[int, int]:
    for _ in range(quarter_turns % 4):
        row, column = column, N - 1 - row
    return row, column


def assign(
    grid: Grid,
    row: int,
    column: int,
    value: int,
) -> None:
    old = grid[row][column]
    if old != UNKNOWN and old != value:
        raise AssertionError(
            f"conflicting assignment at {(row, column)}: {old} vs {value}"
        )
    grid[row][column] = value


def assemble(contexts: list[dict[str, Any]]) -> Grid:
    grid = [[UNKNOWN for _ in range(N)] for _ in range(N)]
    for side, context in enumerate(contexts):
        masks = context["masks"]
        if len(masks) != EDGE_LENGTH + 2:
            raise AssertionError("side path has wrong length")
        for offset, mask in enumerate(masks):
            canonical_column = DEPTH - 1 + offset
            for canonical_row in range(HALO):
                row, column = rotate_coordinate(
                    canonical_row, canonical_column, side
                )
                assign(
                    grid,
                    row,
                    column,
                    (mask >> canonical_row) & 1,
                )
    for corner in range(4):
        context = contexts[(corner - 1) % 4]
        for local_row, text in enumerate(context["corner_patch"]):
            for local_column, value in enumerate(text):
                row, column = rotate_coordinate(
                    local_row, local_column, corner
                )
                assign(grid, row, column, int(value))
    assigned = sum(value != UNKNOWN for row in grid for value in row)
    expected = N * N - (N - 2 * HALO) ** 2
    if assigned != expected:
        raise AssertionError(f"belt assigned {assigned}, expected {expected}")
    return grid


def value_at(grid: Grid, row: int, column: int) -> int:
    if row < 0 or row >= N or column < 0 or column >= N:
        return 0
    value = grid[row][column]
    if value == UNKNOWN:
        raise AssertionError("charged audit reached the unknown centre")
    return value


def pattern_at(grid: Grid, row: int, column: int) -> tuple[int, ...]:
    return tuple(
        value_at(grid, row + dr, column + dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
    )


def belt_charge(grid: Grid) -> int:
    local = sum(
        chu_wastage(pattern_at(grid, row, column))
        for row in range(N)
        for column in range(N)
        if min(row, column, N - 1 - row, N - 1 - column) < DEPTH
    )
    exterior = sum(1 - grid[0][column] for column in range(N))
    exterior += sum(1 - grid[N - 1][column] for column in range(N))
    exterior += sum(1 - grid[row][0] for row in range(N))
    exterior += sum(1 - grid[row][N - 1] for row in range(N))
    return local + exterior


def audit_belt(grid: Grid, expected_charge: int) -> None:
    for row in range(N):
        for column in range(N):
            if (
                min(row, column, N - 1 - row, N - 1 - column)
                < DEPTH
                and not is_stable_pattern(pattern_at(grid, row, column))
            ):
                raise AssertionError(
                    f"unstable charged cell at {(row, column)}"
                )
    for row in range(-1, N + 1):
        for column in range(-1, N + 1):
            if 0 <= row < N and 0 <= column < N:
                continue
            neighbours = sum(
                value_at(grid, row + dr, column + dc)
                for dr in (-1, 0, 1)
                for dc in (-1, 0, 1)
                if (dr, dc) != (0, 0)
            )
            if neighbours == 3:
                raise AssertionError(
                    f"dead exterior birth at {(row, column)}"
                )
    actual = belt_charge(grid)
    if actual != expected_charge:
        raise AssertionError(
            f"physical charge {actual} != abstract {expected_charge}"
        )


CENTRE_CELLS = tuple(
    (row, column)
    for row in range(HALO, N - HALO)
    for column in range(HALO, N - HALO)
)
AFFECTED = tuple(
    (row, column)
    for row in range(HALO - 1, N - HALO + 1)
    for column in range(HALO - 1, N - HALO + 1)
)


def frame_key(grid: Grid) -> tuple[int, ...]:
    return tuple(
        grid[row][column]
        for row in range(HALO - 2, N - HALO + 2)
        for column in range(HALO - 2, N - HALO + 2)
        if (row, column) not in CENTRE_CELLS
    )


def stable_center_masks(
    belt: Grid,
    required_population: int,
) -> list[int]:
    if not 0 <= required_population <= len(CENTRE_CELLS):
        return []

    # Only columns 3..10 and rows 3..10 can affect the 6 x 6 window of
    # centres touched by the variables.  Build the four variable rows one
    # nibble at a time; each choice immediately finalizes the row above it.
    # This is the exact 16-bit centre census, with strong row-local pruning.
    segments = []
    for row in range(HALO - 2, N - HALO + 2):
        segment = 0
        for local, column in enumerate(
            range(HALO - 2, N - HALO + 2)
        ):
            value = belt[row][column]
            if value == 1:
                segment |= 1 << local
        segments.append(segment)

    @lru_cache(maxsize=None)
    def stable_middle(above: int, middle: int, below: int) -> bool:
        for column in range(1, 7):
            window = 7 << (column - 1)
            neighbours = (
                (above & window).bit_count()
                + (below & window).bit_count()
                + ((middle >> (column - 1)) & 1)
                + ((middle >> (column + 1)) & 1)
            )
            alive = (middle >> column) & 1
            if alive:
                if neighbours not in (2, 3):
                    return False
            elif neighbours == 3:
                return False
        return True

    fixed_outer = [
        segments[index] & ~0b00111100 for index in range(8)
    ]
    result: list[int] = []

    def visit(
        variable_index: int,
        chosen_rows: list[int],
        used_population: int,
    ) -> None:
        if used_population > required_population:
            return
        remaining_rows = 4 - variable_index
        if used_population + 4 * remaining_rows < required_population:
            return
        if variable_index == 4:
            rows = [
                segments[0],
                segments[1],
                *chosen_rows,
                segments[6],
                segments[7],
            ]
            if not stable_middle(rows[4], rows[5], rows[6]):
                return
            if not stable_middle(rows[5], rows[6], rows[7]):
                return
            if used_population != required_population:
                return
            mask = sum(
                ((row >> 2) & 15) << (4 * index)
                for index, row in enumerate(chosen_rows)
            )
            result.append(mask)
            return

        row_position = variable_index + 2
        for nibble in range(16):
            following_population = used_population + nibble.bit_count()
            if following_population > required_population:
                continue
            row = fixed_outer[row_position] | (nibble << 2)
            if variable_index == 0:
                above, middle = segments[0], segments[1]
            else:
                above = (
                    segments[1]
                    if variable_index == 1
                    else chosen_rows[-2]
                )
                middle = chosen_rows[-1]
            if not stable_middle(above, middle, row):
                continue
            visit(
                variable_index + 1,
                [*chosen_rows, row],
                following_population,
            )

    visit(0, [], 0)
    return result


def fill_mask(belt: Grid, mask: int) -> Grid:
    grid = [row[:] for row in belt]
    for index, (row, column) in enumerate(CENTRE_CELLS):
        grid[row][column] = (mask >> index) & 1
    return grid


def grid_digest(grid: Grid) -> str:
    payload = "".join(str(value) for row in grid for value in row)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def build(census_only: bool = False) -> tuple[dict[str, Any], Grid | None]:
    nodes, edges = build_edge_graph()
    relation, _statistics = build_corner_relation(set(nodes))
    sources = sorted({tuple(row["outgoing"]) for row in relation})
    path_matrices, _period = restricted_path_matrices(
        nodes,
        edges,
        sources,
        {EDGE_LENGTH},
        period_search_limit=EDGE_LENGTH,
    )
    paths = path_matrices[EDGE_LENGTH]
    transfer = side_transfer(paths, relation, nodes, sources)
    cycles = enumerate_cycles(transfer)
    print(
        f"abstract cycles modulo rotation: {len(cycles)}",
        file=sys.stderr,
        flush=True,
    )
    reconstructor = ArcReconstructor(
        nodes, edges, relation, sources, paths, transfer
    )

    charge_histogram = Counter(cycles.values())
    belt_digests: set[str] = set()
    belt_histogram = Counter()
    frame_histogram = Counter()
    stable_completion_count = 0
    connected_completion_count = 0
    frame_cache: dict[tuple[tuple[int, ...], int], list[int]] = {}
    witness = None
    completed_cycles = 0

    for cycle_number, (cycle, charge) in enumerate(
        sorted(cycles.items()), start=1
    ):
        if cycle_number % 250 == 0:
            print(
                f"belt {cycle_number}/{len(cycles)} "
                f"distinct={len(belt_digests)} "
                f"frames={len(frame_histogram)}",
                file=sys.stderr,
                flush=True,
            )
        contexts = [
            reconstructor.reconstruct(
                cycle[side], cycle[(side + 1) % 4]
            )
            for side in range(4)
        ]
        belt = assemble(contexts)
        audit_belt(belt, charge)
        digest = grid_digest(belt)
        if digest in belt_digests:
            continue
        belt_digests.add(digest)
        belt_population = sum(
            value for row in belt for value in row if value != UNKNOWN
        )
        belt_histogram[(charge, belt_population)] += 1
        required = TARGET - belt_population
        key = (frame_key(belt), required)
        frame_histogram[key] += 1
        if census_only:
            continue
        if key not in frame_cache:
            frame_cache[key] = stable_center_masks(belt, required)
        masks = frame_cache[key]
        stable_completion_count += len(masks)
        for mask in masks:
            grid = fill_mask(belt, mask)
            check = verify_grid(grid, claimed_cells=TARGET)
            if not check.stable or check.population != TARGET:
                raise AssertionError(check.to_dict())
            if len(connected_components(grid)) == 1:
                connected_completion_count += 1
                witness = grid
                break
        completed_cycles += 1
        if witness is not None:
            break

    record = {
        "schema": "n14-minimum-depth4-belt-census-v1",
        "n": N,
        "target_population": TARGET,
        "target_total_wastage": TOTAL_WASTAGE,
        "language": {
            "edge_states": len(nodes),
            "edge_transitions": len(edges),
            "corner_transitions": len(relation),
            "corner_output_states": len(sources),
            "edge_length": EDGE_LENGTH,
        },
        "abstract_minimum_cycles_mod_rotation": len(cycles),
        "abstract_cycle_charge_histogram": {
            str(key): value
            for key, value in sorted(charge_histogram.items())
        },
        "distinct_minimum_representative_belts": len(belt_digests),
        "belt_charge_population_histogram": {
            f"{charge},{population}": count
            for (charge, population), count in sorted(
                belt_histogram.items()
            )
        },
        "distinct_frame_population_keys": len(frame_histogram),
        "frame_key_multiplicity_histogram": {
            str(multiplicity): count
            for multiplicity, count in sorted(
                Counter(frame_histogram.values()).items()
            )
        },
        "centre_search_performed": not census_only,
        "cycles_completed_before_stop": completed_cycles,
        "stable_population_103_completions_examined": stable_completion_count,
        "connected_population_103_completions": connected_completion_count,
        "connected_witness_found": witness is not None,
        "scope": (
            "Complete over abstract cycles of minimum side-transfer charge "
            "<=36 and one deterministic minimum physical representative "
            "per arc. Non-minimum physical realizations of those arcs are "
            "not covered, so a negative result is not an impossibility proof."
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
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record, witness = build(census_only=args.census_only)
    if args.verify:
        stored = json.loads(args.output.read_text(encoding="utf-8"))
        if stored != record:
            raise SystemExit("stored census differs")
        print("VERIFIED", args.output)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if witness is not None:
        payload = {
            "n": N,
            "claimed_cells": TARGET,
            "grid": witness,
            "source": "The depth-four low-charge belt census",
            "verification": verify_grid(
                witness, claimed_cells=TARGET
            ).to_dict(),
        }
        args.witness.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(record, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
