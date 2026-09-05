#!/usr/bin/env python3
"""Certify the corrected depth-six lift ring over equality-supported corners."""

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
ROOT = HERE.parents[1]
CERTIFICATES = ROOT / "certificates" / "upper_bounds"
DECOMPOSITION = CERTIFICATES / "residue0_arc_decomposition_n40.json"
FINITE_DECOMPOSITIONS = {
    16: CERTIFICATES / "residue0_arc_decomposition_n16.json",
    24: CERTIFICATES / "residue0_arc_decomposition_n24.json",
    32: CERTIFICATES / "residue0_arc_decomposition_n32.json",
    40: DECOMPOSITION,
}
OUTPUT = CERTIFICATES / "corrected_depth6_ring_certificate.json"
INF = 30_000

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from depth6_zero_lift_census import (  # noqa: E402
    build_filtered_edge_graph,
)
from certify_depth5_ring import (  # noqa: E402
    anchored_four_cycle_test,
    depth4_wastage,
)
from build_corrected_depth6_lifts import (  # noqa: E402
    configure_depth6,
    corner_extensions,
)


State = tuple[int, int]


def configure_depth5() -> None:
    kernel.CHARGED_DEPTH = 5
    kernel.MASK_BITS = 6
    kernel.MASK_LIMIT = 64
    kernel.PATCH_SIZE = 6


def output_states(
    relation: Sequence[dict[str, Any]],
) -> list[State]:
    return sorted({tuple(row["outgoing"]) for row in relation})


def edge_payload(edge: kernel.Edge) -> list[int]:
    return [*edge.source, edge.target[1], edge.weight]


def equality_corner_mappings(
    decomposition: dict[str, Any],
) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for context in decomposition["side_arc_path_contexts"]:
        patch = tuple(context["corner_representative_patch"])
        incoming = tuple(context["corner_incoming"])
        patch_masks = [
            sum(
                (character == "1") << column
                for column, character in enumerate(row)
            )
            for row in patch
        ]
        outgoing = tuple(
            sum(
                ((patch_masks[row] >> column) & 1) << row
                for row in range(6)
            )
            for column in (4, 5)
        )
        key = (
            incoming,
            outgoing,
            int(context["corner_cost"]),
            patch,
        )
        unique[key] = {
            "incoming": incoming,
            "outgoing": outgoing,
            "cost": int(context["corner_cost"]),
            "patch": list(patch),
        }
    return [unique[key] for key in sorted(unique)]


def build_corrected_corner_relation(
    mappings: Sequence[dict[str, Any]],
    depth5_edges: Sequence[kernel.Edge],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    incoming_edges: dict[State, list[list[int]]] = defaultdict(list)
    outgoing_edges: dict[State, list[list[int]]] = defaultdict(list)
    for edge in depth5_edges:
        incoming_edges[edge.target].append(edge_payload(edge))
        outgoing_edges[edge.source].append(edge_payload(edge))

    configure_depth6()
    best: dict[tuple[State, State], dict[str, Any]] = {}
    extension_count = 0
    mapping_rows = []
    for mapping_index, mapping in enumerate(mappings):
        incoming = tuple(mapping["incoming"])
        outgoing = tuple(mapping["outgoing"])
        previous = {
            "corner_representative_patch": mapping["patch"],
            "corner_incoming": list(incoming),
            "corner_cost": mapping["cost"],
            "path_support": {
                "position_edges": {
                    "30": incoming_edges[incoming]
                }
            },
        }
        following = {
            "path_support": {
                "position_edges": {
                    "1": outgoing_edges[outgoing]
                }
            }
        }
        extensions = corner_extensions(previous, following)
        extension_count += len(extensions)
        mapping_rows.append(
            {
                "mapping_index": mapping_index,
                "incoming": list(incoming),
                "outgoing": list(outgoing),
                "depth5_incoming_edge_count": len(
                    incoming_edges[incoming]
                ),
                "depth5_outgoing_edge_count": len(
                    outgoing_edges[outgoing]
                ),
                "valid_depth6_extension_count": len(extensions),
            }
        )
        for extension in extensions:
            key = (
                tuple(extension["incoming"]),
                tuple(extension["outgoing"]),
            )
            incumbent = best.get(key)
            if incumbent is None or (
                extension["cost"],
                json.dumps(extension, sort_keys=True),
            ) < (
                incumbent["cost"],
                json.dumps(incumbent, sort_keys=True),
            ):
                best[key] = extension
    relation = [
        {
            "incoming": row["incoming"],
            "outgoing": row["outgoing"],
            "cost": row["cost"],
            "representative_patch": row["patch"],
        }
        for _key, row in sorted(best.items())
    ]
    return relation, {
        "equality_depth5_mapping_count": len(mappings),
        "raw_valid_extension_count": extension_count,
        "minimum_depth6_corner_mapping_count": len(relation),
        "mapping_rows": mapping_rows,
        "relation_sha256": hashlib.sha256(
            json.dumps(
                relation, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
        ).hexdigest(),
    }


def recurrence_comparison(
    old: np.ndarray,
    new: np.ndarray,
) -> dict[str, Any]:
    old_finite = old < INF
    new_finite = new < INF
    support_equal = np.array_equal(old_finite, new_finite)
    plus_three = bool(
        support_equal
        and np.array_equal(
            new[new_finite], old[new_finite] + 3
        )
    )
    return {
        "finite_support_equal": bool(support_equal),
        "every_finite_entry_increases_by_3": plus_three,
        "changed_finite_entry_count_after_plus_3": (
            int(
                np.count_nonzero(
                    new[new_finite] != old[new_finite] + 3
                )
            )
            if support_equal
            else None
        ),
        "inducts_for_all_later_lengths": plus_three,
        "induction": (
            "D[L+1]=D[L] min-plus E on the fixed zero-new-wastage "
            "depth-six edge graph; complete D[L+8]=D[L]+3 equality "
            "propagates forever"
        ),
    }


def build(ns: Sequence[int]) -> dict[str, Any]:
    ordered_ns = sorted(set(ns))
    if any(n < 16 or n % 8 != 0 for n in ordered_ns):
        raise ValueError("all n must be >=16 and congruent to zero mod 8")
    finite_decompositions = {
        n: json.loads(path.read_text(encoding="utf-8"))
        for n, path in FINITE_DECOMPOSITIONS.items()
    }
    decomposition = finite_decompositions[40]
    configure_depth5()
    _nodes5, edges5 = kernel.build_edge_graph()
    mappings = equality_corner_mappings(decomposition)
    mapping_keys = {
        (
            tuple(row["incoming"]),
            tuple(row["outgoing"]),
            row["cost"],
            tuple(row["patch"]),
        )
        for row in mappings
    }
    finite_mapping_audit = []
    for n, record in sorted(finite_decompositions.items()):
        rows = equality_corner_mappings(record)
        keys = {
            (
                tuple(row["incoming"]),
                tuple(row["outgoing"]),
                row["cost"],
                tuple(row["patch"]),
            )
            for row in rows
        }
        finite_mapping_audit.append(
            {
                "n": n,
                "mapping_count": len(rows),
                "equals_n40_mapping_set": keys == mapping_keys,
                "decomposition_record_sha256": hashlib.sha256(
                    json.dumps(
                        record, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                ).hexdigest(),
            }
        )
    if not all(
        row["equals_n40_mapping_set"]
        for row in finite_mapping_audit
    ):
        raise AssertionError("transient equality corner set differs")
    relation, corner_statistics = build_corrected_corner_relation(
        mappings, edges5
    )
    if not relation:
        raise AssertionError("corrected corner relation is empty")

    configure_depth6()
    nodes, edges = build_filtered_edge_graph()
    sources = output_states(relation)
    node_index = {state: index for index, state in enumerate(nodes)}
    missing = [state for state in sources if state not in node_index]
    if missing:
        raise AssertionError("corner outputs absent from depth-six edge graph")
    distance = np.full(
        (len(sources), len(nodes)), INF, dtype=np.int16
    )
    for source_index, state in enumerate(sources):
        distance[source_index, node_index[state]] = 0
    incoming_by_target: list[list[tuple[int, int]]] = [
        [] for _node in nodes
    ]
    for edge in edges:
        incoming_by_target[node_index[edge.target]].append(
            (node_index[edge.source], edge.weight)
        )

    target_lengths = {n - 12: n for n in ordered_ns}
    rows = []
    prior: tuple[int, np.ndarray] | None = None
    for length in range(max(target_lengths) + 1):
        if length in target_lengths:
            n = target_lengths[length]
            transfer = side_transfer(
                distance, relation, nodes, sources
            )
            finite = transfer < INF
            if not np.any(finite):
                anchored = {
                    "cycle_at_or_below_target_exists": False,
                    "reason": "side transfer has no finite entries",
                }
            else:
                anchored = anchored_four_cycle_test(
                    transfer, depth4_wastage(n)
                )
            recurrence = None
            if prior is not None and prior[0] == length - 8:
                recurrence = recurrence_comparison(prior[1], distance)
                recurrence["previous_n"] = n - 8
            rows.append(
                {
                    "n": n,
                    "edge_length": length,
                    "old_depth5_target": depth4_wastage(n),
                    "restricted_path_finite_count": int(
                        np.count_nonzero(distance < INF)
                    ),
                    "restricted_path_sha256": hashlib.sha256(
                        distance.tobytes()
                    ).hexdigest(),
                    "side_transfer_finite_count": int(finite.sum()),
                    "side_transfer_sha256": hashlib.sha256(
                        transfer.tobytes()
                    ).hexdigest(),
                    "anchored_four_cycle_test": anchored,
                    "equality_lift_exists": anchored[
                        "cycle_at_or_below_target_exists"
                    ],
                    "comparison_to_n_minus_8": recurrence,
                }
            )
            prior = (length, distance.copy())
        if length == max(target_lengths):
            break
        following = np.full_like(distance, INF)
        for target, incoming in enumerate(incoming_by_target):
            for source, weight in incoming:
                np.minimum(
                    following[:, target],
                    distance[:, source] + weight,
                    out=following[:, target],
                )
        distance = following

    by_n = {row["n"]: row for row in rows}
    bases = (16, 24, 32, 40)
    bases_excluded = all(
        n in by_n and not by_n[n]["equality_lift_exists"]
        for n in bases
    )
    recurrence_rows = [
        row
        for row in rows
        if row["comparison_to_n_minus_8"]
        and row["comparison_to_n_minus_8"][
            "inducts_for_all_later_lengths"
        ]
    ]
    certified = bool(bases_excluded and recurrence_rows)
    return {
        "schema": "corrected-depth6-equality-corner-ring-v1",
        "status": (
            "safe equality-corner overapproximation with exact "
            "zero-new-wastage depth-six side matrices"
        ),
        "language": {
            "depth5_equality_corner_mapping_count": len(mappings),
            "finite_equality_corner_mapping_audit": (
                finite_mapping_audit
            ),
            "later_mapping_set_proof": (
                "The depth-five transfer's complete D[L+8]=D[L]+3 equality from "
                "n=40 onward shifts every path entry and every side "
                "entry by the same amount. Therefore the equality-cycle "
                "support and minimum corner-decomposition equations are "
                "unchanged at every later residue-zero size."
            ),
            "depth6_corner_output_state_count": len(sources),
            "depth6_edge_state_count": len(nodes),
            "depth6_edge_transition_count": len(edges),
            "depth6_corner_statistics": corner_statistics,
        },
        "rows": rows,
        "all_n_upper": {
            "domain": "n>=16 and n mod 8=0",
            "finite_bases": list(bases),
            "all_finite_bases_exclude_equality_lifts": bases_excluded,
            "first_complete_matrix_recurrence_n": (
                recurrence_rows[0]["n"] if recurrence_rows else None
            ),
            "certified": certified,
            "consequence": (
                "Every depth-six ring at the old target would project "
                "to a depth-five equality ring and hence use one of the "
                "retained equality corner mappings. Its new layer has "
                "zero wastage, so it would appear in this ring. Exclusion "
                "therefore proves B6>B5 and C(n)<=U3(n)-1."
            ),
        },
        "claim_scope": (
            "All corrected depth-six zero-additional-wastage lifts whose "
            "outer depth-five corner is supported by a residue-zero "
            "equality ring. This is complete for testing cost B5, but "
            "does not enumerate positive-added-wastage depth-six rings."
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
    parser.add_argument(
        "--n",
        type=int,
        nargs="+",
        default=[16, 24, 32, 40, 48, 56],
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = finalize(build(args.n))
    if args.verify:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored corrected ring certificate differs")
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
                "language": {
                    key: value
                    for key, value in record["language"].items()
                    if key != "depth6_corner_statistics"
                },
                "rows": [
                    {
                        "n": row["n"],
                        "target": row["old_depth5_target"],
                        "equality_lift_exists": row[
                            "equality_lift_exists"
                        ],
                        "recurrence": row[
                            "comparison_to_n_minus_8"
                        ],
                    }
                    for row in record["rows"]
                ],
                "all_n_upper": record["all_n_upper"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
