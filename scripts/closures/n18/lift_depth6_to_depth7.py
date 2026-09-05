#!/usr/bin/env python3
"""Lift all tied n=18 depth-six equality corners to depth seven."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BOUNDARY = ROOT / "scripts" / "boundary"
N17 = ROOT / "scripts" / "closures" / "n17"
N16 = ROOT / "scripts" / "closures" / "n16"
CERTIFICATES = ROOT / "certificates" / "exact_closures" / "n18"
ORBIT5 = CERTIFICATES / "depth5_equality_orbits.json"
ORBIT6 = CERTIFICATES / "depth6_equality_orbits.json"
OUTPUT = CERTIFICATES / "depth7_equality_lift.json"
N = 18
TARGET = 36

for directory in (HERE, BOUNDARY, N17, N16):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_depth5_ring import path_matrix  # noqa: E402
import certify_depth6_equality_lift as lift6  # noqa: E402
from count_depth6_physical_belts import (  # noqa: E402
    lift_retained_physical_corners,
)
from probe_depth7_full_cover import (  # noqa: E402
    lift_edges_generic,
    lift_minimum_corners_generic,
)
sys.path.insert(0,str(ROOT/"src/engines/equality_support"))
from equality_support import complete_equality_support  # noqa: E402


def reconstruct_depth5() -> tuple[
    list[tuple[int, int]],
    list[kernel.Edge],
    list[tuple[int, int]],
    object,
    object,
    list[dict],
]:
    orbit5 = json.loads(ORBIT5.read_text(encoding="utf-8"))
    lift6.N = N
    lift6.TARGET = TARGET
    lift6.configure_depth5()
    nodes5, edges5 = kernel.build_edge_graph()
    relation5, _ = kernel.build_corner_relation(set(nodes5))
    sources5 = lift6.output_states(relation5)
    paths5 = path_matrix(nodes5, edges5, sources5, N - 10)
    transfer5 = side_transfer(
        paths5, relation5, nodes5, sources5
    )
    mapping_keys5 = lift6.equality_mapping_keys(
        orbit5, nodes5, relation5, sources5, paths5, transfer5
    )
    all_patches5, _ = lift6.enumerate_full_depth5_corners(set(nodes5))
    equality_patches5 = [
        row
        for row in all_patches5
        if (row["incoming"], row["outgoing"], row["cost"])
        in mapping_keys5
    ]
    return (
        nodes5,
        edges5,
        sources5,
        paths5,
        transfer5,
        equality_patches5,
    )


def build() -> dict:
    (
        _nodes5,
        edges5,
        _sources5,
        _paths5,
        _transfer5,
        equality_patches5,
    ) = reconstruct_depth5()
    relation6, relation6_statistics = (
        lift6.build_complete_depth6_corner_relation(
            equality_patches5, edges5
        )
    )
    nodes6, edges6, sources6, paths6, transfer6 = (
        lift6.depth6_transfer(relation6, N - 12)
    )
    orbit6 = json.loads(ORBIT6.read_text(encoding="utf-8"))
    mapping_keys6 = lift6.equality_mapping_keys(
        orbit6, nodes6, relation6, sources6, paths6, transfer6
    )
    retained_outgoing6 = {
        sources6[index]
        for index in orbit6["complete_equality_support"]["state_indices"]
    }
    by_outgoing6, physical6_statistics = (
        lift_retained_physical_corners(
            equality_patches5,
            edges5,
            retained_outgoing6,
        )
    )
    physical6 = [
        patch
        for rows in by_outgoing6.values()
        for patch in rows
        if (
            tuple(patch["incoming"]),
            tuple(patch["outgoing"]),
            int(patch["cost"]),
        )
        in mapping_keys6
    ]
    physical6.sort(
        key=lambda row: (
            row["incoming"],
            row["outgoing"],
            row["cost"],
            row["patch"],
        )
    )
    represented = {
        (
            tuple(patch["incoming"]),
            tuple(patch["outgoing"]),
            int(patch["cost"]),
        )
        for patch in physical6
    }
    if represented != mapping_keys6:
        raise AssertionError(
            "a supported depth-six mapping lacks a physical patch"
        )

    nodes7, edges7, edge7_statistics = lift_edges_generic(6, edges6)
    relation7, corner7_statistics = lift_minimum_corners_generic(
        6, physical6, edges6
    )
    sources7 = sorted(
        {tuple(row["outgoing"]) for row in relation7}
    )
    if set(sources7) - set(nodes7):
        raise AssertionError(
            "depth-seven corner output absent from edge graph"
        )
    paths7 = path_matrix(nodes7, edges7, sources7, N - 14)
    transfer7 = side_transfer(
        paths7, relation7, nodes7, sources7
    )
    support7 = complete_equality_support(
        transfer7, sources7, TARGET
    )
    record = {
        "schema": "n18-depth6-to-depth7-equality-lift-v1",
        "n": N,
        "target_population": 171,
        "target_total_wastage": TARGET,
        "depth6": {
            "edge_state_count": len(nodes6),
            "edge_transition_count": len(edges6),
            "corner_mapping_count": len(relation6),
            "corner_lift_statistics": relation6_statistics,
            "equality_mapping_key_count": len(mapping_keys6),
            "physical_equality_patch_count": len(physical6),
            "physical_equality_patch_sha256": hashlib.sha256(
                json.dumps(
                    physical6,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("ascii")
            ).hexdigest(),
            "physical_rebuild_statistics": physical6_statistics,
        },
        "depth7": {
            "edge_length": N - 14,
            "edge_state_count": len(nodes7),
            "edge_transition_count": len(edges7),
            "edge_lift_statistics": edge7_statistics,
            "corner_mapping_count": len(relation7),
            "corner_output_state_count": len(sources7),
            "corner_lift_statistics": corner7_statistics,
            "path_finite_count": int((paths7 < 30_000).sum()),
            "path_sha256": hashlib.sha256(
                paths7.tobytes()
            ).hexdigest(),
            "transfer_finite_count": int(
                (transfer7 < 30_000).sum()
            ),
            "transfer_sha256": hashlib.sha256(
                transfer7.tobytes()
            ).hexdigest(),
            "complete_equality_support": support7,
        },
        "consequence": {
            "connected_population_171_excluded": (
                support7["state_count"] == 0
            ),
            "connected_upper_bound": (
                170 if support7["state_count"] == 0 else 171
            ),
            "next_step": (
                "global connected population 171 excluded"
                if support7["state_count"] == 0
                else "lift tied depth-seven equality corners to depth eight"
            ),
        },
        "claim_scope": (
            "This excludes a 171-cell board only in the connected problem; "
            "the known disconnected ordinary 171-cell still life remains. "
            "Every tied physical depth-six equality corner is lifted with "
            "all adjacent depth-six edges and diagonal bits.  The depth-seven "
            "minimum relation may include positive-charge overapproximations; "
            "target-36 support can use only zero total added charge."
        ),
        "record_sha256_excluding_this_field": None,
    }
    canonical = json.dumps(
        record, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    record["record_sha256_excluding_this_field"] = hashlib.sha256(
        canonical
    ).hexdigest()
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record = build()
    if args.verify:
        if json.loads(args.output.read_text(encoding="utf-8")) != record:
            raise SystemExit("stored depth-seven equality lift differs")
        print(
            "VERIFIED",
            record["record_sha256_excluding_this_field"],
        )
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "depth6": record["depth6"],
                "depth7": {
                    key: record["depth7"][key]
                    for key in (
                        "edge_length",
                        "edge_state_count",
                        "edge_transition_count",
                        "corner_mapping_count",
                        "corner_output_state_count",
                        "complete_equality_support",
                    )
                },
                "consequence": record["consequence"],
                "record_sha256": record[
                    "record_sha256_excluding_this_field"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
