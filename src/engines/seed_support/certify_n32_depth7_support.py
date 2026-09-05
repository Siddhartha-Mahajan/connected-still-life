#!/usr/bin/env python3
"""Lift the complete n=32, P=528 physical language to depth seven."""

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
DEPTH5 = HERE / "outputs" / "n32_population528_depth5_support.json"
INPUT = HERE / "outputs" / "n32_population528_depth6_support.json"
OUTPUT = HERE / "outputs" / "n32_population528_depth7_support.json"
N = 32
TARGET_POPULATION = 528
TARGET_WASTAGE = 64
DENSE_ENTRY_LIMIT = 160_000_000


def load_streaming() -> Any:
    specification = importlib.util.spec_from_file_location(
        "seed_support_module_depth7_streaming",
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
    depth5 = json.loads(DEPTH5.read_text(encoding="utf-8"))
    source_text = INPUT.read_text(encoding="utf-8")
    source = json.loads(source_text)
    if source["schema"] != "n32-population528-depth6-supported-streaming-v1":
        raise AssertionError("wrong depth-six input schema")
    physical6 = source["retained_physical_classes"]
    minimum6 = int(source["conclusion"]["minimum"])
    allowance = TARGET_WASTAGE - minimum6

    streaming = load_streaming()
    engine = configured_engine(streaming)
    engine.configure(5)
    nodes5, edges5 = engine.kernel.build_edge_graph()
    nodes6, edges6, _lift56 = engine.bounded_edge_lift(
        5,
        edges5,
        TARGET_WASTAGE - int(depth5["conclusion"]["minimum"]),
    )
    stage6 = source["stage"]
    if (
        len(nodes6) != stage6["edge_state_count"]
        or len(edges6) != stage6["edge_transition_count"]
        or engine.edge_digest(edges6) != stage6["edge_sha256"]
    ):
        raise AssertionError("reconstructed depth-six edge graph changed")

    nodes7, edges7, edge_lift = engine.bounded_edge_lift(
        6,
        edges6,
        allowance,
    )
    relation7, pass1 = streaming.streamed_minimum_relation(
        engine,
        6,
        physical6,
        edges6,
        allowance,
        crosscheck_incremental=False,
    )
    sources7 = engine.output_states(relation7)
    dense_entries = len(sources7) * len(nodes7)
    if dense_entries <= DENSE_ENTRY_LIMIT:
        analysis_method = "dense_exact_min_plus"
        stage7, artifacts = streaming.analyze_abstract_depth(
            engine,
            7,
            nodes7,
            edges7,
            relation7,
        )
    else:
        analysis_method = "sparse_bounded_exact_anchor"
        stage7, artifacts = streaming.analyze_sparse_abstract_depth(
            engine,
            7,
            nodes7,
            edges7,
            relation7,
        )

    if artifacts is None or not stage7["target_survives"]:
        physical7 = []
        pass2 = {"streamed_pass_not_needed": True}
    else:
        physical7, pass2 = streaming.streamed_supported_physical(
            engine,
            6,
            physical6,
            edges6,
            allowance,
            artifacts["thresholds"],
            crosscheck_incremental=False,
        )
        stage7["physical_candidate_count"] = pass1[
            "connected_logical_extension_count"
        ]
        stage7["physical_candidate_representation"] = (
            "streamed logical extensions; unsupported classes never interned"
        )
        stage7["physical_filter"] = {
            "retained_physical_patch_count": len(physical7),
            "retained_physical_patch_sha256": streaming.digest_json(physical7),
            "safe_filter": (
                "Every logical extension is tested against the exact maximum "
                "physical charge allowed by a supported endpoint arc before "
                "its connectivity-future class is interned."
            ),
        }
        if not physical7:
            stage7["target_survives"] = False
            stage7["exclusion_stage"] = "no_physical_supported_corner"

    return {
        "schema": "n32-population528-depth7-supported-streaming-v1",
        "scope": {
            "n": N,
            "target_population": TARGET_POPULATION,
            "target_wastage": TARGET_WASTAGE,
            "depth": 7,
            "straight_side_length": N - 14,
            "whole_board_search": False,
        },
        "source": {
            "path": str(INPUT.relative_to(PROJECT)),
            "sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "physical_class_count": len(physical6),
        },
        "analysis_selection": {
            "method": analysis_method,
            "dense_matrix_entry_count": dense_entries,
            "dense_entry_limit": DENSE_ENTRY_LIMIT,
            "sparse_fallback_is_exact": True,
        },
        "edge_lift": edge_lift,
        "minimum_relation_count": len(relation7),
        "minimum_relation_sha256": streaming.digest_json(relation7),
        "pass1_endpoint_stream": pass1,
        "stage": stage7,
        "pass2_physical_stream": pass2,
        "retained_physical_classes": physical7,
        "conclusion": {
            "minimum": stage7.get("minimum"),
            "global_slack": stage7.get("global_slack"),
            "target_survives_depth7": stage7["target_survives"],
            "retained_physical_class_count": len(physical7),
            "population528_decided": not stage7["target_survives"],
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
            raise SystemExit("stored n=32 depth-seven support differs")
        print(f"VERIFIED {digest}")
        return
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(PROJECT)),
                "sha256": digest,
                "analysis": record["analysis_selection"],
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
                    "target_survives_depth7"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
