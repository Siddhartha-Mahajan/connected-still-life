#!/usr/bin/env python3
"""Test the bounded-slack joint lift for residue-one target boards.

For n>=25 in residue one, the depth-five boundary minimum can lie one unit
below the full target wastage.  This certificate keeps every depth-five
cycle up to the target and allows at most one unit of newly exposed wastage
in the sixth layer.  The resulting language is an overapproximation, so a
negative four-cycle test is a rigorous finite-size exclusion.
"""

from __future__ import annotations

import argparse
from collections import Counter
from itertools import product
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import numpy as np


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
DEPTH4_MODULE = HERE.parent / "depth4"
DEPTH5_MODULE = HERE.parent / "depth5"
EQUALITY_LIFT_MODULE = HERE.parent / "equality_lift"
EQUALITY_SUPPORT_MODULE = HERE.parent / "equality_support"
OUTPUT = HERE / "outputs" / "residue1_slack1_lift_probe.json"
INF = 30_000

for dependency in (HERE, DEPTH4_MODULE, DEPTH5_MODULE, EQUALITY_LIFT_MODULE, EQUALITY_SUPPORT_MODULE):
    if str(dependency) not in sys.path:
        sys.path.insert(0, str(dependency))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_n17_depth6_equality_lift import (  # noqa: E402
    column_mask,
    edge_payload,
    enumerate_full_depth5_corners,
    full_depth6_corner_valid,
    mask_from_row,
    output_states,
)
from equality_support import complete_equality_support  # noqa: E402
from probe_depth5_ring import (  # noqa: E402
    anchored_four_cycle_test,
    path_matrix,
)
from probe_residue1_joint_lift import (  # noqa: E402
    add_state_payload,
    configure_depth5,
    equality_mapping_keys,
    mapping_key_digest,
    target_population,
    target_wastage,
)


State = tuple[int, int]


def configure_depth6() -> None:
    kernel.CHARGED_DEPTH = 6
    kernel.MASK_BITS = 7
    kernel.MASK_LIMIT = 128
    kernel.PATCH_SIZE = 7


def complete_support_up_to(
    transfer: np.ndarray,
    sources: Sequence[State],
    minimum: int,
    target: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Union the complete supports of all exact costs in [minimum,target]."""

    supports: dict[str, Any] = {}
    states: set[int] = set()
    arcs: set[tuple[int, int]] = set()
    for cost in range(minimum, target + 1):
        support = complete_equality_support(transfer, sources, cost)
        supports[str(cost)] = support
        states.update(support["state_indices"])
        arcs.update(
            tuple(arc) for arc in support["arc_state_indices"]
        )
    union = {
        "cost_interval": [minimum, target],
        "state_count": len(states),
        "arc_count": len(arcs),
        "state_indices": sorted(states),
        "arc_state_indices": [list(arc) for arc in sorted(arcs)],
        "completeness": (
            "Union of complete exact four-cycle supports at every integral "
            "cost from the certified boundary minimum through the full "
            "target budget."
        ),
    }
    return union, supports


def build_bounded_edge_graph(
    slack: int,
) -> tuple[list[State], list[kernel.Edge], dict[str, Any]]:
    """All depth-six edges whose newly exposed cell costs at most slack."""

    configure_depth6()
    edges: list[kernel.Edge] = []
    delta_histogram = Counter()
    for left in range(kernel.MASK_LIMIT):
        for middle in range(kernel.MASK_LIMIT):
            for right in range(kernel.MASK_LIMIT):
                if not kernel.transition_valid(left, middle, right):
                    continue
                delta = kernel.chu_wastage(
                    kernel.local_pattern(left, middle, right, 6)
                )
                if delta > slack:
                    continue
                edges.append(
                    kernel.Edge(
                        (left, middle),
                        (middle, right),
                        kernel.transition_weight(left, middle, right),
                    )
                )
                delta_histogram[delta] += 1
    nodes = sorted(
        {edge.source for edge in edges}
        | {edge.target for edge in edges}
    )
    payload = [
        [*edge.source, edge.target[1], edge.weight]
        for edge in edges
    ]
    return nodes, edges, {
        "allowed_new_wastage_per_straight_cell": slack,
        "state_count": len(nodes),
        "transition_count": len(edges),
        "new_wastage_histogram": {
            str(key): value
            for key, value in sorted(delta_histogram.items())
        },
        "transition_sha256": hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode("ascii")
        ).hexdigest(),
    }


def build_bounded_corner_relation(
    patches: Sequence[dict[str, Any]],
    depth5_edges: Sequence[kernel.Edge],
    slack: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Lift every supported physical corner with bounded new wastage."""

    incoming_edges: dict[State, list[kernel.Edge]] = {}
    outgoing_edges: dict[State, list[kernel.Edge]] = {}
    for edge in depth5_edges:
        incoming_edges.setdefault(edge.target, []).append(edge)
        outgoing_edges.setdefault(edge.source, []).append(edge)

    configure_depth6()
    best: dict[tuple[State, State], dict[str, Any]] = {}
    attempted = 0
    valid = 0
    delta_histogram = Counter()
    patch_extension_histogram = Counter()
    for patch_index, mapping in enumerate(patches):
        base_rows = [
            mask_from_row(row) for row in mapping["patch"]
        ]
        incoming = tuple(mapping["incoming"])
        outgoing = tuple(mapping["outgoing"])
        base_outgoing = (
            column_mask(base_rows, 4, 6),
            column_mask(base_rows, 5, 6),
        )
        if base_outgoing != outgoing:
            raise AssertionError("stored depth-five corner output mismatch")
        extension_count = 0
        for last_edge, first_edge, diagonal in product(
            incoming_edges.get(incoming, ()),
            outgoing_edges.get(outgoing, ()),
            (0, 1),
        ):
            attempted += 1
            last_left, last_middle, last_right, last_weight = (
                edge_payload(last_edge)
            )
            first_left, first_middle, first_right, first_weight = (
                edge_payload(first_edge)
            )
            if (last_middle, last_right) != incoming:
                raise AssertionError("bad incoming-edge index")
            if (first_left, first_middle) != outgoing:
                raise AssertionError("bad outgoing-edge index")
            rows = [
                base_rows[row]
                | (((first_right >> row) & 1) << 6)
                for row in range(6)
            ]
            rows.append(last_left | (diagonal << 6))
            if not full_depth6_corner_valid(rows):
                continue
            delta = kernel.chu_wastage(
                kernel.patch_pattern(rows, 5, 5)
            )
            if delta > slack:
                continue
            cost = kernel.patch_cost(rows)
            expected = (
                int(mapping["cost"])
                + last_weight
                + first_weight
                + delta
            )
            if cost != expected:
                raise AssertionError(
                    f"depth-six corner cost mismatch: {cost}!={expected}"
                )
            incoming6, outgoing6 = kernel.corner_states(rows)
            candidate = {
                "incoming": list(incoming6),
                "outgoing": list(outgoing6),
                "cost": cost,
                "new_corner_wastage": delta,
                "representative_patch": kernel.render_rows(rows),
                "depth5_patch_index": patch_index,
            }
            key = (incoming6, outgoing6)
            incumbent = best.get(key)
            if incumbent is None or (
                cost,
                json.dumps(candidate, sort_keys=True),
            ) < (
                int(incumbent["cost"]),
                json.dumps(incumbent, sort_keys=True),
            ):
                best[key] = candidate
            valid += 1
            extension_count += 1
            delta_histogram[delta] += 1
        patch_extension_histogram[extension_count] += 1

    relation = [
        {
            "incoming": row["incoming"],
            "outgoing": row["outgoing"],
            "cost": row["cost"],
            "new_corner_wastage": row["new_corner_wastage"],
            "representative_patch": row["representative_patch"],
        }
        for _key, row in sorted(best.items())
    ]
    return relation, {
        "allowed_new_wastage_per_corner_cell": slack,
        "supported_physical_patch_count": len(patches),
        "attempted_adjacent_edge_and_diagonal_combinations": attempted,
        "raw_valid_extension_count": valid,
        "minimum_lifted_mapping_count": len(relation),
        "corner_output_state_count": len(
            {tuple(row["outgoing"]) for row in relation}
        ),
        "new_corner_wastage_histogram": {
            str(key): value
            for key, value in sorted(delta_histogram.items())
        },
        "physical_patch_valid_extension_count_histogram": {
            str(key): value
            for key, value in sorted(patch_extension_histogram.items())
        },
        "relation_sha256": hashlib.sha256(
            json.dumps(
                relation, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
        ).hexdigest(),
    }


def probe_one(
    n: int,
    nodes5: list[State],
    edges5: list[kernel.Edge],
    relation5: list[dict[str, Any]],
    sources5: list[State],
    all_patches: Sequence[dict[str, Any]],
    nodes6: list[State],
    edges6: list[kernel.Edge],
    edge6_statistics: dict[str, Any],
) -> dict[str, Any]:
    target = target_wastage(n)
    paths5 = path_matrix(nodes5, edges5, sources5, n - 10)
    transfer5 = side_transfer(
        paths5, relation5, nodes5, sources5
    )
    minimum5_test = anchored_four_cycle_test(transfer5, target)
    minimum5 = minimum5_test["minimum_anchored_four_cycle_cost"]
    slack = target - minimum5
    if slack < 0:
        return {
            "n": n,
            "target_population": target_population(n),
            "target_wastage": target,
            "proof_status": "excluded_at_depth5",
            "depth5": {
                "minimum_test": add_state_payload(
                    minimum5_test, sources5
                )
            },
        }
    if slack > 1:
        return {
            "n": n,
            "target_population": target_population(n),
            "target_wastage": target,
            "proof_status": "unsupported_slack",
            "depth5": {
                "minimum_test": add_state_payload(
                    minimum5_test, sources5
                )
            },
            "slack": slack,
        }

    union, exact_supports = complete_support_up_to(
        transfer5, sources5, minimum5, target
    )
    keys = equality_mapping_keys(
        union,
        nodes5,
        relation5,
        sources5,
        paths5,
        transfer5,
    )
    patches = [
        patch
        for patch in all_patches
        if (
            patch["incoming"],
            patch["outgoing"],
            patch["cost"],
        )
        in keys
    ]
    represented = {
        (
            patch["incoming"],
            patch["outgoing"],
            patch["cost"],
        )
        for patch in patches
    }
    if represented != keys:
        raise AssertionError("supported corner mapping lacks physical patch")

    relation6, corner_statistics = build_bounded_corner_relation(
        patches, edges5, slack
    )
    valid_nodes6 = set(nodes6)
    relation6 = [
        mapping
        for mapping in relation6
        if tuple(mapping["incoming"]) in valid_nodes6
        and tuple(mapping["outgoing"]) in valid_nodes6
    ]
    if not relation6:
        return {
            "n": n,
            "target_population": target_population(n),
            "target_wastage": target,
            "slack": slack,
            "proof_status": "excluded_no_depth6_corner",
            "depth5": {
                "minimum_test": add_state_payload(
                    minimum5_test, sources5
                ),
                "support_union": union,
                "exact_supports": exact_supports,
                "mapping_key_count": len(keys),
                "mapping_key_sha256": mapping_key_digest(keys),
                "physical_patch_count": len(patches),
            },
            "depth6": {
                "edge_graph": edge6_statistics,
                "corner_relation": corner_statistics,
            },
        }

    sources6 = output_states(relation6)
    paths6 = path_matrix(nodes6, edges6, sources6, n - 12)
    transfer6 = side_transfer(
        paths6, relation6, nodes6, sources6
    )
    minimum6_test = anchored_four_cycle_test(transfer6, target)
    minimum6 = minimum6_test["minimum_anchored_four_cycle_cost"]
    proof_status = (
        "excluded_at_depth6"
        if minimum6 > target
        else "survives_depth6_relaxation"
    )
    return {
        "n": n,
        "target_population": target_population(n),
        "target_wastage": target,
        "slack": slack,
        "proof_status": proof_status,
        "depth5": {
            "edge_length": n - 10,
            "minimum_test": add_state_payload(
                minimum5_test, sources5
            ),
            "support_union": union,
            "exact_supports": exact_supports,
            "mapping_key_count": len(keys),
            "mapping_key_sha256": mapping_key_digest(keys),
            "physical_patch_count": len(patches),
            "physical_patch_sha256": hashlib.sha256(
                json.dumps(
                    patches,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("ascii")
            ).hexdigest(),
        },
        "depth6": {
            "edge_length": n - 12,
            "edge_graph": edge6_statistics,
            "corner_relation": corner_statistics,
            "filtered_corner_mapping_count": len(relation6),
            "corner_output_state_count": len(sources6),
            "restricted_path_finite_count": int(
                np.count_nonzero(paths6 < INF)
            ),
            "restricted_path_sha256": hashlib.sha256(
                paths6.tobytes()
            ).hexdigest(),
            "side_transfer_finite_count": int(
                np.count_nonzero(transfer6 < INF)
            ),
            "side_transfer_sha256": hashlib.sha256(
                transfer6.tobytes()
            ).hexdigest(),
            "minimum_test": add_state_payload(
                minimum6_test, sources6
            ),
        },
        "joint_lift_excess_over_target": minimum6 - target,
        "logic": (
            "Every target board has a depth-five ring between the certified "
            "minimum and its total budget. The union contains every such "
            "boundary cycle. Every newly exposed sixth-layer cell costs at "
            "most the total slack, so the bounded lift contains every "
            "target projection. A negative four-cycle test is therefore "
            "a rigorous finite-size exclusion."
        ),
    }


def build(ns: Sequence[int]) -> dict[str, Any]:
    configure_depth5()
    nodes5, edges5 = kernel.build_edge_graph()
    relation5, relation5_statistics = kernel.build_corner_relation(
        set(nodes5)
    )
    sources5 = output_states(relation5)
    all_patches, patch_statistics = enumerate_full_depth5_corners(
        set(nodes5)
    )
    nodes6, edges6, edge6_statistics = build_bounded_edge_graph(1)
    rows = [
        probe_one(
            n,
            nodes5,
            edges5,
            relation5,
            sources5,
            all_patches,
            nodes6,
            edges6,
            edge6_statistics,
        )
        for n in ns
    ]
    return {
        "schema": "residue1-bounded-slack-depth6-lift-v1",
        "scope": {
            "tested_n": list(ns),
            "maximum_supported_slack": 1,
            "whole_board_search": False,
            "finite_prefix_is_not_recurrence_proof": True,
        },
        "method": (
            "Union of complete depth-five cycle supports at every cost "
            "through the target, all tied physical corners, and a safe "
            "depth-six lift permitting at most one new unit per cell."
        ),
        "shared_depth5": {
            "edge_state_count": len(nodes5),
            "edge_transition_count": len(edges5),
            "corner_output_state_count": len(sources5),
            "corner_relation_statistics": relation5_statistics,
            "full_physical_corner_census": patch_statistics,
        },
        "shared_depth6_bounded_edge_graph": edge6_statistics,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--n", nargs="+", type=int, default=[25, 33]
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    ns = sorted(set(args.n))
    if any(n < 25 or n % 8 != 1 for n in ns):
        raise SystemExit("all n must be >=25 and congruent to 1 mod 8")
    record = build(ns)
    rendered = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    if args.verify:
        if not args.output.exists():
            raise SystemExit(f"missing stored probe: {args.output}")
        if args.json.loads(output.read_text(encoding="utf-8")) != json.loads(rendered):
            raise SystemExit("stored bounded-slack probe differs")
        print(f"VERIFIED {digest}")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(
                    args.output.resolve().relative_to(PROJECT)
                ),
                "sha256": digest,
                "rows": [
                    {
                        "n": row["n"],
                        "target": row["target_wastage"],
                        "slack": row.get("slack"),
                        "depth6_minimum": (
                            row.get("depth6", {})
                            .get("minimum_test", {})
                            .get("minimum_anchored_four_cycle_cost")
                        ),
                        "proof_status": row["proof_status"],
                    }
                    for row in record["rows"]
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

