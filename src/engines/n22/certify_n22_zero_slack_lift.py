#!/usr/bin/env python3
"""Lift the exact zero-slack n=22 population-252 language through depth 11."""

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
BASE_PATH = (
    HERE.parent
    / "seed_support"
    / "certify_n32_depth7_support.py"
)
N = 22
TARGET_POPULATION = 252
TARGET_WASTAGE = 48
TERMINAL_DEPTH = 11
DENSE_ENTRY_LIMIT = 160_000_000


def certificate_path(depth: int) -> Path:
    if depth == 5:
        name = "n22_population252_depth5_support.json"
    elif depth == 6:
        name = "n22_population252_depth6_support.json"
    elif depth == 7:
        name = "n22_population252_depth7_support.json"
    else:
        name = f"n22_population252_depth{depth}_zero_slack_support.json"
    return PROJECT / "certificates" / "exact_closures" / "n22" / name


def load_base() -> Any:
    specification = importlib.util.spec_from_file_location(
        "n22_module_zero_slack_base", BASE_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load validated streaming engine")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    module.N = N
    module.TARGET_POPULATION = TARGET_POPULATION
    module.TARGET_WASTAGE = TARGET_WASTAGE
    return module


def reconstruct_previous(engine: Any, previous_depth: int) -> tuple[list[Any], list[Any]]:
    engine.configure(5)
    nodes, edges = engine.kernel.build_edge_graph()
    for old_depth in range(5, previous_depth):
        allowance = 3 if old_depth == 5 else 0
        nodes, edges, _lift = engine.bounded_edge_lift(
            old_depth, edges, allowance
        )
    return nodes, edges


def build(depth: int) -> dict[str, Any]:
    if depth < 8 or depth > TERMINAL_DEPTH:
        raise ValueError("depth must be between 8 and 11")
    previous_depth = depth - 1
    input_path = certificate_path(previous_depth)
    source_text = input_path.read_text(encoding="utf-8")
    source = json.loads(source_text)
    physical_previous = source["retained_physical_classes"]
    minimum_previous = int(source["conclusion"]["minimum"])
    allowance = TARGET_WASTAGE - minimum_previous
    if allowance != 0:
        raise AssertionError("input is not the certified zero-slack language")

    base = load_base()
    streaming = base.load_streaming()
    engine = base.configured_engine(streaming)
    engine.TERMINAL_DEPTH = TERMINAL_DEPTH
    nodes_previous, edges_previous = reconstruct_previous(
        engine, previous_depth
    )
    expected = source["stage"]
    if (
        len(nodes_previous) != expected["edge_state_count"]
        or len(edges_previous) != expected["edge_transition_count"]
        or engine.edge_digest(edges_previous) != expected["edge_sha256"]
    ):
        raise AssertionError("reconstructed preceding edge graph changed")

    if depth != TERMINAL_DEPTH:
        nodes, edges, edge_lift = engine.bounded_edge_lift(
            previous_depth, edges_previous, allowance
        )
    relation, pass1 = streaming.streamed_minimum_relation(
        engine,
        previous_depth,
        physical_previous,
        edges_previous,
        allowance,
        crosscheck_incremental=False,
    )
    if depth == TERMINAL_DEPTH:
        # At side length zero there is no straight edge segment to traverse.
        # The exact terminal transfer joins a corner mapping only when its
        # incoming state equals the preceding corner's outgoing state. The
        # union of relation endpoints is therefore the complete state set;
        # materializing the unused depth-eleven edge graph would add no
        # information and is avoided explicitly.
        nodes = sorted(
            {
                tuple(row["incoming"])
                for row in relation
            }
            | {
                tuple(row["outgoing"])
                for row in relation
            }
        )
        edges = []
        edge_lift = {
            "algorithm": "exact_zero_length_terminal_identity",
            "old_depth": previous_depth,
            "new_depth": depth,
            "edge_state_count": len(nodes),
            "edge_transition_count": 0,
            "proof": (
                "At N-2d=0 no straight edge transition occurs. The complete "
                "terminal transfer is the identity join between consecutive "
                "corner endpoints."
            ),
        }
    sources = engine.output_states(relation)
    dense_entries = len(sources) * len(nodes)
    if dense_entries <= DENSE_ENTRY_LIMIT:
        analysis_method = "dense_exact_min_plus"
        stage, artifacts = streaming.analyze_abstract_depth(
            engine, depth, nodes, edges, relation
        )
    else:
        analysis_method = "sparse_bounded_exact_anchor"
        stage, artifacts = streaming.analyze_sparse_abstract_depth(
            engine, depth, nodes, edges, relation
        )

    if artifacts is None or not stage["target_survives"]:
        physical = []
        pass2 = {"streamed_pass_not_needed": True}
    else:
        physical, pass2 = streaming.streamed_supported_physical(
            engine,
            previous_depth,
            physical_previous,
            edges_previous,
            allowance,
            artifacts["thresholds"],
            crosscheck_incremental=False,
        )
        stage["physical_candidate_count"] = pass1[
            "connected_logical_extension_count"
        ]
        stage["physical_candidate_representation"] = (
            "streamed zero-excess logical extensions; unsupported classes "
            "never interned"
        )
        stage["physical_filter"] = {
            "retained_physical_patch_count": len(physical),
            "retained_physical_patch_sha256": streaming.digest_json(physical),
            "safe_filter": (
                "Every logical extension is tested against exact zero-slack "
                "cycle support before its connectivity future is interned."
            ),
        }
        if not physical:
            stage["target_survives"] = False
            stage["exclusion_stage"] = "no_physical_supported_corner"

    terminal_identity_certificate = None
    if depth == TERMINAL_DEPTH:
        output_states = sorted(
            {tuple(row["outgoing"]) for row in relation}
        )
        output_set = set(output_states)
        endpoint_rows = [
            [row["incoming"], row["outgoing"], int(row["cost"])]
            for row in relation
        ]
        compatible = [
            row
            for row in endpoint_rows
            if tuple(row[0]) in output_set
        ]
        terminal_identity_certificate = {
            "output_state_count": len(output_states),
            "output_states": [list(state) for state in output_states],
            "endpoint_minimum_count": len(endpoint_rows),
            "endpoint_minima": endpoint_rows,
            "endpoint_minima_sha256": streaming.digest_json(endpoint_rows),
            "zero_length_compatible_mapping_count": len(compatible),
            "zero_length_compatible_mappings": compatible,
            "proof": (
                "A zero-length path has charge zero and exists exactly when "
                "the preceding output state equals the next corner's incoming "
                "state. No compatible mapping means the terminal directed "
                "side transfer has no arc, hence no four-cycle."
            ),
        }

    return {
        "schema": f"n22-population252-depth{depth}-zero-slack-support-v1",
        "scope": {
            "n": N,
            "target_population": TARGET_POPULATION,
            "target_wastage": TARGET_WASTAGE,
            "depth": depth,
            "straight_side_length": N - 2 * depth,
            "terminal_depth": TERMINAL_DEPTH,
            "incoming_global_slack": allowance,
            "whole_board_search": False,
        },
        "source": {
            "path": str(input_path.relative_to(PROJECT)),
            "sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "physical_class_count": len(physical_previous),
        },
        "engine": {
            "base_path": str(BASE_PATH.relative_to(PROJECT)),
            "base_sha256": hashlib.sha256(BASE_PATH.read_bytes()).hexdigest(),
        },
        "analysis_selection": {
            "method": analysis_method,
            "dense_matrix_entry_count": dense_entries,
            "dense_entry_limit": DENSE_ENTRY_LIMIT,
            "sparse_fallback_is_exact": True,
        },
        "edge_lift": edge_lift,
        "minimum_relation_count": len(relation),
        "minimum_relation_sha256": streaming.digest_json(relation),
        "pass1_endpoint_stream": pass1,
        "stage": stage,
        "pass2_physical_stream": pass2,
        "retained_physical_classes": physical,
        **(
            {"terminal_identity_certificate": terminal_identity_certificate}
            if depth == TERMINAL_DEPTH
            else {}
        ),
        "conclusion": {
            "minimum": stage.get("minimum"),
            "global_slack": stage.get("global_slack"),
            "target_survives": stage["target_survives"],
            "retained_physical_class_count": len(physical),
            "population252_decided": not stage["target_survives"],
            "decision_if_empty": "C(22)<=251",
            "terminal_depth_reached": depth == TERMINAL_DEPTH,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth", type=int, required=True)
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    output = certificate_path(arguments.depth)
    record = build(arguments.depth)
    rendered = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    if arguments.verify:
        if json.loads(output.read_text(encoding="utf-8")) != json.loads(rendered):
            raise SystemExit(f"stored depth-{arguments.depth} support differs")
        print(f"VERIFIED {digest}")
        return
    output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output.relative_to(PROJECT)),
                "sha256": digest,
                "depth": arguments.depth,
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
                "target_survives": record["conclusion"]["target_survives"],
                "terminal_depth_reached": record["conclusion"][
                    "terminal_depth_reached"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
