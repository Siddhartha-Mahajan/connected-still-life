#!/usr/bin/env python3
"""Decompose every supported equality side arc into exact local minima."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CERTIFICATES = ROOT / "certificates" / "upper_bounds"
ORBIT_RECORD = CERTIFICATES / "residue0_equality_orbits_n40.json"
OUTPUT = CERTIFICATES / "residue0_arc_decomposition_n40.json"
INF = 30_000
DEFAULT_N = 40
LENGTH = DEFAULT_N - 10
import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_depth5_ring import path_matrix  # noqa: E402


State = tuple[int, int]


def configure_depth5() -> None:
    kernel.CHARGED_DEPTH = 5
    kernel.MASK_BITS = 6
    kernel.MASK_LIMIT = 64
    kernel.PATCH_SIZE = 6


def output_states(
    relation: list[dict[str, Any]],
) -> list[State]:
    return sorted({tuple(row["outgoing"]) for row in relation})


def forward_layers(
    source: State,
    nodes: list[State],
    edges: list[kernel.Edge],
) -> list[np.ndarray]:
    node_index = {state: index for index, state in enumerate(nodes)}
    layers = [
        np.full(len(nodes), INF, dtype=np.int16)
    ]
    layers[0][node_index[source]] = 0
    incoming_by_target: list[list[tuple[int, int]]] = [
        [] for _node in nodes
    ]
    for edge in edges:
        incoming_by_target[node_index[edge.target]].append(
            (node_index[edge.source], edge.weight)
        )
    for _step in range(LENGTH):
        following = np.full(len(nodes), INF, dtype=np.int16)
        for target, incoming in enumerate(incoming_by_target):
            following[target] = min(
                (
                    int(layers[-1][prior]) + weight
                    for prior, weight in incoming
                ),
                default=INF,
            )
        layers.append(following)
    return layers


def minimum_path_support(
    source: State,
    targets: set[State],
    nodes: list[State],
    edges: list[kernel.Edge],
) -> dict[str, Any]:
    node_index = {state: index for index, state in enumerate(nodes)}
    layers = forward_layers(source, nodes, edges)
    incoming_by_target: list[list[tuple[int, int, int]]] = [
        [] for _node in nodes
    ]
    for edge_index, edge in enumerate(edges):
        incoming_by_target[node_index[edge.target]].append(
            (
                node_index[edge.source],
                edge.weight,
                edge_index,
            )
        )

    current = {node_index[target] for target in targets}
    position_edges: dict[int, set[int]] = defaultdict(set)
    position_states: dict[int, set[int]] = {
        LENGTH: set(current)
    }
    for step in range(LENGTH, 0, -1):
        preceding: set[int] = set()
        for target in current:
            for prior, weight, edge_index in incoming_by_target[target]:
                if (
                    int(layers[step - 1][prior]) + weight
                    == int(layers[step][target])
                ):
                    preceding.add(prior)
                    position_edges[step].add(edge_index)
        current = preceding
        position_states[step - 1] = set(current)

    if node_index[source] not in position_states[0]:
        raise AssertionError("minimum-path backtrace lost its source")
    union_edges = sorted(
        set().union(*position_edges.values())
    )
    union_states = sorted(
        set().union(*position_states.values())
    )
    return {
        "source": list(source),
        "target_count": len(targets),
        "targets": [list(target) for target in sorted(targets)],
        "position_state_counts": {
            str(step): len(position_states[step])
            for step in range(LENGTH + 1)
        },
        "position_edge_counts": {
            str(step): len(position_edges[step])
            for step in range(1, LENGTH + 1)
        },
        "first_position_edges": [
            [
                *edges[index].source,
                edges[index].target[1],
                edges[index].weight,
            ]
            for index in sorted(position_edges[1])
        ],
        "last_position_edges": [
            [
                *edges[index].source,
                edges[index].target[1],
                edges[index].weight,
            ]
            for index in sorted(position_edges[LENGTH])
        ],
        "union_state_count": len(union_states),
        "union_edge_count": len(union_edges),
        "union_state_sha256": hashlib.sha256(
            json.dumps(
                [nodes[index] for index in union_states],
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest(),
        "position_edge_sha256": hashlib.sha256(
            json.dumps(
                {
                    str(step): sorted(position_edges[step])
                    for step in range(1, LENGTH + 1)
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest(),
    }


def single_target_path_support(
    source: State,
    target: State,
    layers: list[np.ndarray],
    nodes: list[State],
    edges: list[kernel.Edge],
) -> dict[str, Any]:
    node_index = {state: index for index, state in enumerate(nodes)}
    incoming_by_target: list[list[tuple[int, int, int]]] = [
        [] for _node in nodes
    ]
    for edge_index, edge in enumerate(edges):
        incoming_by_target[node_index[edge.target]].append(
            (node_index[edge.source], edge.weight, edge_index)
        )
    current = {node_index[target]}
    position_edges: dict[int, set[int]] = defaultdict(set)
    for step in range(LENGTH, 0, -1):
        preceding: set[int] = set()
        for following in current:
            for prior, weight, edge_index in incoming_by_target[following]:
                if (
                    int(layers[step - 1][prior]) + weight
                    == int(layers[step][following])
                ):
                    preceding.add(prior)
                    position_edges[step].add(edge_index)
        current = preceding
    if node_index[source] not in current:
        raise AssertionError("single-target backtrace lost source")
    return {
        "source": list(source),
        "target": list(target),
        "path_cost": int(layers[LENGTH][node_index[target]]),
        "position_edges": {
            str(step): [
                [
                    *edges[index].source,
                    edges[index].target[1],
                    edges[index].weight,
                ]
                for index in sorted(position_edges[step])
            ]
            for step in range(1, LENGTH + 1)
        },
    }


def build(n: int, orbit_path: Path) -> dict[str, Any]:
    global LENGTH
    if n < 16 or n % 8 != 0:
        raise ValueError("n must be >=16 and congruent to zero mod 8")
    LENGTH = n - 10
    orbit = json.loads(orbit_path.read_text(encoding="utf-8"))
    if orbit["n"] != n:
        raise ValueError("orbit record n does not match requested n")
    supported_arcs = {
        tuple(row)
        for row in orbit["complete_equality_support"][
            "arc_state_indices"
        ]
    }
    configure_depth5()
    nodes, edges = kernel.build_edge_graph()
    relation, _statistics = kernel.build_corner_relation(set(nodes))
    sources = output_states(relation)
    source_index = {
        state: index for index, state in enumerate(sources)
    }
    node_index = {state: index for index, state in enumerate(nodes)}
    paths = path_matrix(nodes, edges, sources, LENGTH)
    transfer = side_transfer(paths, relation, nodes, sources)

    relation_by_output: dict[State, list[dict[str, Any]]] = defaultdict(list)
    for corner in relation:
        relation_by_output[tuple(corner["outgoing"])].append(corner)

    decompositions = []
    targets_by_source: dict[State, set[State]] = defaultdict(set)
    corner_mapping_count = Counter()
    for first_index, second_index in sorted(supported_arcs):
        first = sources[first_index]
        second = sources[second_index]
        side_cost = int(transfer[first_index, second_index])
        minimum_corners = []
        for corner in relation_by_output[second]:
            incoming = tuple(corner["incoming"])
            path_cost = int(
                paths[first_index, node_index[incoming]]
            )
            corner_cost = int(corner["cost"])
            if path_cost + corner_cost != side_cost:
                continue
            targets_by_source[first].add(incoming)
            minimum_corners.append(
                {
                    "incoming": list(incoming),
                    "path_cost": path_cost,
                    "corner_cost": corner_cost,
                    "representative_patch": corner[
                        "representative_patch"
                    ],
                }
            )
        if not minimum_corners:
            raise AssertionError("supported side arc has no decomposition")
        corner_mapping_count[len(minimum_corners)] += 1
        decompositions.append(
            {
                "source_index": first_index,
                "target_index": second_index,
                "source": list(first),
                "target": list(second),
                "side_cost": side_cost,
                "minimum_corner_decomposition_count": len(
                    minimum_corners
                ),
                "minimum_corner_decompositions": minimum_corners,
            }
        )

    path_support = [
        minimum_path_support(source, targets, nodes, edges)
        for source, targets in sorted(targets_by_source.items())
    ]
    layers_by_source = {
        source: forward_layers(source, nodes, edges)
        for source in targets_by_source
    }
    cached_single_support: dict[
        tuple[State, State], dict[str, Any]
    ] = {}
    side_arc_path_contexts = []
    for decomposition in decompositions:
        source = tuple(decomposition["source"])
        for corner in decomposition[
            "minimum_corner_decompositions"
        ]:
            incoming = tuple(corner["incoming"])
            cache_key = (source, incoming)
            if cache_key not in cached_single_support:
                cached_single_support[cache_key] = (
                    single_target_path_support(
                        source,
                        incoming,
                        layers_by_source[source],
                        nodes,
                        edges,
                    )
                )
            side_arc_path_contexts.append(
                {
                    "source_index": decomposition["source_index"],
                    "target_index": decomposition["target_index"],
                    "corner_incoming": list(incoming),
                    "corner_cost": corner["corner_cost"],
                    "corner_representative_patch": corner[
                        "representative_patch"
                    ],
                    "path_support": cached_single_support[cache_key],
                }
            )
    return {
        "schema": "depth5-residue0-equality-arc-decomposition-v1",
        "n": n,
        "edge_length": LENGTH,
        "supported_side_arc_count": len(supported_arcs),
        "side_arc_decompositions": decompositions,
        "corner_decomposition_multiplicity_histogram": {
            str(count): arcs
            for count, arcs in sorted(corner_mapping_count.items())
        },
        "unique_path_source_count": len(targets_by_source),
        "unique_path_endpoint_pair_count": sum(
            len(targets) for targets in targets_by_source.values()
        ),
        "minimum_path_support": path_support,
        "side_arc_path_context_count": len(
            side_arc_path_contexts
        ),
        "side_arc_path_contexts": side_arc_path_contexts,
        "claim_scope": (
            "Complete minimum corner decompositions and union of all "
            "minimum edge paths for the 29 supported equality side arcs. "
            "No depth-six lift claim."
        ),
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
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--orbit", type=Path, default=ORBIT_RECORD)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = finalize(build(args.n, args.orbit))
    if args.verify:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored equality decomposition differs")
        print("VERIFIED", args.output)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: record[key]
                for key in (
                    "supported_side_arc_count",
                    "corner_decomposition_multiplicity_histogram",
                    "unique_path_source_count",
                    "unique_path_endpoint_pair_count",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
