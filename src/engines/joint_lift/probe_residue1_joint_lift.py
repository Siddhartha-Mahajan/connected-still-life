#!/usr/bin/env python3
"""Probe the residue-one depth-five equality/depth-six zero-lift language.

This is a boundary-language computation, not a whole-board search.  It
generalizes the certified n=17 argument to arbitrary tested sizes congruent
to one modulo eight and records exactly where an all-size recurrence could
hold or fail.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
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
OUTPUT = HERE / "outputs" / "residue1_joint_lift_probe.json"
INF = 30_000

for dependency in (DEPTH4_MODULE, DEPTH5_MODULE, EQUALITY_LIFT_MODULE, EQUALITY_SUPPORT_MODULE):
    if str(dependency) not in sys.path:
        sys.path.insert(0, str(dependency))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_n17_depth6_equality_lift import (  # noqa: E402
    build_complete_depth6_corner_relation,
    depth6_transfer,
    enumerate_full_depth5_corners,
    output_states,
)
from equality_support import complete_equality_support  # noqa: E402
from probe_depth5_ring import (  # noqa: E402
    anchored_four_cycle_test,
    path_matrix,
)


State = tuple[int, int]


def configure_depth5() -> None:
    kernel.CHARGED_DEPTH = 5
    kernel.MASK_BITS = 6
    kernel.MASK_LIMIT = 64
    kernel.PATCH_SIZE = 6


def target_population(n: int) -> int:
    """The proved d_1=23 all-residue endpoint in residue one."""

    if n % 8 != 1:
        raise ValueError(f"n={n} is not congruent to one modulo eight")
    return (4 * n * n + 5 * n - 23) // 8


def target_wastage(n: int) -> int:
    population = target_population(n)
    return 2 * n * n + 4 * n - 4 * population


def equality_mapping_keys(
    support: dict[str, Any],
    nodes: Sequence[State],
    relation: Sequence[dict[str, Any]],
    sources: Sequence[State],
    paths: np.ndarray,
    transfer: np.ndarray,
) -> set[tuple[State, State, int]]:
    """Return all physical corner mapping keys used on equality arcs."""

    node_index = {state: index for index, state in enumerate(nodes)}
    relation_by_output: dict[State, list[dict[str, Any]]] = defaultdict(list)
    for corner in relation:
        relation_by_output[tuple(corner["outgoing"])].append(corner)

    keys: set[tuple[State, State, int]] = set()
    for first_index, second_index in support["arc_state_indices"]:
        outgoing = sources[second_index]
        side_cost = int(transfer[first_index, second_index])
        for corner in relation_by_output[outgoing]:
            incoming = tuple(corner["incoming"])
            corner_cost = int(corner["cost"])
            path_cost = int(paths[first_index, node_index[incoming]])
            if path_cost + corner_cost == side_cost:
                keys.add((incoming, outgoing, corner_cost))
    return keys


def mapping_key_digest(
    keys: set[tuple[State, State, int]],
) -> str:
    payload = [
        [*incoming, *outgoing, cost]
        for incoming, outgoing, cost in sorted(keys)
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def add_state_payload(
    anchored: dict[str, Any],
    sources: Sequence[State],
) -> dict[str, Any]:
    enriched = dict(anchored)
    indices = anchored.get("minimum_cycle_state_indices")
    if indices is not None:
        enriched["minimum_cycle_states"] = [
            list(sources[index]) for index in indices
        ]
    return enriched


def probe_one(
    n: int,
    nodes5: list[State],
    edges5: list[kernel.Edge],
    relation5: list[dict[str, Any]],
    sources5: list[State],
    all_patches: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    target_p = target_population(n)
    target_w = target_wastage(n)
    paths5 = path_matrix(nodes5, edges5, sources5, n - 10)
    transfer5 = side_transfer(
        paths5, relation5, nodes5, sources5
    )
    depth5_minimum = anchored_four_cycle_test(transfer5, target_w)
    row: dict[str, Any] = {
        "n": n,
        "target_population": target_p,
        "target_wastage": target_w,
        "depth5": {
            "edge_length": n - 10,
            "restricted_path_sha256": hashlib.sha256(
                paths5.tobytes()
            ).hexdigest(),
            "side_transfer_finite_count": int(
                np.count_nonzero(transfer5 < INF)
            ),
            "side_transfer_sha256": hashlib.sha256(
                transfer5.tobytes()
            ).hexdigest(),
            "minimum_test": add_state_payload(
                depth5_minimum, sources5
            ),
        },
        "proof_status": "inconclusive",
    }

    minimum5 = depth5_minimum["minimum_anchored_four_cycle_cost"]
    if minimum5 > target_w:
        row["proof_status"] = "excluded_at_depth5"
        row["consequence"] = (
            "Every full board has total wastage at least its depth-five "
            "boundary wastage, so the target population is excluded."
        )
        return row
    if minimum5 < target_w:
        row["proof_status"] = "depth5_has_slack"
        row["consequence"] = (
            "The equality/zero-lift implication is unavailable because a "
            "target board could spend positive wastage inside depth five."
        )
        return row

    support = complete_equality_support(
        transfer5, sources5, target_w
    )
    keys = equality_mapping_keys(
        support,
        nodes5,
        relation5,
        sources5,
        paths5,
        transfer5,
    )
    equality_patches = [
        patch
        for patch in all_patches
        if (
            patch["incoming"],
            patch["outgoing"],
            patch["cost"],
        )
        in keys
    ]
    represented_keys = {
        (
            patch["incoming"],
            patch["outgoing"],
            patch["cost"],
        )
        for patch in equality_patches
    }
    if represented_keys != keys:
        raise AssertionError("a supported mapping has no physical patch")

    relation6, lift_statistics = (
        build_complete_depth6_corner_relation(
            equality_patches, edges5
        )
    )
    row["depth5"]["equality_support"] = support
    row["depth5"]["equality_mapping_key_count"] = len(keys)
    row["depth5"]["equality_mapping_keys_sha256"] = (
        mapping_key_digest(keys)
    )
    row["depth5"]["equality_physical_patch_count"] = len(
        equality_patches
    )
    row["depth5"]["equality_physical_patches_sha256"] = hashlib.sha256(
        json.dumps(
            equality_patches,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()

    if not relation6:
        row["depth6"] = {
            "corner_lift_statistics": lift_statistics,
            "minimum_test": None,
        }
        row["proof_status"] = "excluded_no_depth6_corner"
        row["consequence"] = (
            "No supported equality corner has a zero-new-wastage "
            "depth-six extension."
        )
        return row

    nodes6, edges6, sources6, paths6, transfer6 = depth6_transfer(
        relation6, n - 12
    )
    minimum6 = anchored_four_cycle_test(transfer6, target_w)
    row["depth6"] = {
        "edge_length": n - 12,
        "edge_state_count": len(nodes6),
        "edge_transition_count": len(edges6),
        "corner_output_state_count": len(sources6),
        "corner_lift_statistics": lift_statistics,
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
        "minimum_test": add_state_payload(minimum6, sources6),
    }
    minimum6_cost = minimum6["minimum_anchored_four_cycle_cost"]
    row["joint_lift_excess_over_target"] = minimum6_cost - target_w
    if minimum6_cost > target_w:
        row["proof_status"] = "excluded_at_depth6"
        row["consequence"] = (
            "Every target board would project to a depth-five equality "
            "ring with zero additional sixth-layer wastage, but the safe "
            "enlarged lift language has no such four-side cycle."
        )
    else:
        row["proof_status"] = "survives_depth6_relaxation"
        row["consequence"] = (
            "The safe depth-six overapproximation contains a target-cost "
            "cycle. This does not construct a full board, but it refutes "
            "this depth-six exclusion strategy at the tested size."
        )
    return row


def recurrence_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    pairs = []
    for first, second in zip(rows, rows[1:]):
        if second["n"] != first["n"] + 8:
            continue
        pair: dict[str, Any] = {
            "from_n": first["n"],
            "to_n": second["n"],
            "target_wastage_increment": (
                second["target_wastage"] - first["target_wastage"]
            ),
            "depth5_mapping_keys_equal": (
                first["depth5"].get("equality_mapping_keys_sha256")
                == second["depth5"].get(
                    "equality_mapping_keys_sha256"
                )
            ),
        }
        first_test = first.get("depth6", {}).get("minimum_test")
        second_test = second.get("depth6", {}).get("minimum_test")
        if first_test is not None and second_test is not None:
            pair["depth6_minimum_increment"] = (
                second_test["minimum_anchored_four_cycle_cost"]
                - first_test["minimum_anchored_four_cycle_cost"]
            )
            pair["depth6_corner_relation_equal"] = (
                first["depth6"]["corner_lift_statistics"][
                    "relation_sha256"
                ]
                == second["depth6"]["corner_lift_statistics"][
                    "relation_sha256"
                ]
            )
        pairs.append(pair)
    return {
        "adjacent_residue_one_pairs": pairs,
        "all_tested_targets_excluded": all(
            row["proof_status"].startswith("excluded")
            for row in rows
        ),
        "finite_prefix_is_not_a_recurrence_proof": True,
    }


def build(ns: Sequence[int]) -> dict[str, Any]:
    configure_depth5()
    nodes5, edges5 = kernel.build_edge_graph()
    relation5, relation_statistics = kernel.build_corner_relation(
        set(nodes5)
    )
    sources5 = output_states(relation5)
    all_patches, full_patch_statistics = enumerate_full_depth5_corners(
        set(nodes5)
    )
    rows = [
        probe_one(
            n,
            nodes5,
            edges5,
            relation5,
            sources5,
            all_patches,
        )
        for n in ns
    ]
    return {
        "schema": "residue1-joint-depth5-depth6-probe-v1",
        "method": (
            "Complete depth-five equality support followed by every tied "
            "physical corner and a safe zero-new-wastage depth-six lift."
        ),
        "scope": {
            "tested_n": list(ns),
            "residue": 1,
            "modulus": 8,
            "target_charge": 23,
            "whole_board_search": False,
            "claim": (
                "Each negative row is a rigorous finite-size exclusion. "
                "The collection is not an all-size theorem without a "
                "separately certified recurrence."
            ),
        },
        "shared_depth5_language": {
            "edge_state_count": len(nodes5),
            "edge_transition_count": len(edges5),
            "corner_output_state_count": len(sources5),
            "corner_relation_statistics": relation_statistics,
            "full_physical_corner_census": full_patch_statistics,
        },
        "rows": rows,
        "recurrence_observations": recurrence_summary(rows),
    }


def render(record: dict[str, Any]) -> str:
    return json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--n",
        nargs="+",
        type=int,
        default=[17, 25, 33, 41, 49],
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    ns = sorted(set(args.n))
    if any(n < 17 or n % 8 != 1 for n in ns):
        raise SystemExit("all n must be at least 17 and congruent to 1 mod 8")
    record = build(ns)
    rendered = render(record)
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    if args.verify:
        if not args.output.exists():
            raise SystemExit(f"missing stored probe: {args.output}")
        if args.json.loads(output.read_text(encoding="utf-8")) != json.loads(rendered):
            raise SystemExit("stored residue-one joint probe differs")
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
                        "target_wastage": row["target_wastage"],
                        "depth5_minimum": row["depth5"][
                            "minimum_test"
                        ]["minimum_anchored_four_cycle_cost"],
                        "depth6_minimum": (
                            row.get("depth6", {})
                            .get("minimum_test", {})
                            .get("minimum_anchored_four_cycle_cost")
                            if row.get("depth6", {}).get("minimum_test")
                            is not None
                            else None
                        ),
                        "proof_status": row["proof_status"],
                    }
                    for row in record["rows"]
                ],
                "recurrence": record["recurrence_observations"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
