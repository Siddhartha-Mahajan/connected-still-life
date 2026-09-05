#!/usr/bin/env python3
"""Compose the exact depth-four edge and corner languages around a square."""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from depth4_boundary_census import (
    Edge,
    State,
    build_corner_relation,
    build_edge_graph,
)


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "outputs" / "depth4_ring_certificate.json"
CENSUS = HERE / "outputs" / "depth4_boundary_census.json"
INF = 10**7
DEPTH4_RESIDUE_VECTOR = (18, 23, 18, 23, 20, 15, 26, 11)


def output_states(
    relation: Sequence[dict[str, Any]],
) -> list[State]:
    return sorted({tuple(row["outgoing"]) for row in relation})


def restricted_path_matrices(
    nodes: Sequence[State],
    edges: Sequence[Edge],
    sources: Sequence[State],
    lengths: set[int],
    *,
    period_search_limit: int,
) -> tuple[dict[int, np.ndarray], dict[str, Any] | None]:
    node_index = {state: index for index, state in enumerate(nodes)}
    distance = np.full(
        (len(sources), len(nodes)), INF, dtype=np.int32
    )
    for source_index, state in enumerate(sources):
        distance[source_index, node_index[state]] = 0
    results = {0: distance.copy()} if 0 in lengths else {}
    history: deque[tuple[int, np.ndarray]] = deque(
        [(0, distance.copy())], maxlen=9
    )
    certificate = None
    last_required = max(lengths)

    incoming_by_target: list[list[tuple[int, int]]] = [
        [] for _node in nodes
    ]
    for edge in edges:
        incoming_by_target[node_index[edge.target]].append(
            (node_index[edge.source], edge.weight)
        )

    for length in range(
        1, max(last_required, period_search_limit) + 1
    ):
        following = np.full_like(distance, INF)
        for target, incoming in enumerate(incoming_by_target):
            for source, weight in incoming:
                np.minimum(
                    following[:, target],
                    distance[:, source] + weight,
                    out=following[:, target],
                )
        distance = following
        if length in lengths:
            results[length] = distance.copy()
        history.append((length, distance.copy()))
        if len(history) == 9 and certificate is None:
            old_length, old = history[0]
            old_finite = old < INF
            new_finite = distance < INF
            periodic = np.array_equal(
                old_finite, new_finite
            ) and np.array_equal(
                distance[new_finite], old[new_finite] + 3
            )
            if periodic:
                certificate = {
                    "start_length": old_length,
                    "period": 8,
                    "weight_increment": 3,
                    "source_state_count": len(sources),
                    "target_state_count": len(nodes),
                    "finite_entry_count": int(new_finite.sum()),
                    "matrix_sha256_at_start": hashlib.sha256(
                        old.tobytes()
                    ).hexdigest(),
                    "matrix_sha256_after_period": hashlib.sha256(
                        distance.tobytes()
                    ).hexdigest(),
                    "induction": (
                        "D[L+1]=D[L] min-plus E on the fixed edge graph; "
                        "one complete restricted matrix equality implies "
                        "the same equality for all later L"
                    ),
                }
        if length >= last_required and certificate is not None:
            break
    return results, certificate


def side_transfer(
    paths: np.ndarray,
    relation: Sequence[dict[str, Any]],
    nodes: Sequence[State],
    sources: Sequence[State],
) -> np.ndarray:
    node_index = {state: index for index, state in enumerate(nodes)}
    source_index = {
        state: index for index, state in enumerate(sources)
    }
    result = np.full(
        (len(sources), len(sources)), INF, dtype=np.int32
    )
    for corner in relation:
        incoming = node_index[tuple(corner["incoming"])]
        outgoing = source_index[tuple(corner["outgoing"])]
        np.minimum(
            result[:, outgoing],
            paths[:, incoming] + int(corner["cost"]),
            out=result[:, outgoing],
        )
    return result


def four_side_minimum(matrix: np.ndarray) -> tuple[int, tuple[int, int]]:
    square = np.full_like(matrix, INF)
    for middle in range(matrix.shape[0]):
        np.minimum(
            square,
            matrix[:, middle, None] + matrix[middle, None, :],
            out=square,
        )
    candidates = square + square.T
    flat = int(np.argmin(candidates))
    first, opposite = divmod(flat, matrix.shape[0])
    return int(candidates[first, opposite]), (first, opposite)


def population_upper(n: int, wastage_lower: int) -> int:
    return (2 * n * n + 4 * n - wastage_lower) // 4


def formula_upper(n: int) -> int:
    return (
        4 * n * n
        + 5 * n
        - DEPTH4_RESIDUE_VECTOR[n % 8]
    ) // 8


def build(
    n_min: int,
    n_max: int,
    period_search_limit: int,
) -> dict[str, Any]:
    if n_min < 10 or n_max < n_min:
        raise ValueError("require 10 <= n_min <= n_max")
    stored_census = json.loads(CENSUS.read_text(encoding="utf-8"))
    nodes, edges = build_edge_graph()
    relation, corner_statistics = build_corner_relation(set(nodes))
    sources = output_states(relation)
    if (
        len(nodes) != stored_census["edge_graph"]["state_count"]
        or len(edges)
        != stored_census["edge_graph"]["transition_count"]
        or len(relation)
        != stored_census["corner_relation"][
            "minimum_cost_transition_count"
        ]
    ):
        raise AssertionError("depth-four census mismatch")

    lengths = {
        n - 2 * 4 for n in range(n_min, n_max + 1)
    }
    path_matrices, period = restricted_path_matrices(
        nodes,
        edges,
        sources,
        lengths,
        period_search_limit=period_search_limit,
    )

    rows = []
    for n in range(n_min, n_max + 1):
        length = n - 8
        transfer = side_transfer(
            path_matrices[length], relation, nodes, sources
        )
        wastage, minimizer = four_side_minimum(transfer)
        rows.append(
            {
                "n": n,
                "edge_length": length,
                "boundary_wastage_lower_bound": wastage,
                "population_upper_bound": population_upper(
                    n, wastage
                ),
                "formula_population_upper": formula_upper(n),
                "matches_formula": (
                    population_upper(n, wastage)
                    == formula_upper(n)
                ),
                "opposite_output_state_indices": list(minimizer),
                "opposite_output_states": [
                    list(sources[index]) for index in minimizer
                ],
                "side_transfer_finite_count": int(
                    np.count_nonzero(transfer < INF)
                ),
                "side_transfer_sha256": hashlib.sha256(
                    transfer.tobytes()
                ).hexdigest(),
            }
        )

    recurrences = []
    by_n = {row["n"]: row for row in rows}
    for n in range(n_min, n_max - 7):
        recurrences.append(
            {
                "n": n,
                "wastage_increment": (
                    by_n[n + 8][
                        "boundary_wastage_lower_bound"
                    ]
                    - by_n[n]["boundary_wastage_lower_bound"]
                ),
                "population_upper_increment": (
                    by_n[n + 8]["population_upper_bound"]
                    - by_n[n]["population_upper_bound"]
                ),
            }
        )

    formula_finite_match = all(
        row["matches_formula"] for row in rows
    )
    first_recurrent_n = (
        period["start_length"] + 8 if period is not None else None
    )
    induction_bases_available = (
        first_recurrent_n is not None
        and n_min <= first_recurrent_n
        and n_max >= first_recurrent_n + 7
    )
    induction_base_match = (
        all(
            by_n[n]["matches_formula"]
            for n in range(
                first_recurrent_n, first_recurrent_n + 8
            )
        )
        if induction_bases_available
        else False
    )
    all_n_formula_certified = (
        formula_finite_match
        and induction_bases_available
        and induction_base_match
        and n_min <= 14
    )
    return {
        "schema": "depth4-four-corner-ring-certificate-v1",
        "status": "rigorous depth-four boundary relaxation",
        "charged_region": (
            "depth-four boundary belt plus adjusted orthogonal exterior"
        ),
        "language": {
            "edge_state_count": len(nodes),
            "edge_transition_count": len(edges),
            "corner_transition_count": len(relation),
            "corner_output_state_count": len(sources),
            "corner_statistics": {
                key: corner_statistics[key]
                for key in (
                    "valid_patch_count",
                    "edge_extendible_patch_count",
                    "minimum_cost_transition_count",
                )
            },
        },
        "restricted_edge_matrix_period": period,
        "range": {"n_min": n_min, "n_max": n_max},
        "rows": rows,
        "recurrence_differences": recurrences,
        "all_n_upper_formula": {
            "domain": "n>=14",
            "formula": (
                "floor((4*n^2+5*n-c[n mod 8])/8)"
            ),
            "residue_vector_c_0_to_7": list(
                DEPTH4_RESIDUE_VECTOR
            ),
            "finite_range_matches": formula_finite_match,
            "induction_first_n": first_recurrent_n,
            "eight_induction_bases_available": (
                induction_bases_available
            ),
            "eight_induction_bases_match": induction_base_match,
            "certified_for_every_n_at_least_14": (
                all_n_formula_certified
            ),
            "proof": (
                "Finite exact four-side values cover n=14 through the "
                "eight recurrence bases. The complete restricted edge "
                "matrix equality D[L+8]=D[L]+3 implies every finite side "
                "transfer rises by 3, so every four-side closed walk rises "
                "by 12. The displayed quadratic formula has the same "
                "recurrence."
            ),
        },
        "claim_scope": (
            "Every stable connected still life with population greater "
            "than four is block-free, so its depth-four belt is represented "
            "here. Uncharged central wastage is nonnegative. Connectivity "
            "partitions are not yet imposed."
        ),
        "record_sha256_excluding_this_field": None,
    }


def finalize(record: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record["record_sha256_excluding_this_field"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return record


def summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "language": record["language"],
        "restricted_edge_matrix_period": record[
            "restricted_edge_matrix_period"
        ],
        "rows": [
            {
                "n": row["n"],
                "wastage": row[
                    "boundary_wastage_lower_bound"
                ],
                "population_upper": row["population_upper_bound"],
                "formula_upper": row["formula_population_upper"],
            }
            for row in record["rows"]
        ],
        "all_n_upper_formula": record["all_n_upper_formula"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-min", type=int, default=14)
    parser.add_argument("--n-max", type=int, default=40)
    parser.add_argument("--period-search-limit", type=int, default=96)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = finalize(
        build(args.n_min, args.n_max, args.period_search_limit)
    )
    if args.verify:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("stored depth-four ring certificate differs")
        print("VERIFIED", args.output)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary(record), indent=2))


if __name__ == "__main__":
    main()
