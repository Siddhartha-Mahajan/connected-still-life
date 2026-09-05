#!/usr/bin/env python3
"""Certify the block-free width-three Chu--Stuckey edge theorem.

This is a finite-state proof, not a full-board optimization search.

The script:

* reconstructs Chu--Stuckey's local wastage table from their token rules;
* builds the exact width-three edge transition graph;
* verifies the ordinary minimum cycle mean 4/11;
* adds the locally necessary connectedness constraint "no live 2 x 2";
* verifies the block-free minimum cycle mean 3/8 with an integer potential;
* proves the exact period-eight formula for finite free-ended edge segments;
* emits the castle half-plane extension with zero interior wastage; and
* writes a machine-readable certificate which this script can re-check.

All masks store rows 1,...,4 in their low four bits.  Row 0 is the fixed dead
exterior.  A state is a pair of consecutive four-bit columns.  A transition
(a,b)->(b,c) validates the Life rule in rows 1,...,3 and charges the exterior
wastage plus the Chu--Stuckey wastage in the central column b.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_OUTPUT = (
    ROOT / "certificates" / "upper_bounds" / "depth3_edge_certificate.json"
)
HEIGHT = 3
MASK_BITS = HEIGHT + 1
INF = 10**9
CHU_MINUS_TWO_RESIDUES = {
    0,
    1,
    3,
    8,
    9,
    11,
    16,
    17,
    19,
    25,
    27,
    31,
    33,
    39,
    41,
    47,
    49,
}


def bit(mask: int, row: int) -> int:
    """Return a strip bit; row 0 and negative rows are fixed dead."""

    return (mask >> (row - 1)) & 1 if row >= 1 else 0


def local_pattern(a: int, b: int, c: int, row: int) -> tuple[int, ...]:
    """The row-major 3 x 3 pattern around (central column b, given row)."""

    return (
        bit(a, row - 1),
        bit(b, row - 1),
        bit(c, row - 1),
        bit(a, row),
        bit(b, row),
        bit(c, row),
        bit(a, row + 1),
        bit(b, row + 1),
        bit(c, row + 1),
    )


def is_stable_pattern(pattern: tuple[int, ...]) -> bool:
    """Whether the central cell obeys B3/S23 in this neighborhood."""

    center = pattern[4]
    neighbours = sum(pattern) - center
    if center:
        return neighbours in (2, 3)
    return neighbours != 3


SPECIAL_LIVE_ZERO_WASTE = {
    # The paired donor/recipient patterns in Chu--Stuckey Table 3, in all
    # four rotations.  The tuple omits the known-live center.
    (0, 0, 0, 0, 0, 1, 1, 1),
    (1, 1, 1, 0, 0, 0, 0, 0),
    (1, 0, 0, 1, 0, 1, 0, 0),
    (0, 0, 1, 0, 1, 0, 0, 1),
}


def chu_wastage(pattern: tuple[int, ...]) -> int:
    """Return q(P) from Chu--Stuckey's Tables 1--3.

    For a dead center, this is the number of its two tokens not donated.
    For a live center, a dead orthogonal neighbour donates unless both
    flanking diagonal cells are live.  The last two patterns of Table 3 form
    a forced donor/recipient pair and both have zero final wastage.
    """

    nw, north, ne, west, center, east, sw, south, se = pattern
    if not center:
        orthogonal_live = north + east + south + west
        return (2, 1, 0, 0, 2)[orthogonal_live]

    benefactors = (
        not north and not (nw and ne),
        not east and not (ne and se),
        not south and not (sw and se),
        not west and not (nw and sw),
    )
    without_center = (nw, north, ne, west, east, sw, south, se)
    if without_center in SPECIAL_LIVE_ZERO_WASTE:
        return 0
    return max(0, sum(benefactors) - 2)


def has_block_between(left: int, right: int) -> bool:
    """Whether two adjacent columns contain a live 2 x 2 square."""

    return any(
        bit(left, row)
        and bit(left, row + 1)
        and bit(right, row)
        and bit(right, row + 1)
        for row in range(1, HEIGHT + 1)
    )


def transition_valid(a: int, b: int, c: int, blockfree: bool) -> bool:
    """Validate one width-three edge transition."""

    # The exterior dead cell above b would be born if these three top-edge
    # cells were all live.
    if bit(a, 1) + bit(b, 1) + bit(c, 1) > 2:
        return False
    if not all(
        is_stable_pattern(local_pattern(a, b, c, row))
        for row in range(1, HEIGHT + 1)
    ):
        return False
    if blockfree and (
        has_block_between(a, b) or has_block_between(b, c)
    ):
        return False
    return True


def transition_weight(a: int, b: int, c: int) -> int:
    """Exterior plus first-three-row wastage in central column b."""

    exterior = 1 - bit(b, 1)
    interior = sum(
        chu_wastage(local_pattern(a, b, c, row))
        for row in range(1, HEIGHT + 1)
    )
    return exterior + interior


State = tuple[int, int]


@dataclass(frozen=True)
class Edge:
    source: State
    target: State
    weight: int


def build_graph(blockfree: bool) -> tuple[list[State], list[Edge]]:
    """Enumerate every valid state and transition."""

    edges: list[Edge] = []
    for a in range(1 << MASK_BITS):
        for b in range(1 << MASK_BITS):
            for c in range(1 << MASK_BITS):
                if transition_valid(a, b, c, blockfree):
                    edges.append(
                        Edge((a, b), (b, c), transition_weight(a, b, c))
                    )
    nodes = sorted(
        {edge.source for edge in edges} | {edge.target for edge in edges}
    )
    return nodes, edges


def cycle_mean_potential(
    nodes: list[State],
    edges: list[Edge],
    numerator: int,
    denominator: int,
) -> dict[State, int]:
    """Return an integer potential proving every cycle mean >= num/den.

    With adjusted weight a(e)=den*w(e)-num, Bellman--Ford is initialized at
    zero on every node (equivalent to a zero-cost super-source).  Absence of
    an update on pass |V| proves there is no negative cycle.  The resulting
    distances d satisfy

        a(e) + d(source) - d(target) >= 0

    on every edge.  Summing around a cycle cancels d.
    """

    distance = {node: 0 for node in nodes}
    for pass_number in range(len(nodes)):
        changed = False
        for edge in edges:
            adjusted = denominator * edge.weight - numerator
            candidate = distance[edge.source] + adjusted
            if distance[edge.target] > candidate:
                distance[edge.target] = candidate
                changed = True
        if not changed:
            break
        if pass_number == len(nodes) - 1:
            raise AssertionError("negative cycle: proposed mean is too high")

    for edge in edges:
        reduced = (
            denominator * edge.weight
            - numerator
            + distance[edge.source]
            - distance[edge.target]
        )
        if reduced < 0:
            raise AssertionError("invalid potential inequality")
    return distance


def tight_edges(
    edges: Iterable[Edge],
    potential: dict[State, int],
    numerator: int,
    denominator: int,
) -> list[Edge]:
    """Edges on which the potential inequality is tight."""

    result = []
    for edge in edges:
        reduced = (
            denominator * edge.weight
            - numerator
            + potential[edge.source]
            - potential[edge.target]
        )
        if reduced == 0:
            result.append(edge)
    return result


def strongly_connected_components(
    nodes: Iterable[State], edges: Iterable[Edge]
) -> list[list[State]]:
    """Tarjan SCC decomposition."""

    adjacency: dict[State, list[State]] = defaultdict(list)
    self_loops: set[State] = set()
    for edge in edges:
        adjacency[edge.source].append(edge.target)
        if edge.source == edge.target:
            self_loops.add(edge.source)

    index: dict[State, int] = {}
    lowlink: dict[State, int] = {}
    stack: list[State] = []
    on_stack: set[State] = set()
    components: list[list[State]] = []
    counter = 0

    def visit(node: State) -> None:
        nonlocal counter
        index[node] = lowlink[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for target in adjacency[node]:
            if target not in index:
                visit(target)
                lowlink[node] = min(lowlink[node], lowlink[target])
            elif target in on_stack:
                lowlink[node] = min(lowlink[node], index[target])
        if lowlink[node] == index[node]:
            component = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            components.append(component)

    for node in nodes:
        if node not in index:
            visit(node)
    return [
        component
        for component in components
        if len(component) > 1 or component[0] in self_loops
    ]


def enumerate_simple_cycles(
    nodes: list[State], edges: list[Edge]
) -> list[list[State]]:
    """Enumerate simple cycles in the small critical graph.

    Ordering the start node below every other node in a cycle removes cyclic
    rotations.  The certified graphs have only one small cyclic SCC.
    """

    adjacency: dict[State, list[State]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source].append(edge.target)

    cycles: list[list[State]] = []
    for component in strongly_connected_components(nodes, edges):
        allowed = set(component)
        for start in sorted(component):
            path = [start]
            used = {start}

            def visit(node: State) -> None:
                for target in adjacency[node]:
                    if target not in allowed or target < start:
                        continue
                    if target == start:
                        cycles.append(path.copy())
                    elif target not in used:
                        used.add(target)
                        path.append(target)
                        visit(target)
                        path.pop()
                        used.remove(target)

            visit(start)
    return cycles


def edge_lookup(edges: Iterable[Edge]) -> dict[tuple[State, State], Edge]:
    """Map graph arcs to their unique weighted edge."""

    result = {}
    for edge in edges:
        key = (edge.source, edge.target)
        if key in result and result[key].weight != edge.weight:
            raise AssertionError("parallel arcs with different weights")
        result[key] = edge
    return result


def cycle_record(cycle: list[State], edges: list[Edge]) -> dict:
    """Serialize a cycle and its row bitmap."""

    lookup = edge_lookup(edges)
    weights = []
    for index, source in enumerate(cycle):
        target = cycle[(index + 1) % len(cycle)]
        weights.append(lookup[source, target].weight)
    columns = [state[1] for state in cycle]
    rows = [
        "".join("#" if bit(column, row) else "." for column in columns)
        for row in range(1, MASK_BITS + 1)
    ]
    return {
        "length": len(cycle),
        "wastage": sum(weights),
        "weights": weights,
        "states": [list(state) for state in cycle],
        "rows_1_through_4": rows,
    }


def free_segment_values(
    nodes: list[State], edges: list[Edge], through: int
) -> tuple[list[int], list[dict[State, int]]]:
    """Minimum cost of an arbitrary-ended path of each positive length."""

    distance = {node: 0 for node in nodes}
    values = []
    vectors = []
    for _length in range(1, through + 1):
        following = {node: INF for node in nodes}
        for edge in edges:
            following[edge.target] = min(
                following[edge.target],
                distance[edge.source] + edge.weight,
            )
        distance = following
        values.append(min(distance.values()))
        vectors.append(distance.copy())
    return values, vectors


def zero_ended_values(
    edges: list[Edge], through: int
) -> tuple[list[int], list[dict[State, int]]]:
    """Minimum n-column cost with fixed dead columns 0 and n+1."""

    transitions: dict[State, list[Edge]] = defaultdict(list)
    for edge in edges:
        transitions[edge.source].append(edge)
    distance = {(0, first): 0 for first in range(1 << MASK_BITS)}
    values = []
    vectors = []
    for _length in range(1, through + 1):
        following: dict[State, int] = {}
        for source, cost in distance.items():
            for edge in transitions[source]:
                following[edge.target] = min(
                    following.get(edge.target, INF), cost + edge.weight
                )
        distance = following
        values.append(
            min(
                (
                    cost
                    for (_previous, final), cost in distance.items()
                    if final == 0
                ),
                default=INF,
            )
        )
        vectors.append(distance.copy())
    return values, vectors


def assert_vector_shift(
    vectors: list[dict[State, int]],
    first_length: int,
    period: int,
    increment: int,
) -> None:
    """Check one full min-plus vector identity."""

    first = vectors[first_length - 1]
    second = vectors[first_length + period - 1]
    if first.keys() != second.keys():
        raise AssertionError("period vectors have different domains")
    if any(second[state] != first[state] + increment for state in first):
        raise AssertionError("period vector identity failed")


def layered_residue_lower_bounds(
    nodes: list[State],
    edges: list[Edge],
    period: int,
    numerator: int,
    denominator: int,
) -> list[int]:
    """Minimum adjusted path cost in each length residue.

    The product graph has vertices (length mod period, state) and adjusted
    edge weight denominator*weight-numerator.  Every residue-zero vertex is
    connected to a zero-cost super-source.  Bellman--Ford gives the minimum
    adjusted cost over paths of *every* length in each residue.  The original
    cycle potential proves this product graph has no negative cycle.
    """

    layered = [(phase, node) for phase in range(period) for node in nodes]
    distance = {
        (phase, node): 0 if phase == 0 else INF
        for phase, node in layered
    }
    for pass_number in range(len(layered)):
        changed = False
        for edge in edges:
            adjusted = denominator * edge.weight - numerator
            for phase in range(period):
                source = (phase, edge.source)
                target = ((phase + 1) % period, edge.target)
                candidate = distance[source] + adjusted
                if distance[target] > candidate:
                    distance[target] = candidate
                    changed = True
        if not changed:
            break
        if pass_number == len(layered) - 1:
            raise AssertionError("negative cycle in layered residue graph")
    return [
        min(distance[phase, node] for node in nodes)
        for phase in range(period)
    ]


def critical_insertion_witnesses(
    nodes: list[State],
    edges: list[Edge],
    critical_cycles: list[list[State]],
    values: list[int],
) -> dict[str, dict]:
    """Find one optimal base path per residue which visits a critical cycle.

    Inserting the corresponding length-eight, wastage-three critical cycle
    at the visited state proves the matching upper recurrence for all later
    lengths in that residue.
    """

    critical_nodes = {
        state for cycle in critical_cycles for state in cycle
    }
    distance: dict[tuple[State, bool], tuple[int, list[State]]] = {
        (node, node in critical_nodes): (0, [node]) for node in nodes
    }
    witnesses: dict[str, dict] = {}
    for length in range(1, 12):
        following: dict[
            tuple[State, bool], tuple[int, list[State]]
        ] = {}
        for edge in edges:
            for visited in (False, True):
                source_key = (edge.source, visited)
                if source_key not in distance:
                    continue
                cost, path = distance[source_key]
                now_visited = visited or edge.target in critical_nodes
                target_key = (edge.target, now_visited)
                candidate = (cost + edge.weight, path + [edge.target])
                if (
                    target_key not in following
                    or candidate[0] < following[target_key][0]
                ):
                    following[target_key] = candidate
        distance = following
        if length < 4:
            continue
        optimum = values[length - 1]
        candidates = [
            path
            for (_state, visited), (cost, path) in distance.items()
            if visited and cost == optimum
        ]
        if not candidates:
            raise AssertionError(
                f"no critical-cycle witness at length {length}"
            )
        path = min(candidates)
        visited_state = next(
            state for state in path if state in critical_nodes
        )
        cycle_index = next(
            index
            for index, cycle in enumerate(critical_cycles)
            if visited_state in cycle
        )
        witnesses[str(length % 8)] = {
            "base_length": length,
            "base_wastage": optimum,
            "visited_critical_state": list(visited_state),
            "insert_cycle_index": cycle_index,
            "state_path": [list(state) for state in path],
        }
    if set(witnesses) != {str(residue) for residue in range(8)}:
        raise AssertionError("missing a residue-class insertion witness")
    return witnesses


def row_mask(text: str) -> int:
    """Convert a left-to-right #/. row to an eight-bit cyclic mask."""

    if len(text) != 8 or set(text) - {"#", "."}:
        raise ValueError(text)
    return sum((symbol == "#") << column for column, symbol in enumerate(text))


def cyclic_bit(mask: int, column: int) -> int:
    return (mask >> (column % 8)) & 1


def cyclic_pattern(
    above: int, middle: int, below: int, column: int
) -> tuple[int, ...]:
    return (
        cyclic_bit(above, column - 1),
        cyclic_bit(above, column),
        cyclic_bit(above, column + 1),
        cyclic_bit(middle, column - 1),
        cyclic_bit(middle, column),
        cyclic_bit(middle, column + 1),
        cyclic_bit(below, column - 1),
        cyclic_bit(below, column),
        cyclic_bit(below, column + 1),
    )


def verify_half_plane() -> dict:
    """Verify the explicit castle cap and zero-wastage periodic bulk."""

    exterior = row_mask("........")
    cap = row_mask("##.#.##.")
    bulk_text = [
        "#.###.#.",
        "#.....#.",
        "#######.",
        ".......#",
        ".#####.#",
        ".#...#.#",
        ".#.#.#.#",
    ]
    bulk = [row_mask(text) for text in bulk_text]

    # One cap row, followed by the seven-row bulk repeated forever.
    rows = [exterior, cap] + bulk + bulk[:2]
    # Check the cap row and all seven rows of one bulk period, including the
    # last-bulk-row -> first-bulk-row wrap transition.
    for row in range(1, 2 + len(bulk)):
        above, middle, below = rows[row - 1 : row + 2]
        for column in range(8):
            pattern = cyclic_pattern(above, middle, below, column)
            if not is_stable_pattern(pattern):
                raise AssertionError("half-plane stability failure")
            if row >= 2 and chu_wastage(pattern) != 0:
                raise AssertionError("bulk has interior wastage")
        if has_cyclic_block(middle, below):
            raise AssertionError("half-plane contains a live 2 x 2")

    if 8 - cap.bit_count() != 3:
        raise AssertionError("castle cap does not have wastage 3")
    if any(
        sum(cyclic_bit(cap, column + dc) for dc in (-1, 0, 1)) == 3
        for column in range(8)
    ):
        raise AssertionError("dead exterior would contain a birth")

    # Check the 7 x 8 bulk is one 8-connected component on its torus.
    live = {
        (row, column)
        for row, mask in enumerate(bulk)
        for column in range(8)
        if cyclic_bit(mask, column)
    }
    seen = {next(iter(live))}
    queue = list(seen)
    while queue:
        row, column = queue.pop()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                target = ((row + dr) % 7, (column + dc) % 8)
                if target in live and target not in seen:
                    seen.add(target)
                    queue.append(target)
    if seen != live:
        raise AssertionError("bulk torus is disconnected")

    # Add the cap as a non-periodic row above the connected bulk torus and
    # check that every cap component attaches to it.
    combined = {
        (0, column)
        for column in range(8)
        if cyclic_bit(cap, column)
    } | {
        (row + 1, column) for row, column in live
    }
    combined_seen = {next(iter(combined))}
    queue = list(combined_seen)
    while queue:
        row, column = queue.pop()
        candidates = {
            (row, (column - 1) % 8),
            (row, (column + 1) % 8),
        }
        if row == 0:
            candidates |= {
                (1, (column + dc) % 8) for dc in (-1, 0, 1)
            }
        else:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    bulk_row = (row - 1 + dr) % 7
                    candidates.add((bulk_row + 1, (column + dc) % 8))
            if row == 1:
                candidates |= {
                    (0, (column + dc) % 8) for dc in (-1, 0, 1)
                }
        for target in candidates:
            if target in combined and target not in combined_seen:
                combined_seen.add(target)
                queue.append(target)
    if combined_seen != combined:
        raise AssertionError("castle cap does not attach to the bulk")

    return {
        "horizontal_period": 8,
        "cap_rows": ["##.#.##."],
        "bulk_vertical_period": 7,
        "bulk_rows": bulk_text,
        "bulk_population": sum(mask.bit_count() for mask in bulk),
        "bulk_area": 56,
        "bulk_density": "1/2",
        "bulk_torus_connected": True,
        "cap_and_bulk_connected": True,
        "dead_exterior_stable": True,
        "interior_wastage_per_period": 0,
        "exterior_wastage_per_horizontal_period": 3,
    }


def has_cyclic_block(above: int, below: int) -> bool:
    return any(
        cyclic_bit(above, column)
        and cyclic_bit(above, column + 1)
        and cyclic_bit(below, column)
        and cyclic_bit(below, column + 1)
        for column in range(8)
    )


def state_key(state: State) -> str:
    return f"{state[0]},{state[1]}"


def chu_ordinary_maximum(n: int) -> int:
    """Chu--Stuckey Theorem 6, valid for n>=61."""

    if n < 61:
        raise ValueError("ordinary closed form is stated only for n>=61")
    offset = 2 if n % 54 in CHU_MINUS_TWO_RESIDUES else 1
    return (27 * n * n + 34 * n - 54 * offset) // 54


def connected_edge_upper(n: int, free_constants: list[int]) -> int:
    """The disjoint block-free-strip upper bound for n>=10."""

    if n < 10:
        raise ValueError("disjoint-strip bound is stated only for n>=10")
    length = n - 6
    path_wastage = (
        3 * length + free_constants[length % 8]
    ) // 8
    return (n * n + 2 * n - 2 * path_wastage) // 2


def graph_record(
    nodes: list[State],
    edges: list[Edge],
    numerator: int,
    denominator: int,
) -> dict:
    """Build the proof record for one transition graph."""

    potential = cycle_mean_potential(
        nodes, edges, numerator=numerator, denominator=denominator
    )
    critical = tight_edges(
        edges, potential, numerator=numerator, denominator=denominator
    )
    cycles = enumerate_simple_cycles(nodes, critical)
    records = [cycle_record(cycle, edges) for cycle in cycles]
    if not records:
        raise AssertionError("lower cycle-mean bound is not attained")
    if any(
        denominator * record["wastage"]
        != numerator * record["length"]
        for record in records
    ):
        raise AssertionError("critical cycle has the wrong mean")

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "target_cycle_mean": f"{numerator}/{denominator}",
        "potential_inequality": (
            f"{denominator}*weight-{numerator}"
            "+potential[source]-potential[target]>=0"
        ),
        "potential": {
            state_key(state): potential[state] for state in sorted(nodes)
        },
        "potential_min": min(potential.values()),
        "potential_max": max(potential.values()),
        "tight_edge_count": len(critical),
        "critical_cyclic_scc_sizes": sorted(
            len(component)
            for component in strongly_connected_components(nodes, critical)
        ),
        "critical_cycles": records,
    }


def build_certificate() -> dict:
    """Build and internally verify the complete certificate."""

    unrestricted_nodes, unrestricted_edges = build_graph(blockfree=False)
    blockfree_nodes, blockfree_edges = build_graph(blockfree=True)

    unrestricted = graph_record(
        unrestricted_nodes, unrestricted_edges, numerator=4, denominator=11
    )
    blockfree = graph_record(
        blockfree_nodes, blockfree_edges, numerator=3, denominator=8
    )

    free_values, free_vectors = free_segment_values(
        blockfree_nodes, blockfree_edges, through=27
    )
    # A layered shortest-path certificate proves the lower formula for all
    # lengths.  Optimal base paths which visit a critical eight-cycle prove
    # the reverse inequality after insertion of any number of cycles.
    del free_vectors
    free_lower_constants = layered_residue_lower_bounds(
        blockfree_nodes,
        blockfree_edges,
        period=8,
        numerator=3,
        denominator=8,
    )
    blockfree_potential = cycle_mean_potential(
        blockfree_nodes, blockfree_edges, numerator=3, denominator=8
    )
    blockfree_tight = tight_edges(
        blockfree_edges,
        blockfree_potential,
        numerator=3,
        denominator=8,
    )
    blockfree_critical_cycles = enumerate_simple_cycles(
        blockfree_nodes, blockfree_tight
    )
    insertion_witnesses = critical_insertion_witnesses(
        blockfree_nodes,
        blockfree_edges,
        blockfree_critical_cycles,
        free_values,
    )

    zero_values, zero_vectors = zero_ended_values(
        blockfree_edges, through=27
    )
    assert_vector_shift(
        zero_vectors, first_length=12, period=8, increment=3
    )
    if any(
        zero_values[length + 8 - 1] != zero_values[length - 1] + 3
        for length in range(2, 20)
    ):
        raise AssertionError("zero-ended scalar period failed")

    # Recompute the requested high representatives without storing 80 vector
    # layers in the certificate.
    long_free, _ = free_segment_values(
        blockfree_nodes, blockfree_edges, through=87
    )
    long_zero, _ = zero_ended_values(blockfree_edges, through=87)
    free_constants = {
        str(residue): 8 * long_free[(80 + residue) - 1]
        - 3 * (80 + residue)
        for residue in range(8)
    }
    if [free_constants[str(residue)] for residue in range(8)] != (
        free_lower_constants
    ):
        raise AssertionError("layered lower bounds do not match witnesses")
    square_additive_constants = {}
    for residue in range(8):
        segment_residue = (residue - 6) % 8
        # n - f(n-6) = 5n/8 + (18-a[segment_residue])/8.
        square_additive_constants[str(residue)] = (
            f"{18 - free_lower_constants[segment_residue]}/8"
        )

    # The two closed forms have joint period 216 after subtracting their
    # common quadratic term.  Advancing by 216 increases
    # M_ordinary(n)-U_blockfree(n) by exactly one.  A finite residue window
    # therefore proves the eventual comparison.
    for n in range(61, 61 + 216):
        difference = (
            chu_ordinary_maximum(n)
            - connected_edge_upper(n, free_lower_constants)
        )
        advanced = (
            chu_ordinary_maximum(n + 216)
            - connected_edge_upper(n + 216, free_lower_constants)
        )
        if advanced != difference + 1:
            raise AssertionError("216-step bound comparison failed")
    first_strict_improvement = next(
        n
        for n in range(61, 2000)
        if connected_edge_upper(n, free_lower_constants)
        < chu_ordinary_maximum(n)
    )
    eventual_all_n_threshold = next(
        threshold
        for threshold in range(61, 2000)
        if all(
            connected_edge_upper(n, free_lower_constants)
            < chu_ordinary_maximum(n)
            for n in range(threshold, threshold + 216)
        )
    )
    small_comparison = [
        {
            "n": n,
            "blockfree_edge_upper": connected_edge_upper(
                n, free_lower_constants
            ),
        }
        for n in range(10, 33)
    ]
    zero_constants = {
        str(residue): 8 * long_zero[(80 + residue) - 1]
        - 3 * (80 + residue)
        for residue in range(8)
    }

    half_plane = verify_half_plane()
    certificate = {
        "schema": "connected-still-life-blockfree-edge-certificate-v1",
        "mathematical_scope": (
            "finite width-three edge automaton; no full-board optimization"
        ),
        "connectedness_local_lemma": {
            "statement": (
                "In a still life, every live 2x2 square is an isolated "
                "8-connected component. Hence a connected still life with "
                "more than four live cells is block-free."
            ),
            "proof": (
                "Each of the four cells already has exactly three live "
                "neighbors inside the square. Stability forbids every "
                "additional live neighbor of any square cell."
            ),
        },
        "local_table": {
            "stable_neighborhood_count": sum(
                is_stable_pattern(
                    tuple((mask >> position) & 1 for position in range(9))
                )
                for mask in range(1 << 9)
            ),
            "maximum_wastage": max(
                chu_wastage(
                    tuple((mask >> position) & 1 for position in range(9))
                )
                for mask in range(1 << 9)
                if is_stable_pattern(
                    tuple(
                        (mask >> position) & 1 for position in range(9)
                    )
                )
            ),
        },
        "ordinary_width3_graph": unrestricted,
        "blockfree_width3_graph": blockfree,
        "finite_free_segment": {
            "definition": (
                "f(L) is the minimum weight of any L-edge path in the "
                "block-free width-three graph"
            ),
            "values_L_1_through_27": free_values,
            "proved_recurrence": "f(L+8)=f(L)+3 for every L>=4",
            "lower_bound_certificate": (
                "shortest paths in the 8-layer adjusted-weight product graph"
            ),
            "upper_bound_certificate": (
                "one optimal base path per residue visits a critical "
                "length-8, wastage-3 cycle, which can be inserted repeatedly"
            ),
            "critical_cycle_insertion_witnesses": insertion_witnesses,
            "residue_formula": (
                "f(L)=(3L+a[L mod 8])/8 for L>=4"
            ),
            "a_by_residue_0_through_7": free_constants,
        },
        "finite_zero_ended_segment": {
            "definition": (
                "m(n) is the minimum n-column weight with dead columns "
                "0 and n+1"
            ),
            "values_n_1_through_27": zero_values,
            "proved_recurrence": "m(n+8)=m(n)+3 for every n>=2",
            "vector_identity": "distance_vector(20)=distance_vector(12)+3",
            "residue_formula": (
                "m(n)=(3n+b[n mod 8])/8 for n>=2"
            ),
            "b_by_residue_0_through_7": zero_constants,
        },
        "square_upper_bound": {
            "range": "n>=10",
            "disjoint_strip_choice": (
                "For each side use depth-three cells whose along-side "
                "coordinates are 4,...,n-3; the four charged regions are "
                "pairwise disjoint."
            ),
            "wastage_bound": "W>=4*f(n-6)",
            "population_bound": (
                "C(n)<=floor(n^2/2+n-f(n-6)) for connected C(n)>4"
            ),
            "explicit_residue_form": (
                "C(n)<=floor(n^2/2+5n/8+k[n mod 8])"
            ),
            "k_by_n_residue_0_through_7": square_additive_constants,
            "asymptotic_consequence": (
                "C(n)<=n^2/2+5n/8+O(1)"
            ),
            "comparison_with_chu_ordinary_upper": {
                "joint_difference_period": 216,
                "difference_increment_per_216": 1,
                "first_strict_improvement_n": first_strict_improvement,
                "strictly_better_for_every_n_at_least": (
                    eventual_all_n_threshold
                ),
                "n_10_through_32": small_comparison,
                "note": (
                    "For n<=32 the ordinary upper remains stronger; the "
                    "new theorem is an eventual connectedness improvement."
                ),
            },
        },
        "half_plane_attainment": half_plane,
        "open_square_problem": (
            "The half-plane proves the 3/8 edge rate is extendible with "
            "zero interior wastage. An exact square formula still requires "
            "four compatible edge phases, finite corner states, and one "
            "common connected zero-wastage center."
        ),
    }
    canonical = json.dumps(
        certificate, sort_keys=True, separators=(",", ":")
    ).encode()
    certificate["content_sha256_without_this_field"] = hashlib.sha256(
        canonical
    ).hexdigest()
    return certificate


def verify_saved(saved: dict) -> None:
    """Regenerate the proof object and compare it byte-for-byte semantically."""

    regenerated = build_certificate()
    if saved != regenerated:
        raise AssertionError("saved certificate differs from regeneration")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing certificate instead of overwriting it.",
    )
    args = parser.parse_args()
    if args.verify:
        verify_saved(json.loads(args.output.read_text()))
        print(f"VERIFIED {args.output}")
        return

    certificate = build_certificate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(certificate, indent=2) + "\n")
    print(f"WROTE {args.output}")
    print(
        "ordinary:",
        certificate["ordinary_width3_graph"]["target_cycle_mean"],
        "block-free:",
        certificate["blockfree_width3_graph"]["target_cycle_mean"],
    )
    print(
        "square bound:",
        certificate["square_upper_bound"]["population_bound"],
    )


if __name__ == "__main__":
    main()
