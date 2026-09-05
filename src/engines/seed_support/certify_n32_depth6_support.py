#!/usr/bin/env python3
"""Lift the complete n=32, P=528 physical language to depth six."""

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
INPUT = HERE / "outputs" / "n32_population528_depth5_support.json"
OUTPUT = HERE / "outputs" / "n32_population528_depth6_support.json"
N = 32
TARGET_POPULATION = 528
TARGET_WASTAGE = 64


def load_streaming() -> Any:
    specification = importlib.util.spec_from_file_location(
        "seed_support_module_depth6_streaming",
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
    module.START_DEPTH = 5
    module.TERMINAL_DEPTH = 16
    return module


def configured_engine(streaming: Any) -> Any:
    connected = streaming.load_connected_module()
    connected.N = N
    connected.TARGET_POPULATION = TARGET_POPULATION
    connected.TARGET_WASTAGE = TARGET_WASTAGE
    engine = connected.load_engine()
    engine.N = N
    engine.TARGET_POPULATION = TARGET_POPULATION
    engine.TARGET_WASTAGE = TARGET_WASTAGE
    engine.START_DEPTH = 5
    engine.TERMINAL_DEPTH = 16
    engine.frontier_signature = connected.frontier_signature
    return engine


def build() -> dict[str, Any]:
    source_text = INPUT.read_text(encoding="utf-8")
    source = json.loads(source_text)
    if source["schema"] != "n32-population528-depth5-physical-support-v1":
        raise AssertionError("wrong depth-five input schema")
    physical5 = source["retained_physical_classes"]
    minimum5 = int(source["conclusion"]["minimum"])
    allowance = TARGET_WASTAGE - minimum5

    streaming = load_streaming()
    engine = configured_engine(streaming)
    engine.configure(5)
    nodes5, edges5 = engine.kernel.build_edge_graph()
    initial = source["initial_census"]
    if (
        len(nodes5) != initial["edge_state_count"]
        or len(edges5) != initial["edge_transition_count"]
        or engine.edge_digest(edges5) != initial["edge_sha256"]
    ):
        raise AssertionError("reconstructed depth-five edge graph changed")

    nodes6, edges6, edge_lift = engine.bounded_edge_lift(
        5,
        edges5,
        allowance,
    )
    relation6, pass1 = streaming.streamed_minimum_relation(
        engine,
        5,
        physical5,
        edges5,
        allowance,
        crosscheck_incremental=False,
    )
    stage6, artifacts = streaming.analyze_abstract_depth(
        engine,
        6,
        nodes6,
        edges6,
        relation6,
    )
    if artifacts is None or not stage6["target_survives"]:
        physical6 = []
        pass2 = {"streamed_pass_not_needed": True}
    else:
        physical6, pass2 = streaming.streamed_supported_physical(
            engine,
            5,
            physical5,
            edges5,
            allowance,
            artifacts["thresholds"],
            crosscheck_incremental=False,
        )
        stage6["physical_candidate_count"] = pass1[
            "connected_logical_extension_count"
        ]
        stage6["physical_candidate_representation"] = (
            "streamed logical extensions; unsupported classes never interned"
        )
        stage6["physical_filter"] = {
            "retained_physical_patch_count": len(physical6),
            "retained_physical_patch_sha256": streaming.digest_json(physical6),
            "safe_filter": (
                "Every logical extension is tested against the exact maximum "
                "physical charge allowed by a supported endpoint arc before "
                "its connectivity-future class is interned."
            ),
        }
        if not physical6:
            stage6["target_survives"] = False
            stage6["exclusion_stage"] = "no_physical_supported_corner"

    return {
        "schema": "n32-population528-depth6-supported-streaming-v1",
        "scope": {
            "n": N,
            "target_population": TARGET_POPULATION,
            "target_wastage": TARGET_WASTAGE,
            "depth": 6,
            "straight_side_length": N - 12,
            "whole_board_search": False,
        },
        "source": {
            "path": str(INPUT.relative_to(PROJECT)),
            "sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "physical_class_count": len(physical5),
        },
        "theorem": {
            "support_before_materialization": (
                "Endpoint minima and complete four-cycle support depend only "
                "on ordered boundary states and charge. Therefore unsupported "
                "physical connectivity classes can be rejected before "
                "interning without losing a target completion."
            ),
            "incremental_connectivity": (
                "The exposed-frontier partition is advanced by the exact "
                "contacts of the appended L-shaped layer; an old component "
                "with no new-layer contact is permanently sealed and cannot "
                "occur in a connected completion."
            ),
        },
        "edge_lift": edge_lift,
        "minimum_relation_count": len(relation6),
        "minimum_relation_sha256": streaming.digest_json(relation6),
        "pass1_endpoint_stream": pass1,
        "stage": stage6,
        "pass2_physical_stream": pass2,
        "retained_physical_classes": physical6,
        "conclusion": {
            "minimum": stage6.get("minimum"),
            "global_slack": stage6.get("global_slack"),
            "target_survives_depth6": stage6["target_survives"],
            "retained_physical_class_count": len(physical6),
            "population528_decided": not stage6["target_survives"],
            "decision_if_empty": "C(32)<=527",
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
            raise SystemExit("stored n=32 depth-six support differs")
        print(f"VERIFIED {digest}")
        return
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(PROJECT)),
                "sha256": digest,
                "edge_state_count": record["stage"]["edge_state_count"],
                "edge_transition_count": record["stage"][
                    "edge_transition_count"
                ],
                "minimum_relation_count": record["minimum_relation_count"],
                "minimum": record["conclusion"]["minimum"],
                "global_slack": record["conclusion"]["global_slack"],
                "support_arc_count": record["stage"].get(
                    "support_union", {}
                ).get("arc_count"),
                "retained_physical_class_count": record["conclusion"][
                    "retained_physical_class_count"
                ],
                "target_survives": record["conclusion"][
                    "target_survives_depth6"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
