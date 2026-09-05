#!/usr/bin/env python3
"""Enumerate the complete depth-six n=18 target-36 equality support."""

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
CERTIFICATES = ROOT / "certificates" / "exact_closures" / "n18"
ORBIT5 = CERTIFICATES / "depth5_equality_orbits.json"
LIFT6 = CERTIFICATES / "depth6_equality_lift.json"
OUTPUT = CERTIFICATES / "depth6_equality_orbits.json"
N = 18
TARGET = 36

for directory in (HERE, BOUNDARY, N17):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import depth4_boundary_census as kernel  # noqa: E402
from certify_depth4_ring import side_transfer  # noqa: E402
from certify_depth5_ring import path_matrix  # noqa: E402
import certify_depth6_equality_lift as lift  # noqa: E402
sys.path.insert(0,str(ROOT/"src/engines/equality_support"))
from equality_support import complete_equality_support  # noqa: E402


def reconstruct() -> tuple[
    list[tuple[int, int]],
    list[kernel.Edge],
    list[tuple[int, int]],
    object,
    object,
    list[dict],
    dict,
]:
    orbit = json.loads(ORBIT5.read_text(encoding="utf-8"))
    lift.N = N
    lift.TARGET = TARGET
    lift.configure_depth5()
    nodes5, edges5 = kernel.build_edge_graph()
    relation5, _ = kernel.build_corner_relation(set(nodes5))
    sources5 = lift.output_states(relation5)
    paths5 = path_matrix(nodes5, edges5, sources5, N - 10)
    transfer5 = side_transfer(
        paths5, relation5, nodes5, sources5
    )
    if hashlib.sha256(transfer5.tobytes()).hexdigest() != orbit[
        "side_transfer"
    ]["sha256"]:
        raise AssertionError("depth-five transfer differs")
    mapping_keys = lift.equality_mapping_keys(
        orbit, nodes5, relation5, sources5, paths5, transfer5
    )
    all_patches, _ = lift.enumerate_full_depth5_corners(set(nodes5))
    equality_patches = [
        row
        for row in all_patches
        if (row["incoming"], row["outgoing"], row["cost"])
        in mapping_keys
    ]
    relation6, statistics6 = (
        lift.build_complete_depth6_corner_relation(
            equality_patches, edges5
        )
    )
    nodes6, edges6, sources6, paths6, transfer6 = (
        lift.depth6_transfer(relation6, N - 12)
    )
    return (
        nodes6,
        edges6,
        sources6,
        paths6,
        transfer6,
        relation6,
        statistics6,
    )


def build() -> dict:
    (
        nodes,
        edges,
        sources,
        paths,
        transfer,
        relation,
        statistics,
    ) = reconstruct()
    stored_lift = json.loads(LIFT6.read_text(encoding="utf-8"))
    if (
        hashlib.sha256(transfer.tobytes()).hexdigest()
        != stored_lift["depth6"]["side_transfer_sha256"]
    ):
        raise AssertionError("depth-six transfer differs from lift record")
    support = complete_equality_support(transfer, sources, TARGET)
    record = {
        "schema": "n18-depth6-equality-orbit-support-v1",
        "n": N,
        "depth": 6,
        "edge_length": N - 12,
        "target_population": 171,
        "target_total_wastage": TARGET,
        "language": {
            "edge_state_count": len(nodes),
            "edge_transition_count": len(edges),
            "corner_mapping_count": len(relation),
            "corner_output_state_count": len(sources),
            "corner_lift_statistics": statistics,
            "path_finite_count": int((paths < 30_000).sum()),
            "path_sha256": hashlib.sha256(paths.tobytes()).hexdigest(),
            "transfer_finite_count": int((transfer < 30_000).sum()),
            "transfer_sha256": hashlib.sha256(
                transfer.tobytes()
            ).hexdigest(),
        },
        "complete_equality_support": support,
        "next_step": (
            "lift every tied supported depth-six corner to depth seven"
            if support["state_count"]
            else "population 171 excluded"
        ),
        "claim_scope": (
            "Complete target-36 state/arc support inside the safe depth-six "
            "lift of every tied physical depth-five equality corner.  This "
            "is a global boundary necessary condition, not a full board."
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
            raise SystemExit("stored depth-six equality support differs")
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
                "language": record["language"],
                "complete_equality_support": record[
                    "complete_equality_support"
                ],
                "record_sha256": record[
                    "record_sha256_excluding_this_field"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
