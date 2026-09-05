#!/usr/bin/env python3
"""Certify the complete depth-five physical support for n=32, P=528."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
STREAMING_ENGINE = (
    HERE.parent
    / "streaming"
    / "certify_n19_supported_streaming.py"
)
OUTPUT = HERE / "outputs" / "n32_population528_depth5_support.json"
N = 32
TARGET_POPULATION = 528
TARGET_WASTAGE = 64
START_DEPTH = 5
TERMINAL_DEPTH = 16


def load_streaming() -> Any:
    specification = importlib.util.spec_from_file_location(
        "seed_support_module_streaming_engine",
        STREAMING_ENGINE,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load the validated streaming engine")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    module.N = N
    module.TARGET_POPULATION = TARGET_POPULATION
    module.TARGET_WASTAGE = TARGET_WASTAGE
    module.START_DEPTH = START_DEPTH
    module.TERMINAL_DEPTH = TERMINAL_DEPTH
    return module


def build() -> dict[str, Any]:
    streaming = load_streaming()
    connected = streaming.load_connected_module()
    connected.N = N
    connected.TARGET_POPULATION = TARGET_POPULATION
    connected.TARGET_WASTAGE = TARGET_WASTAGE
    engine = connected.load_engine()
    engine.N = N
    engine.TARGET_POPULATION = TARGET_POPULATION
    engine.TARGET_WASTAGE = TARGET_WASTAGE
    engine.START_DEPTH = START_DEPTH
    engine.TERMINAL_DEPTH = TERMINAL_DEPTH
    engine.frontier_signature = connected.frontier_signature

    engine.configure(START_DEPTH)
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
        raise AssertionError("target unexpectedly fails at depth five")
    if stage["edge_length"] != N - 2 * START_DEPTH:
        raise AssertionError("wrong depth-five straight length")
    if stage["global_slack"] != TARGET_WASTAGE - minimum:
        raise AssertionError("wrong global slack")

    return {
        "schema": "n32-population528-depth5-physical-support-v1",
        "scope": {
            "n": N,
            "target_population": TARGET_POPULATION,
            "target_wastage": TARGET_WASTAGE,
            "depth": START_DEPTH,
            "straight_side_length": N - 2 * START_DEPTH,
            "whole_board_search": False,
        },
        "theorem": {
            "mandatory_anchor_threshold": TARGET_WASTAGE // 4,
            "support_completeness": (
                "Every directed four-cycle of total charge at most 64 has "
                "an arc of charge at most 16. Every such anchor and every "
                "three-arc return is included by the exact min-plus support."
            ),
            "physical_completeness": (
                "All physical depth-five corners are enumerated. A corner "
                "is retained exactly when its excess over a supported side "
                "minimum fits the global slack, then quotiented only by its "
                "exact exposed-frontier connectivity future."
            ),
        },
        "engine": {
            "path": str(STREAMING_ENGINE.relative_to(PROJECT)),
            "sha256": hashlib.sha256(STREAMING_ENGINE.read_bytes()).hexdigest(),
        },
        "initial_census": {
            "edge_state_count": len(nodes),
            "edge_transition_count": len(edges),
            "edge_sha256": engine.edge_digest(edges),
            "minimum_corner_relation_statistics": relation_statistics,
            "full_physical_corner_statistics": physical_statistics,
        },
        "stage": stage,
        "retained_physical_classes": retained,
        "conclusion": {
            "minimum": minimum,
            "global_slack": TARGET_WASTAGE - minimum,
            "target_survives_depth5": stage["target_survives"],
            "retained_physical_class_count": len(retained),
            "population528_decided": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    record = build()
    rendered = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    if arguments.verify:
        if json.loads(OUTPUT.read_text(encoding="utf-8")) != json.loads(rendered):
            raise SystemExit("stored n=32 depth-five support differs")
        print(f"VERIFIED {digest}")
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(PROJECT)),
                "sha256": digest,
                "minimum": record["conclusion"]["minimum"],
                "global_slack": record["conclusion"]["global_slack"],
                "support_state_count": record["stage"]["support_union"][
                    "state_count"
                ],
                "support_arc_count": record["stage"]["support_union"][
                    "arc_count"
                ],
                "retained_physical_class_count": record["conclusion"][
                    "retained_physical_class_count"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
