#!/usr/bin/env python3
"""Exact connectivity-aware low-slack boundary quotient for n=19, P=188.

A processed corner can occur in a connected completion only if every live
component touches its south/east exposed frontier.  Among such patches, all
future connectivity behavior is determined by the partition induced on that
frontier, together with the two-row/two-column Life boundary and the charge.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from itertools import product
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Sequence


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
ENGINE_PATH = (
    HERE.parent
    / "bounded_lift"
    / "certify_n19_complete_low_slack_chain.py"
)
OUTPUT = HERE / "outputs" / "n19_population188_connected_future_quotient.json"
N = 19
TARGET_POPULATION = 188
TARGET_WASTAGE = 46
State = tuple[int, int]
GridPatch = dict[str, Any]
Cell = tuple[int, int]


def digest_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
            "ascii"
        )
    ).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def rows_from_patch(patch: GridPatch) -> list[list[int]]:
    return [[int(character) for character in row] for row in patch["patch"]]


def frontier_signature(
    rendered: Sequence[str],
) -> tuple[tuple[int, ...] | None, int]:
    """Return the canonical frontier partition, or None if a part is sealed."""

    grid = [[int(character) for character in row] for row in rendered]
    size = len(grid)
    if size == 0 or any(len(row) != size for row in grid):
        raise AssertionError("corner patch must be a nonempty square")
    live = {
        (row, column)
        for row in range(size)
        for column in range(size)
        if grid[row][column]
    }
    component_of: dict[Cell, int] = {}
    components: list[set[Cell]] = []
    unseen = set(live)
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        component = {start}
        queue = deque([start])
        while queue:
            row, column = queue.popleft()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    neighbour = row + dr, column + dc
                    if neighbour in unseen:
                        unseen.remove(neighbour)
                        component.add(neighbour)
                        queue.append(neighbour)
        index = len(components)
        components.append(component)
        for cell in component:
            component_of[cell] = index

    frontier = sorted(
        (row, column)
        for row in range(size)
        for column in range(size)
        if row == size - 1 or column == size - 1
    )
    touching = {
        component_of[cell] for cell in frontier if cell in component_of
    }
    sealed = len(components) - len(touching)
    if sealed:
        return None, sealed

    relabel: dict[int, int] = {}
    signature = []
    for cell in frontier:
        component = component_of.get(cell)
        if component is None:
            signature.append(-1)
            continue
        if component not in relabel:
            relabel[component] = len(relabel)
        signature.append(relabel[component])
    return tuple(signature), 0


def connectivity_key(
    patch: GridPatch,
) -> tuple[State, State, int, tuple[int, ...]] | None:
    signature, sealed = frontier_signature(patch["patch"])
    if sealed:
        return None
    assert signature is not None
    return (
        tuple(patch["incoming"]),
        tuple(patch["outgoing"]),
        int(patch["cost"]),
        signature,
    )


def quotient_connected_patches(
    patches: Sequence[GridPatch],
) -> tuple[list[GridPatch], dict[str, Any]]:
    representatives: dict[
        tuple[State, State, int, tuple[int, ...]], tuple[str, ...]
    ] = {}
    sealed_histogram = Counter()
    for patch in patches:
        signature, sealed = frontier_signature(patch["patch"])
        if sealed:
            sealed_histogram[sealed] += 1
            continue
        assert signature is not None
        key = (
            tuple(patch["incoming"]),
            tuple(patch["outgoing"]),
            int(patch["cost"]),
            signature,
        )
        rendered = tuple(patch["patch"])
        incumbent = representatives.get(key)
        if incumbent is None or rendered < incumbent:
            representatives[key] = rendered
    result = [
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
    return result, {
        "input_patch_count": len(patches),
        "discarded_sealed_component_patch_count": sum(
            sealed_histogram.values()
        ),
        "sealed_component_count_histogram": {
            str(count): frequency
            for count, frequency in sorted(sealed_histogram.items())
        },
        "connectivity_future_equivalence_class_count": len(result),
        "removed_duplicate_connectivity_classes": (
            len(patches) - sum(sealed_histogram.values()) - len(result)
        ),
        "class_sha256": digest_json(result),
    }


def load_engine() -> Any:
    specification = importlib.util.spec_from_file_location(
        "connected_future_quotient_boundary_engine",
        ENGINE_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load complete low-slack engine")
    engine = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(engine)
    engine.N = N
    engine.TARGET_POPULATION = TARGET_POPULATION
    engine.TARGET_WASTAGE = TARGET_WASTAGE
    engine.START_DEPTH = 5
    engine.TERMINAL_DEPTH = 9
    engine.PROGRESS = True

    raw_retain = engine.retain_physical_within_slack
    raw_zero_retain = engine.retain_zero_length_physical_within_slack

    def retain_connected(*args: Any, **kwargs: Any) -> tuple[Any, Any]:
        retained, statistics = raw_retain(*args, **kwargs)
        quotient, quotient_statistics = quotient_connected_patches(retained)
        statistics["connectivity_future_quotient"] = quotient_statistics
        statistics["retained_physical_patch_count_before_quotient"] = (
            statistics["retained_physical_patch_count"]
        )
        statistics["retained_physical_patch_count"] = len(quotient)
        statistics["retained_physical_patch_sha256"] = digest_json(quotient)
        return quotient, statistics

    def retain_zero_connected(*args: Any, **kwargs: Any) -> tuple[Any, Any]:
        retained, statistics = raw_zero_retain(*args, **kwargs)
        quotient, quotient_statistics = quotient_connected_patches(retained)
        statistics["connectivity_future_quotient"] = quotient_statistics
        statistics["retained_physical_patch_count_before_quotient"] = (
            statistics["retained_physical_patch_count"]
        )
        statistics["retained_physical_patch_count"] = len(quotient)
        statistics["retained_physical_patch_sha256"] = digest_json(quotient)
        return quotient, statistics

    def bounded_connected_lift(
        old_depth: int,
        old_patches: Sequence[GridPatch],
        old_edges: Sequence[Any],
        maximum_added_charge: int,
    ) -> tuple[list[GridPatch], dict[str, Any]]:
        incoming_edges: dict[State, list[Any]] = defaultdict(list)
        outgoing_edges: dict[State, list[Any]] = defaultdict(list)
        for edge in old_edges:
            incoming_edges[edge.target].append(edge)
            outgoing_edges[edge.source].append(edge)

        engine.configure(old_depth + 1)
        by_boundary: dict[
            tuple[State, State], list[tuple[GridPatch, list[int]]]
        ] = defaultdict(list)
        for mapping in old_patches:
            by_boundary[
                tuple(mapping["incoming"]), tuple(mapping["outgoing"])
            ].append(
                (
                    mapping,
                    [engine.mask_from_row(row) for row in mapping["patch"]],
                )
            )

        representatives: dict[
            tuple[State, State, int, tuple[int, ...]], tuple[str, ...]
        ] = {}
        boundary_contexts_tested = 0
        logical_contexts = 0
        raw_valid_boundary_contexts = 0
        raw_valid_logical_contexts = 0
        valid_added = Counter()
        retained_added = Counter()
        sealed_histogram = Counter()
        for (incoming, outgoing), mappings in sorted(by_boundary.items()):
            representative_rows = mappings[0][1]
            multiplicity = len(mappings)
            for last_edge, first_edge, diagonal in product(
                incoming_edges.get(incoming, ()),
                outgoing_edges.get(outgoing, ()),
                (0, 1),
            ):
                boundary_contexts_tested += 1
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
                    representative_extension, old_depth
                ):
                    continue
                raw_valid_boundary_contexts += 1
                raw_valid_logical_contexts += multiplicity
                added = int(
                    engine.kernel.chu_wastage(
                        engine.kernel.patch_pattern(
                            representative_extension, old_depth, old_depth
                        )
                    )
                )
                valid_added[added] += multiplicity
                if added > maximum_added_charge:
                    continue
                retained_added[added] += multiplicity
                for mapping, base_rows in mappings:
                    rows = [
                        base_rows[row]
                        | (((first_right >> row) & 1) << high)
                        for row in range(old_depth + 1)
                    ]
                    rows.append(last_left | (diagonal << high))
                    rendered = tuple(engine.kernel.render_rows(rows))
                    signature, sealed = frontier_signature(rendered)
                    if sealed:
                        sealed_histogram[sealed] += 1
                        continue
                    assert signature is not None
                    incoming_new, outgoing_new = engine.kernel.corner_states(rows)
                    cost = (
                        int(mapping["cost"])
                        + int(last_weight)
                        + int(first_weight)
                        + added
                    )
                    key = incoming_new, outgoing_new, cost, signature
                    incumbent = representatives.get(key)
                    if incumbent is None or rendered < incumbent:
                        representatives[key] = rendered

        patches = [
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
        return patches, {
            "old_depth": old_depth,
            "new_depth": old_depth + 1,
            "maximum_added_charge": maximum_added_charge,
            "input_connectivity_future_class_count": len(old_patches),
            "input_boundary_pair_count": len(by_boundary),
            "boundary_contexts_tested": boundary_contexts_tested,
            "attempted_logical_contexts": logical_contexts,
            "raw_valid_boundary_context_count": raw_valid_boundary_contexts,
            "raw_valid_logical_context_count": raw_valid_logical_contexts,
            "valid_histogram_by_added_charge": {
                str(charge): count for charge, count in sorted(valid_added.items())
            },
            "retained_histogram_by_added_charge": {
                str(charge): count
                for charge, count in sorted(retained_added.items())
            },
            "discarded_sealed_extension_count": sum(sealed_histogram.values()),
            "sealed_component_count_histogram": {
                str(count): frequency
                for count, frequency in sorted(sealed_histogram.items())
            },
            "distinct_retained_physical_patch_count": len(patches),
            "connectivity_future_equivalence_class_count": len(patches),
            "physical_patch_sha256": digest_json(patches),
            "quotient_key": (
                "(incoming,outgoing,total_charge,exposed_frontier_partition)"
            ),
        }

    engine.retain_physical_within_slack = retain_connected
    engine.retain_zero_length_physical_within_slack = retain_zero_connected
    engine.bounded_physical_corner_lift = bounded_connected_lift
    return engine


def compact_stage(stage: dict[str, Any]) -> dict[str, Any]:
    physical = stage.get("physical_filter", {})
    quotient = physical.get("connectivity_future_quotient", {})
    return {
        "depth": stage["depth"],
        "edge_length": stage["edge_length"],
        "minimum": stage.get("minimum"),
        "global_slack": stage.get("global_slack"),
        "target_survives": stage["target_survives"],
        "exclusion_stage": stage["exclusion_stage"],
        "unquotiented_retained_patch_count": physical.get(
            "retained_physical_patch_count_before_quotient"
        ),
        "discarded_sealed_patch_count": quotient.get(
            "discarded_sealed_component_patch_count"
        ),
        "connectivity_future_class_count": physical.get(
            "retained_physical_patch_count"
        ),
    }


def build() -> dict[str, Any]:
    engine = load_engine()
    chain = engine.build()
    return {
        "schema": "connected-low-slack-future-equivalence-quotient-v1",
        "scope": {
            "n": N,
            "target_population": TARGET_POPULATION,
            "target_wastage": TARGET_WASTAGE,
            "start_depth": 5,
            "terminal_depth": 9,
            "whole_board_search": False,
        },
        "theorem": {
            "sealed_component_pruning": (
                "A component not meeting the last row or last column of a "
                "processed northwest corner cannot meet any future layer, "
                "so no connected completion contains that patch."
            ),
            "equivalence_key": (
                "last-two-row state, last-two-column state, accumulated "
                "charge, and the canonical component partition on the "
                "last-row/last-column frontier"
            ),
            "future_completeness": (
                "Life validity and added charge depend only on the two-cell-"
                "thick boundary. Future component merges depend only on "
                "frontier occupancy and its component partition. Thus one "
                "representative per key preserves every connected future."
            ),
        },
        "engine": {
            "path": str(ENGINE_PATH.relative_to(PROJECT)),
            "sha256": file_digest(ENGINE_PATH),
        },
        "compact_stages": [compact_stage(stage) for stage in chain["stages"]],
        "chain": chain,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    record = build()
    rendered = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    digest = hashlib.sha256(rendered.encode()).hexdigest()
    if arguments.verify:
        if json.loads(OUTPUT.read_text(encoding="utf-8")) != json.loads(rendered):
            raise SystemExit("stored connectivity quotient differs")
        print(f"VERIFIED {digest}")
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(PROJECT)),
                "sha256": digest,
                "compact_stages": record["compact_stages"],
                "conclusion": record["chain"]["conclusion"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
