#!/usr/bin/env python3
"""Exact inward boundary lifts with streamed physical support.

First stream the exact minimum endpoint relation, find
all supported endpoint arcs, and only then interns physical connectivity
classes.  The filtering order is exact because support depends only on the
endpoint states, side paths, charge, and the target charge.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import importlib.util
from itertools import product
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Sequence

import numpy as np


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
CONNECTED_ENGINE_PATH = (
    HERE.parent
    / "connectivity"
    / "certify_connected_future_quotient.py"
)
OUTPUT = HERE / "outputs" / "n19_population188_supported_streaming.json"
N = 19
TARGET_POPULATION = 188
TARGET_WASTAGE = 46
START_DEPTH = 5
TERMINAL_DEPTH = 9
INF = 30_000

State = tuple[int, int]
GridPatch = dict[str, Any]
ExtensionVisitor = Callable[
    [GridPatch, State, State, int, tuple[int, ...] | None,
     Sequence[int], int, int],
    None,
]


def progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def digest_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_connected_module() -> Any:
    specification = importlib.util.spec_from_file_location(
        "streaming_module_connected_quotient",
        CONNECTED_ENGINE_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load connectivity-aware quotient engine")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class LayerConnectivity:
    """Connectivity of a newly appended south/east L-shaped layer."""

    old_size: int
    new_frontier_component: tuple[int, ...]
    old_frontier_touch_masks: tuple[int, ...]
    component_count: int


def frontier_positions(size: int) -> tuple[tuple[int, int], ...]:
    return tuple(
        (row, column)
        for row in range(size)
        for column in range(size)
        if row == size - 1 or column == size - 1
    )


def layer_connectivity(
    old_size: int,
    right_mask: int,
    bottom_mask: int,
) -> LayerConnectivity:
    """Precompute new-layer components and contacts with the old frontier."""

    new_size = old_size + 1
    new_positions = frontier_positions(new_size)
    old_positions = frontier_positions(old_size)
    occupied = tuple(
        (
            ((right_mask >> row) & 1)
            if column == old_size and row < old_size
            else ((bottom_mask >> column) & 1)
        )
        for row, column in new_positions
    )

    parent = list(range(len(new_positions)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            if first_root > second_root:
                first_root, second_root = second_root, first_root
            parent[second_root] = first_root

    for first, first_position in enumerate(new_positions):
        if not occupied[first]:
            continue
        for second in range(first):
            if not occupied[second]:
                continue
            second_position = new_positions[second]
            if max(
                abs(first_position[0] - second_position[0]),
                abs(first_position[1] - second_position[1]),
            ) <= 1:
                union(first, second)

    relabel: dict[int, int] = {}
    component = []
    for index, live in enumerate(occupied):
        if not live:
            component.append(-1)
            continue
        root = find(index)
        if root not in relabel:
            relabel[root] = len(relabel)
        component.append(relabel[root])

    old_touch_masks = []
    for old_position in old_positions:
        mask = 0
        for index, new_position in enumerate(new_positions):
            label = component[index]
            if label < 0:
                continue
            if max(
                abs(old_position[0] - new_position[0]),
                abs(old_position[1] - new_position[1]),
            ) <= 1:
                mask |= 1 << label
        old_touch_masks.append(mask)

    return LayerConnectivity(
        old_size=old_size,
        new_frontier_component=tuple(component),
        old_frontier_touch_masks=tuple(old_touch_masks),
        component_count=len(relabel),
    )


def advance_frontier_partition(
    old_signature: Sequence[int],
    layer: LayerConnectivity,
) -> tuple[int, ...] | None:
    """Advance an exact component partition or reject a sealed component."""

    expected = 2 * layer.old_size - 1
    if len(old_signature) != expected:
        raise AssertionError(
            f"frontier length {len(old_signature)} != {expected}"
        )
    old_component_count = 1 + max(old_signature, default=-1)
    touches = [0] * old_component_count
    for label, touch_mask in zip(
        old_signature,
        layer.old_frontier_touch_masks,
    ):
        if label >= 0:
            touches[label] |= touch_mask
    if any(mask == 0 for mask in touches):
        return None

    parent = list(range(layer.component_count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            if first_root > second_root:
                first_root, second_root = second_root, first_root
            parent[second_root] = first_root

    for mask in touches:
        if not mask:
            continue
        first = (mask & -mask).bit_length() - 1
        remaining = mask & (mask - 1)
        while remaining:
            next_bit = remaining & -remaining
            union(first, next_bit.bit_length() - 1)
            remaining ^= next_bit

    canonical: dict[int, int] = {}
    result = []
    for label in layer.new_frontier_component:
        if label < 0:
            result.append(-1)
            continue
        root = find(label)
        if root not in canonical:
            canonical[root] = len(canonical)
        result.append(canonical[root])
    return tuple(result)


def extension_rows(
    engine: Any,
    mapping: GridPatch,
    first_right: int,
    last_left: int,
    diagonal: int,
    old_depth: int,
) -> list[int]:
    old_size = old_depth + 1
    high = old_size
    base_rows = [engine.mask_from_row(row) for row in mapping["patch"]]
    rows = [
        base_rows[row] | (((first_right >> row) & 1) << high)
        for row in range(old_size)
    ]
    rows.append(last_left | (diagonal << high))
    return rows


def scan_extensions(
    engine: Any,
    old_depth: int,
    old_patches: Sequence[GridPatch],
    old_edges: Sequence[Any],
    maximum_added_charge: int,
    visitor: ExtensionVisitor,
    *,
    crosscheck_incremental: bool = False,
) -> dict[str, Any]:
    """Visit every admissible extension without interning physical classes."""

    started = time.monotonic()
    incoming_edges: dict[State, list[Any]] = defaultdict(list)
    outgoing_edges: dict[State, list[Any]] = defaultdict(list)
    for edge in old_edges:
        incoming_edges[edge.target].append(edge)
        outgoing_edges[edge.source].append(edge)

    by_boundary: dict[tuple[State, State], list[GridPatch]] = defaultdict(list)
    for mapping in old_patches:
        by_boundary[
            tuple(mapping["incoming"]), tuple(mapping["outgoing"])
        ].append(mapping)

    engine.configure(old_depth + 1)
    boundary_contexts = 0
    logical_contexts = 0
    valid_boundary_contexts = 0
    valid_logical_contexts = 0
    charge_retained_logical_contexts = 0
    incremental_crosschecks = 0
    layer_cache: dict[tuple[int, int], LayerConnectivity] = {}
    added_histogram = Counter()
    retained_added_histogram = Counter()
    pair_count = len(by_boundary)

    for pair_index, ((incoming, outgoing), mappings) in enumerate(
        sorted(by_boundary.items()),
        start=1,
    ):
        representative_rows = [
            engine.mask_from_row(row) for row in mappings[0]["patch"]
        ]
        multiplicity = len(mappings)
        for last_edge, first_edge, diagonal in product(
            incoming_edges.get(incoming, ()),
            outgoing_edges.get(outgoing, ()),
            (0, 1),
        ):
            boundary_contexts += 1
            logical_contexts += multiplicity
            last_left, _, _, last_weight = engine.edge_payload(last_edge)
            _, _, first_right, first_weight = engine.edge_payload(first_edge)
            high = old_depth + 1
            representative_extension = [
                representative_rows[row]
                | (((first_right >> row) & 1) << high)
                for row in range(old_depth + 1)
            ]
            representative_extension.append(last_left | (diagonal << high))
            if not engine.one_layer_corner_extension_valid(
                representative_extension,
                old_depth,
            ):
                continue
            valid_boundary_contexts += 1
            valid_logical_contexts += multiplicity
            added = int(
                engine.kernel.chu_wastage(
                    engine.kernel.patch_pattern(
                        representative_extension,
                        old_depth,
                        old_depth,
                    )
                )
            )
            added_histogram[added] += multiplicity
            if added > maximum_added_charge:
                continue
            retained_added_histogram[added] += multiplicity
            charge_retained_logical_contexts += multiplicity

            incoming_new, outgoing_new = engine.kernel.corner_states(
                representative_extension
            )
            right_mask = first_right & ((1 << (old_depth + 1)) - 1)
            bottom_mask = last_left | (diagonal << (old_depth + 1))
            layer_key = right_mask, bottom_mask
            layer = layer_cache.get(layer_key)
            if layer is None:
                layer = layer_connectivity(
                    old_depth + 1,
                    right_mask,
                    bottom_mask,
                )
                layer_cache[layer_key] = layer
            adjustment = int(last_weight) + int(first_weight) + added

            for mapping in mappings:
                signature = advance_frontier_partition(
                    mapping["frontier_partition"],
                    layer,
                )
                if crosscheck_incremental:
                    rows = extension_rows(
                        engine,
                        mapping,
                        first_right,
                        last_left,
                        diagonal,
                        old_depth,
                    )
                    rendered = tuple(engine.kernel.render_rows(rows))
                    direct, _sealed = engine.frontier_signature(rendered)
                    if direct != signature:
                        raise AssertionError(
                            "incremental frontier partition disagrees with "
                            "direct physical connectivity"
                        )
                    incremental_crosschecks += 1
                visitor(
                    mapping,
                    incoming_new,
                    outgoing_new,
                    adjustment,
                    signature,
                    representative_extension,
                    first_right,
                    diagonal,
                )

        if pair_index % 100 == 0 or pair_index == pair_count:
            progress(
                f"depth {old_depth}->{old_depth + 1}: "
                f"endpoint groups {pair_index}/{pair_count}, "
                f"logical={logical_contexts:,}, "
                f"valid={valid_logical_contexts:,}, "
                f"elapsed={time.monotonic() - started:.1f}s"
            )

    return {
        "old_depth": old_depth,
        "new_depth": old_depth + 1,
        "maximum_added_charge": maximum_added_charge,
        "input_connectivity_class_count": len(old_patches),
        "input_endpoint_pair_count": pair_count,
        "boundary_context_count": boundary_contexts,
        "logical_context_count": logical_contexts,
        "valid_boundary_context_count": valid_boundary_contexts,
        "valid_logical_context_count": valid_logical_contexts,
        "charge_retained_logical_context_count": (
            charge_retained_logical_contexts
        ),
        "valid_histogram_by_added_charge": {
            str(charge): count
            for charge, count in sorted(added_histogram.items())
        },
        "retained_histogram_by_added_charge": {
            str(charge): count
            for charge, count in sorted(retained_added_histogram.items())
        },
        "distinct_new_layer_pattern_count": len(layer_cache),
        "incremental_partition_crosscheck_count": incremental_crosschecks,
    }


def streamed_minimum_relation(
    engine: Any,
    old_depth: int,
    old_patches: Sequence[GridPatch],
    old_edges: Sequence[Any],
    maximum_added_charge: int,
    *,
    crosscheck_incremental: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """First pass: retain only the least connected charge per endpoint."""

    best: dict[tuple[State, State], tuple[int, tuple[str, ...]]] = {}
    connected_logical = 0
    sealed_logical = 0

    def visit(
        mapping: GridPatch,
        incoming: State,
        outgoing: State,
        adjustment: int,
        signature: tuple[int, ...] | None,
        _representative_rows: Sequence[int],
        first_right: int,
        diagonal: int,
    ) -> None:
        nonlocal connected_logical, sealed_logical
        if signature is None:
            sealed_logical += 1
            return
        connected_logical += 1
        cost = int(mapping["cost"]) + adjustment
        key = incoming, outgoing
        incumbent = best.get(key)
        if incumbent is not None and cost > incumbent[0]:
            return
        # Reconstruct only a possible minimum representative.  The first
        # edge's right mask and the diagonal determine the appended column;
        # the appended row is already present in representative_rows.
        old_size = old_depth + 1
        base_rows = [engine.mask_from_row(row) for row in mapping["patch"]]
        rows = [
            base_rows[row]
            | (((first_right >> row) & 1) << old_size)
            for row in range(old_size)
        ]
        rows.append(
            int(_representative_rows[-1])
        )
        rendered = tuple(engine.kernel.render_rows(rows))
        candidate = cost, rendered
        if incumbent is None or candidate < incumbent:
            best[key] = candidate

    scan = scan_extensions(
        engine,
        old_depth,
        old_patches,
        old_edges,
        maximum_added_charge,
        visit,
        crosscheck_incremental=crosscheck_incremental,
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
    scan.update(
        {
            "connected_logical_extension_count": connected_logical,
            "discarded_sealed_logical_extension_count": sealed_logical,
            "minimum_relation_count": len(relation),
            "minimum_relation_sha256": digest_json(relation),
        }
    )
    return relation, scan


def analyze_abstract_depth(
    engine: Any,
    depth: int,
    nodes: Sequence[State],
    edges: Sequence[Any],
    relation: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Compute the exact transfer, target support, and physical thresholds."""

    valid_nodes = set(nodes)
    relation = [
        mapping
        for mapping in relation
        if tuple(mapping["incoming"]) in valid_nodes
        and tuple(mapping["outgoing"]) in valid_nodes
    ]
    sources = engine.output_states(relation)
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
        }, None

    if edge_length == 0:
        paths = None
        transfer, zero_stats = engine.zero_length_transfer(
            relation,
            sources,
        )
    else:
        paths = engine.path_matrix(nodes, edges, sources, edge_length)
        transfer = engine.side_transfer(paths, relation, nodes, sources)
        zero_stats = None
    minimum_test, minimum = engine.safe_minimum_test(
        transfer,
        TARGET_WASTAGE,
    )
    stage = {
        "depth": depth,
        "edge_length": edge_length,
        "edge_state_count": len(nodes),
        "edge_transition_count": len(edges),
        "edge_sha256": engine.edge_digest(edges),
        "corner_mapping_count": len(relation),
        "corner_output_state_count": len(sources),
        "minimum_relation_sha256": digest_json(relation),
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
                [[index, list(state)] for index, state in enumerate(sources)]
            )
            if paths is None
            else hashlib.sha256(paths.tobytes()).hexdigest()
        ),
        "transfer_finite_count": int(np.count_nonzero(transfer < INF)),
        "transfer_sha256": hashlib.sha256(transfer.tobytes()).hexdigest(),
        "minimum_test": minimum_test,
    }
    if zero_stats is not None:
        stage["zero_length_transfer"] = zero_stats
    if minimum is None or minimum > TARGET_WASTAGE:
        stage.update(
            {
                "target_survives": False,
                "exclusion_stage": (
                    "no_anchor_arc"
                    if minimum is None
                    and not int(minimum_test.get("anchor_arc_count", 0))
                    else (
                        "no_finite_anchored_cycle"
                        if minimum is None
                        else "minimum_exceeds_target"
                    )
                ),
            }
        )
        return stage, None

    support, exact_supports = engine.complete_support_up_to(
        transfer,
        sources,
        minimum,
        TARGET_WASTAGE,
    )
    slack = TARGET_WASTAGE - minimum
    node_index = {state: index for index, state in enumerate(nodes)}
    arcs_by_output: dict[State, list[tuple[int, int]]] = defaultdict(list)
    for source_index, target_index in support["arc_state_indices"]:
        arcs_by_output[sources[target_index]].append(
            (int(source_index), int(target_index))
        )

    thresholds: dict[tuple[State, State], int] = {}
    for mapping in relation:
        incoming = tuple(mapping["incoming"])
        outgoing = tuple(mapping["outgoing"])
        incoming_index = node_index.get(incoming)
        if incoming_index is None:
            continue
        best_threshold = None
        for source_index, target_index in arcs_by_output.get(outgoing, ()):
            if paths is None:
                path_cost = 0 if source_index == incoming_index else INF
            else:
                path_cost = int(paths[source_index, incoming_index])
            if path_cost >= INF:
                continue
            threshold = (
                slack
                - path_cost
                + int(transfer[source_index, target_index])
            )
            if best_threshold is None or threshold > best_threshold:
                best_threshold = threshold
        if best_threshold is not None:
            thresholds[incoming, outgoing] = best_threshold

    threshold_histogram = Counter(thresholds.values())
    stage.update(
        {
            "minimum": minimum,
            "global_slack": slack,
            "support_union": support,
            "exact_supports": exact_supports,
            "physical_endpoint_threshold_count": len(thresholds),
            "physical_charge_threshold_histogram": {
                str(charge): count
                for charge, count in sorted(threshold_histogram.items())
            },
            "target_survives": True,
            "exclusion_stage": None,
        }
    )
    return stage, {
        "thresholds": thresholds,
        "sources": sources,
        "paths": paths,
        "transfer": transfer,
        "support": support,
    }


def sparse_exact_side_paths(
    nodes: Sequence[State],
    edges: Sequence[Any],
    sources: Sequence[State],
    relation: Sequence[dict[str, Any]],
    length: int,
    target: int,
) -> tuple[dict[State, dict[State, int]], dict[str, Any]]:
    """Exact bounded paths, computed backward only for corner inputs.

    Every side arc in a four-cycle of total at most ``target`` itself costs
    at most ``target``.  Since all Chu--Stuckey charges are nonnegative, a
    path prefix whose charge already exceeds ``target`` minus the cheapest
    corner at its endpoint can be discarded exactly.
    """

    valid_nodes = set(nodes)
    source_set = set(sources)
    incoming_minimum: dict[State, int] = {}
    for mapping in relation:
        incoming = tuple(mapping["incoming"])
        if incoming not in valid_nodes:
            continue
        cost = int(mapping["cost"])
        incumbent = incoming_minimum.get(incoming)
        if incumbent is None or cost < incumbent:
            incoming_minimum[incoming] = cost

    predecessor_minimum: dict[State, dict[State, int]] = defaultdict(dict)
    for edge in edges:
        predecessor = edge.source
        endpoint = edge.target
        weight = int(edge.weight)
        incumbent = predecessor_minimum[endpoint].get(predecessor)
        if incumbent is None or weight < incumbent:
            predecessor_minimum[endpoint][predecessor] = weight
    predecessors = {
        endpoint: sorted(mapping.items())
        for endpoint, mapping in predecessor_minimum.items()
    }

    paths: dict[State, dict[State, int]] = {}
    discarded_over_cap = 0
    peak_frontier = 0
    for index, (endpoint, corner_minimum) in enumerate(
        sorted(incoming_minimum.items()),
        start=1,
    ):
        cap = target - corner_minimum
        if cap < 0:
            paths[endpoint] = {}
            continue
        frontier: dict[State, int] = {endpoint: 0}
        for _step in range(length):
            following: dict[State, int] = {}
            for state, suffix_cost in frontier.items():
                for predecessor, weight in predecessors.get(state, ()):
                    cost = suffix_cost + weight
                    if cost > cap:
                        discarded_over_cap += 1
                        continue
                    incumbent = following.get(predecessor)
                    if incumbent is None or cost < incumbent:
                        following[predecessor] = cost
            frontier = following
            peak_frontier = max(peak_frontier, len(frontier))
            if not frontier:
                break
        paths[endpoint] = {
            source: cost
            for source, cost in frontier.items()
            if source in source_set
        }
        if index % 1000 == 0 or index == len(incoming_minimum):
            progress(
                f"sparse length-{length} paths: corner inputs "
                f"{index}/{len(incoming_minimum)}"
            )

    path_digest = hashlib.sha256()
    for endpoint, mapping in sorted(paths.items()):
        path_digest.update(
            json.dumps(
                [
                    list(endpoint),
                    [
                        [list(source), cost]
                        for source, cost in sorted(mapping.items())
                    ],
                ],
                separators=(",", ":"),
            ).encode("ascii")
        )
        path_digest.update(b"\n")
    return paths, {
        "algorithm": "bounded_reverse_exact_length_dynamic_program",
        "length": length,
        "node_count": len(nodes),
        "input_edge_count": len(edges),
        "minimum_predecessor_edge_count": sum(
            len(mapping) for mapping in predecessors.values()
        ),
        "source_state_count": len(sources),
        "corner_input_state_count": len(incoming_minimum),
        "finite_source_to_corner_pair_count": sum(
            len(mapping) for mapping in paths.values()
        ),
        "peak_reverse_frontier_state_count": peak_frontier,
        "discarded_partial_paths_over_exact_cap_count": discarded_over_cap,
        "path_relation_line_sha256": path_digest.hexdigest(),
        "exact_cap_proof": (
            "All edge and corner charges are nonnegative. An abstract side "
            "arc used by a four-cycle of total charge at most the target "
            "has side charge at most the target, so reverse partial paths "
            "above target minus the least endpoint-corner charge cannot "
            "participate."
        ),
    }


def sparse_side_transfer(
    sources: Sequence[State],
    relation: Sequence[dict[str, Any]],
    paths: dict[State, dict[State, int]],
    target: int,
) -> tuple[dict[tuple[int, int], int], dict[str, Any]]:
    """Join exact bounded paths and corner minima into sparse side arcs."""

    source_index = {state: index for index, state in enumerate(sources)}
    transfer: dict[tuple[int, int], int] = {}
    joined = 0
    discarded_over_target = 0
    for mapping_index, mapping in enumerate(relation, start=1):
        incoming = tuple(mapping["incoming"])
        outgoing = tuple(mapping["outgoing"])
        outgoing_index = source_index.get(outgoing)
        if outgoing_index is None:
            continue
        corner_cost = int(mapping["cost"])
        for source, path_cost in paths.get(incoming, {}).items():
            joined += 1
            cost = path_cost + corner_cost
            if cost > target:
                discarded_over_target += 1
                continue
            key = source_index[source], outgoing_index
            incumbent = transfer.get(key)
            if incumbent is None or cost < incumbent:
                transfer[key] = cost

        if mapping_index % 5000 == 0 or mapping_index == len(relation):
            progress(
                f"sparse side transfer: corner mappings "
                f"{mapping_index}/{len(relation)}, arcs={len(transfer):,}"
            )

    transfer_digest = hashlib.sha256()
    for (first, second), cost in sorted(transfer.items()):
        transfer_digest.update(f"{first},{second},{cost}\n".encode("ascii"))
    histogram = Counter(transfer.values())
    return transfer, {
        "algorithm": "sparse_exact_path_corner_join",
        "joined_path_corner_pair_count": joined,
        "discarded_side_arcs_over_target_count": discarded_over_target,
        "finite_arc_count_at_most_target": len(transfer),
        "arc_charge_histogram": {
            str(cost): count for cost, count in sorted(histogram.items())
        },
        "sparse_transfer_line_sha256": transfer_digest.hexdigest(),
    }


def sparse_four_cycle_support(
    sources: Sequence[State],
    transfer: dict[tuple[int, int], int],
    target: int,
) -> tuple[dict[str, Any] | None, dict[str, Any], int | None]:
    """Enumerate every transfer four-cycle of total charge at most target."""

    outgoing: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for (first, second), cost in sorted(transfer.items()):
        outgoing[first].append((second, cost))
    anchor_threshold = target // 4
    anchors = [
        (first, second, cost)
        for (first, second), cost in sorted(transfer.items())
        if cost <= anchor_threshold
    ]
    state_support_by_cost: dict[int, set[int]] = defaultdict(set)
    arc_support_by_cost: dict[int, set[tuple[int, int]]] = defaultdict(set)
    anchor_labelled_cycle_count = Counter()
    samples = []

    for anchor_index, (first, second, first_cost) in enumerate(
        anchors,
        start=1,
    ):
        for third, second_cost in outgoing.get(second, ()):
            partial_two = first_cost + second_cost
            if partial_two > target:
                continue
            for fourth, third_cost in outgoing.get(third, ()):
                partial_three = partial_two + third_cost
                if partial_three > target:
                    continue
                fourth_cost = transfer.get((fourth, first))
                if fourth_cost is None:
                    continue
                total = partial_three + fourth_cost
                if total > target:
                    continue
                cycle = (first, second, third, fourth)
                arcs = tuple(
                    (cycle[position], cycle[(position + 1) % 4])
                    for position in range(4)
                )
                state_support_by_cost[total].update(cycle)
                arc_support_by_cost[total].update(arcs)
                anchor_labelled_cycle_count[total] += 1
                if len(samples) < 32:
                    samples.append(
                        {
                            "total_charge": total,
                            "state_indices": list(cycle),
                            "arc_charges": [
                                first_cost,
                                second_cost,
                                third_cost,
                                fourth_cost,
                            ],
                        }
                    )
        if anchor_index % 1000 == 0 or anchor_index == len(anchors):
            progress(
                f"sparse four-cycle anchors {anchor_index}/{len(anchors)}"
            )

    if not state_support_by_cost:
        minimum_test = {
            "target_cost": target,
            "anchor_threshold_floor_target_over_4": anchor_threshold,
            "anchor_arc_count": len(anchors),
            "cycle_at_or_below_target_exists": False,
            "minimum_anchored_four_cycle_cost": INF,
            "anchor_labelled_cycle_count": 0,
            "proof": (
                "Every four-cycle of total cost at most K contains an arc "
                "of cost at most floor(K/4). Every such sparse transfer "
                "arc and every exact three-arc return were enumerated."
            ),
        }
        return None, minimum_test, None

    minimum = min(state_support_by_cost)
    union_states: set[int] = set()
    union_arcs: set[tuple[int, int]] = set()
    exact_supports: dict[str, Any] = {}
    for cost in range(minimum, target + 1):
        states = state_support_by_cost.get(cost, set())
        arcs = arc_support_by_cost.get(cost, set())
        union_states.update(states)
        union_arcs.update(arcs)
        exact_supports[str(cost)] = {
            "target": cost,
            "state_count": len(states),
            "arc_count": len(arcs),
            "state_indices": sorted(states),
            "arc_state_indices": [list(arc) for arc in sorted(arcs)],
            "anchor_labelled_cycle_count": anchor_labelled_cycle_count[cost],
            "support_sha256": digest_json(
                [sorted(states), [list(arc) for arc in sorted(arcs)]]
            ),
        }
    union = {
        "cost_interval": [minimum, target],
        "state_count": len(union_states),
        "arc_count": len(union_arcs),
        "state_indices": sorted(union_states),
        "arc_state_indices": [list(arc) for arc in sorted(union_arcs)],
        "completeness": (
            "Union of every sparse exact four-cycle support with total "
            "charge from the certified minimum through the target."
        ),
    }
    minimum_test = {
        "target_cost": target,
        "anchor_threshold_floor_target_over_4": anchor_threshold,
        "anchor_arc_count": len(anchors),
        "cycle_at_or_below_target_exists": True,
        "minimum_anchored_four_cycle_cost": minimum,
        "anchor_labelled_cycle_count": sum(
            anchor_labelled_cycle_count.values()
        ),
        "anchor_labelled_cycle_count_by_total_charge": {
            str(cost): count
            for cost, count in sorted(anchor_labelled_cycle_count.items())
        },
        "sample_anchor_labelled_cycles": samples,
        "proof": (
            "Every four-cycle of total cost at most K contains an arc of "
            "cost at most floor(K/4). Every such sparse transfer arc and "
            "every exact three-arc return were enumerated."
        ),
    }
    return {
        "union": union,
        "exact": exact_supports,
    }, minimum_test, minimum


def analyze_sparse_abstract_depth(
    engine: Any,
    depth: int,
    nodes: Sequence[State],
    edges: Sequence[Any],
    relation: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Exact sparse replacement for the legacy dense side-support step."""

    valid_nodes = set(nodes)
    relation = [
        mapping
        for mapping in relation
        if tuple(mapping["incoming"]) in valid_nodes
        and tuple(mapping["outgoing"]) in valid_nodes
    ]
    sources = engine.output_states(relation)
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
        }, None

    paths, path_stats = sparse_exact_side_paths(
        nodes,
        edges,
        sources,
        relation,
        edge_length,
        TARGET_WASTAGE,
    )
    transfer, transfer_stats = sparse_side_transfer(
        sources,
        relation,
        paths,
        TARGET_WASTAGE,
    )
    support_record, minimum_test, minimum = sparse_four_cycle_support(
        sources,
        transfer,
        TARGET_WASTAGE,
    )
    stage = {
        "depth": depth,
        "edge_length": edge_length,
        "edge_state_count": len(nodes),
        "edge_transition_count": len(edges),
        "edge_sha256": engine.edge_digest(edges),
        "corner_mapping_count": len(relation),
        "corner_output_state_count": len(sources),
        "minimum_relation_sha256": digest_json(relation),
        "path_representation": "sparse_bounded_reverse_exact_length",
        "path_statistics": path_stats,
        "transfer_representation": "sparse_arcs_at_most_target",
        "transfer_statistics": transfer_stats,
        "minimum_test": minimum_test,
    }
    if support_record is None or minimum is None:
        stage.update(
            {
                "target_survives": False,
                "exclusion_stage": "no_four_cycle_at_or_below_target",
            }
        )
        return stage, None

    support = support_record["union"]
    exact_supports = support_record["exact"]
    slack = TARGET_WASTAGE - minimum
    arcs_by_output: dict[State, list[tuple[int, int]]] = defaultdict(list)
    for first, second in support["arc_state_indices"]:
        arcs_by_output[sources[second]].append((int(first), int(second)))

    thresholds: dict[tuple[State, State], int] = {}
    for mapping in relation:
        incoming = tuple(mapping["incoming"])
        outgoing = tuple(mapping["outgoing"])
        best_threshold = None
        incoming_paths = paths.get(incoming, {})
        for first, second in arcs_by_output.get(outgoing, ()):
            path_cost = incoming_paths.get(sources[first])
            if path_cost is None:
                continue
            threshold = slack - path_cost + transfer[first, second]
            if best_threshold is None or threshold > best_threshold:
                best_threshold = threshold
        if best_threshold is not None:
            thresholds[incoming, outgoing] = best_threshold

    threshold_histogram = Counter(thresholds.values())
    stage.update(
        {
            "minimum": minimum,
            "global_slack": slack,
            "support_union": support,
            "exact_supports": exact_supports,
            "physical_endpoint_threshold_count": len(thresholds),
            "physical_charge_threshold_histogram": {
                str(charge): count
                for charge, count in sorted(threshold_histogram.items())
            },
            "target_survives": True,
            "exclusion_stage": None,
        }
    )
    return stage, {
        "thresholds": thresholds,
        "sources": sources,
        "paths": paths,
        "transfer": transfer,
        "support": support,
    }


def streamed_supported_physical(
    engine: Any,
    old_depth: int,
    old_patches: Sequence[GridPatch],
    old_edges: Sequence[Any],
    maximum_added_charge: int,
    thresholds: dict[tuple[State, State], int],
    *,
    crosscheck_incremental: bool = False,
) -> tuple[list[GridPatch], dict[str, Any]]:
    """Second pass: intern only exact target-supported physical classes."""

    representatives: dict[
        tuple[State, State, int, tuple[int, ...]], tuple[str, ...]
    ] = {}
    unsupported_endpoint = 0
    over_threshold = 0
    sealed = 0
    supported_logical = 0

    def visit(
        mapping: GridPatch,
        incoming: State,
        outgoing: State,
        adjustment: int,
        signature: tuple[int, ...] | None,
        representative_rows: Sequence[int],
        first_right: int,
        _diagonal: int,
    ) -> None:
        nonlocal unsupported_endpoint, over_threshold, sealed
        nonlocal supported_logical
        threshold = thresholds.get((incoming, outgoing))
        if threshold is None:
            unsupported_endpoint += 1
            return
        cost = int(mapping["cost"]) + adjustment
        if cost > threshold:
            over_threshold += 1
            return
        if signature is None:
            sealed += 1
            return
        supported_logical += 1
        old_size = old_depth + 1
        base_rows = [engine.mask_from_row(row) for row in mapping["patch"]]
        rows = [
            base_rows[row]
            | (((first_right >> row) & 1) << old_size)
            for row in range(old_size)
        ]
        rows.append(int(representative_rows[-1]))
        rendered = tuple(engine.kernel.render_rows(rows))
        key = incoming, outgoing, cost, signature
        incumbent = representatives.get(key)
        if incumbent is None or rendered < incumbent:
            representatives[key] = rendered

    scan = scan_extensions(
        engine,
        old_depth,
        old_patches,
        old_edges,
        maximum_added_charge,
        visit,
        crosscheck_incremental=crosscheck_incremental,
    )
    physical = [
        {
            "incoming": list(incoming),
            "outgoing": list(outgoing),
            "cost": cost,
            "frontier_partition": list(signature),
            "patch": list(rendered),
        }
        for (incoming, outgoing, cost, signature), rendered in sorted(
            representatives.items()
        )
    ]
    scan.update(
        {
            "discarded_unsupported_endpoint_logical_count": (
                unsupported_endpoint
            ),
            "discarded_over_charge_threshold_logical_count": over_threshold,
            "discarded_sealed_supported_logical_count": sealed,
            "supported_connected_logical_extension_count": supported_logical,
            "retained_connectivity_future_class_count": len(physical),
            "retained_physical_sha256": digest_json(physical),
        }
    )
    return physical, scan


def initial_depth(engine: Any) -> tuple[
    list[State], list[Any], list[dict[str, Any]], list[GridPatch],
    dict[str, Any], int,
]:
    engine.configure(START_DEPTH)
    progress("depth 5: building complete initial language")
    nodes, edges = engine.kernel.build_edge_graph()
    relation, relation_statistics = engine.kernel.build_corner_relation(
        set(nodes)
    )
    all_physical, physical_statistics = engine.enumerate_full_depth5_corners(
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
    stage, retained, minimum = engine.analyze_depth(
        START_DEPTH,
        nodes,
        edges,
        relation,
        physical,
    )
    if minimum is None or not stage["target_survives"]:
        raise AssertionError("population 188 unexpectedly excluded at depth 5")
    stage["initial_relation_statistics"] = relation_statistics
    stage["initial_physical_statistics"] = physical_statistics
    progress(
        f"depth 5: minimum={minimum}, retained={len(retained):,}"
    )
    return nodes, edges, relation, retained, stage, minimum


def validate_small_transition(
    engine: Any,
    old_depth: int,
    old_physical: Sequence[GridPatch],
    old_edges: Sequence[Any],
    maximum_added_charge: int,
    new_nodes: Sequence[State],
    new_edges: Sequence[Any],
    streamed_relation: Sequence[dict[str, Any]],
    streamed_physical: Sequence[GridPatch],
    streamed_stage: dict[str, Any],
) -> dict[str, Any]:
    """Compare depth six with the former materialize-first implementation."""

    progress("depth 5->6: running materialize-first validation")
    materialized, materialize_stats = engine.bounded_physical_corner_lift(
        old_depth,
        old_physical,
        old_edges,
        maximum_added_charge,
    )
    relation = engine.minimum_relation(materialized)
    stage, retained, minimum = engine.analyze_depth(
        old_depth + 1,
        list(new_nodes),
        list(new_edges),
        relation,
        materialized,
    )
    comparisons = {
        "minimum_relation_equal": list(streamed_relation) == relation,
        "minimum_relation_sha256_streamed": digest_json(streamed_relation),
        "minimum_relation_sha256_materialized": digest_json(relation),
        "minimum_equal": streamed_stage.get("minimum") == minimum,
        "support_equal": (
            streamed_stage.get("support_union", {}).get("state_indices")
            == stage.get("support_union", {}).get("state_indices")
            and streamed_stage.get("support_union", {}).get(
                "arc_state_indices"
            )
            == stage.get("support_union", {}).get("arc_state_indices")
        ),
        "retained_physical_equal": list(streamed_physical) == retained,
        "retained_physical_sha256_streamed": digest_json(streamed_physical),
        "retained_physical_sha256_materialized": digest_json(retained),
        "materialized_candidate_count": len(materialized),
        "materialize_statistics": materialize_stats,
    }
    if not all(
        comparisons[key]
        for key in (
            "minimum_relation_equal",
            "minimum_equal",
            "support_equal",
            "retained_physical_equal",
        )
    ):
        raise AssertionError("streaming/materialized validation mismatch")
    progress("depth 5->6: exact validation passed")
    return comparisons


def validate_sparse_support_kernel(engine: Any) -> dict[str, Any]:
    """Compare sparse path/cycle code with dense algebra on a finite model."""

    nodes: list[State] = [(0, 0), (0, 1), (1, 0), (1, 1)]
    edges = [
        engine.kernel.Edge(nodes[index], nodes[(index + 1) % 4], 1)
        for index in range(4)
    ] + [
        engine.kernel.Edge(state, state, 3) for state in nodes
    ]
    relation = [
        {
            "incoming": list(state),
            "outgoing": list(state),
            "cost": 1,
            "representative_patch": [],
        }
        for state in nodes
    ]
    sources = engine.output_states(relation)
    target = 12
    sparse_paths, _path_stats = sparse_exact_side_paths(
        nodes,
        edges,
        sources,
        relation,
        1,
        target,
    )
    sparse_transfer, _transfer_stats = sparse_side_transfer(
        sources,
        relation,
        sparse_paths,
        target,
    )
    sparse_support, sparse_minimum_test, sparse_minimum = (
        sparse_four_cycle_support(sources, sparse_transfer, target)
    )

    dense_paths = engine.path_matrix(nodes, edges, sources, 1)
    dense_transfer = engine.side_transfer(
        dense_paths,
        relation,
        nodes,
        sources,
    )
    dense_finite = {
        (first, second): int(dense_transfer[first, second])
        for first in range(len(sources))
        for second in range(len(sources))
        if int(dense_transfer[first, second]) <= target
    }
    dense_minimum_test, dense_minimum = engine.safe_minimum_test(
        dense_transfer,
        target,
    )
    if dense_minimum is None:
        raise AssertionError("toy dense model unexpectedly has no cycle")
    dense_union, _dense_exact = engine.complete_support_up_to(
        dense_transfer,
        sources,
        dense_minimum,
        target,
    )
    if sparse_support is None:
        raise AssertionError("toy sparse model unexpectedly has no cycle")
    comparisons = {
        "sparse_transfer_equals_dense_bounded_transfer": (
            sparse_transfer == dense_finite
        ),
        "minimum_equal": sparse_minimum == dense_minimum,
        "minimum_value": sparse_minimum,
        "support_states_equal": (
            sparse_support["union"]["state_indices"]
            == dense_union["state_indices"]
        ),
        "support_arcs_equal": (
            sparse_support["union"]["arc_state_indices"]
            == dense_union["arc_state_indices"]
        ),
        "sparse_anchor_count": sparse_minimum_test["anchor_arc_count"],
        "dense_anchor_count": dense_minimum_test["anchor_arc_count"],
    }
    if not all(
        comparisons[key]
        for key in (
            "sparse_transfer_equals_dense_bounded_transfer",
            "minimum_equal",
            "support_states_equal",
            "support_arcs_equal",
        )
    ):
        raise AssertionError("sparse/dense support-kernel validation mismatch")
    progress("sparse support kernel: dense finite-model validation passed")
    return comparisons


def build(*, validate_small: bool, stop_after_depth: int) -> dict[str, Any]:
    connected = load_connected_module()
    engine = connected.load_engine()
    # ``load_engine`` returns the imported low-slack module and installs the
    # connectivity-aware lift/filter closures on it.  Expose the independent
    # direct flood-fill routine as well for the validation crosscheck.
    engine.frontier_signature = connected.frontier_signature
    validations = (
        [validate_sparse_support_kernel(engine)] if validate_small else []
    )
    nodes, edges, relation, physical, stage, minimum = initial_depth(engine)
    stages = [stage]
    lifts = []

    for old_depth in range(START_DEPTH, stop_after_depth):
        maximum_added_charge = TARGET_WASTAGE - minimum
        progress(
            f"depth {old_depth}->{old_depth + 1}: edge lift with "
            f"allowance {maximum_added_charge}"
        )
        new_nodes, new_edges, edge_stats = engine.bounded_edge_lift(
            old_depth,
            edges,
            maximum_added_charge,
        )
        progress(
            f"depth {old_depth}->{old_depth + 1}: pass 1 endpoint minima"
        )
        relation_next, pass1_stats = streamed_minimum_relation(
            engine,
            old_depth,
            physical,
            edges,
            maximum_added_charge,
            crosscheck_incremental=(validate_small and old_depth == 5),
        )
        if old_depth + 1 < 8:
            stage_next, artifacts = analyze_abstract_depth(
                engine,
                old_depth + 1,
                new_nodes,
                new_edges,
                relation_next,
            )
        else:
            stage_next, artifacts = analyze_sparse_abstract_depth(
                engine,
                old_depth + 1,
                new_nodes,
                new_edges,
                relation_next,
            )
        if artifacts is None:
            stage_next["physical_candidate_count"] = 0
            stage_next["physical_candidate_sha256"] = digest_json([])
            stage_next["physical_filter"] = {
                "retained_physical_patch_count": 0,
                "retained_physical_patch_sha256": digest_json([]),
                "streamed_pass_not_needed": True,
            }
            physical_next: list[GridPatch] = []
            pass2_stats = {"streamed_pass_not_needed": True}
        else:
            progress(
                f"depth {old_depth}->{old_depth + 1}: minimum="
                f"{stage_next['minimum']}, support arcs="
                f"{stage_next['support_union']['arc_count']}; "
                "pass 2 supported physical classes"
            )
            physical_next, pass2_stats = streamed_supported_physical(
                engine,
                old_depth,
                physical,
                edges,
                maximum_added_charge,
                artifacts["thresholds"],
                crosscheck_incremental=(validate_small and old_depth == 5),
            )
            stage_next["physical_candidate_count"] = pass1_stats[
                "connected_logical_extension_count"
            ]
            stage_next["physical_candidate_representation"] = (
                "streamed_logical_extensions; uninterned"
            )
            stage_next["physical_filter"] = {
                "retained_physical_patch_count": len(physical_next),
                "retained_physical_patch_sha256": digest_json(physical_next),
                "safe_filter": (
                    "Every extension is tested against the exact maximum "
                    "physical charge allowed by a supported endpoint arc "
                    "before its connectivity-future key is interned."
                ),
            }
            if not physical_next:
                stage_next["target_survives"] = False
                stage_next["exclusion_stage"] = "no_physical_supported_corner"

        if validate_small and old_depth == 5:
            validations.append(
                validate_small_transition(
                    engine,
                    old_depth,
                    physical,
                    edges,
                    maximum_added_charge,
                    new_nodes,
                    new_edges,
                    relation_next,
                    physical_next,
                    stage_next,
                )
            )

        lifts.append(
            {
                "from_depth": old_depth,
                "to_depth": old_depth + 1,
                "global_slack_allowance": maximum_added_charge,
                "edge_lift": edge_stats,
                "streamed_minimum_relation_pass": pass1_stats,
                "supported_physical_pass": pass2_stats,
            }
        )
        stages.append(stage_next)
        progress(
            f"depth {old_depth + 1}: survives="
            f"{stage_next['target_survives']}, retained="
            f"{len(physical_next):,}"
        )
        nodes = list(new_nodes)
        edges = list(new_edges)
        relation = relation_next
        physical = physical_next
        if not stage_next["target_survives"]:
            break
        minimum = int(stage_next["minimum"])

    terminal_depth = int(stages[-1]["depth"])
    excluded = not bool(stages[-1]["target_survives"])
    record = {
        "schema": "n19-supported-streaming-connected-chain-v1",
        "scope": {
            "n": N,
            "target_population": TARGET_POPULATION,
            "target_wastage": TARGET_WASTAGE,
            "start_depth": START_DEPTH,
            "requested_terminal_depth": stop_after_depth,
            "reached_depth": terminal_depth,
        },
        "theorem": {
            "future_equivalence_key": (
                "incoming and outgoing two-row states, total charge, and "
                "the canonical 8-connected partition of the exposed "
                "south/east frontier"
            ),
            "streaming_completeness": (
                "The first pass retains the exact minimum connected corner "
                "charge for every endpoint pair. Exact four-side support "
                "then gives an endpoint-specific maximum physical charge. "
                "The second pass discards a physical extension only when "
                "no target-supported side arc can contain it, and interns "
                "one representative per exact connectivity-future key."
            ),
            "incremental_connectivity": (
                "When one south/east layer is appended, an old component "
                "is permanently sealed exactly when its frontier class "
                "touches no new live component. New mergers depend only "
                "on those contacts, so the partition advances without "
                "examining discarded interior cells."
            ),
        },
        "dependencies": {
            "connectivity_engine": str(
                CONNECTED_ENGINE_PATH.relative_to(PROJECT)
            ),
            "connectivity_engine_sha256": file_digest(CONNECTED_ENGINE_PATH),
        },
        "validations": validations,
        "stages": stages,
        "lifts": lifts,
        "conclusion": {
            "target_excluded": excluded,
            "excluded_at_depth": terminal_depth if excluded else None,
            "terminal_target_survives": not excluded,
            "terminal_retained_connectivity_class_count": len(physical),
            "terminal_retained_physical_sha256": digest_json(physical),
        },
    }
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--validate-small", action="store_true")
    parser.add_argument(
        "--stop-after-depth",
        type=int,
        choices=range(5, TERMINAL_DEPTH + 1),
        default=TERMINAL_DEPTH,
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()
    record = build(
        validate_small=arguments.validate_small,
        stop_after_depth=arguments.stop_after_depth,
    )
    rendered = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    digest = hashlib.sha256(rendered.encode()).hexdigest()
    output = arguments.output
    if arguments.verify:
        if json.loads(output.read_text(encoding="utf-8")) != json.loads(rendered):
            raise SystemExit("stored supported-streaming certificate differs")
        print(f"VERIFIED {digest}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output.resolve().relative_to(PROJECT)),
                "sha256": digest,
                "stages": [
                    {
                        "depth": stage["depth"],
                        "minimum": stage.get("minimum"),
                        "slack": stage.get("global_slack"),
                        "support_arc_count": stage.get(
                            "support_union", {}
                        ).get("arc_count"),
                        "retained": stage.get("physical_filter", {}).get(
                            "retained_physical_patch_count"
                        ),
                        "survives": stage["target_survives"],
                    }
                    for stage in record["stages"]
                ],
                "conclusion": record["conclusion"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
