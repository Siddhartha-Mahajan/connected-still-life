#!/usr/bin/env python3
"""Certify complete depth-five physical support for n=22, population 252."""

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
    / "certify_n32_depth5_support.py"
)
OUTPUT = PROJECT / "certificates" / "exact_closures" / "n22" / "n22_population252_depth5_support.json"
N = 22
TARGET_POPULATION = 252
TARGET_WASTAGE = 48
TERMINAL_DEPTH = 11


def load_base() -> Any:
    specification = importlib.util.spec_from_file_location(
        "n22_module_depth5_base", BASE_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load validated depth-five engine")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    module.N = N
    module.TARGET_POPULATION = TARGET_POPULATION
    module.TARGET_WASTAGE = TARGET_WASTAGE
    module.TERMINAL_DEPTH = TERMINAL_DEPTH
    return module


def build() -> dict[str, Any]:
    base = load_base()
    record = base.build()
    record["schema"] = "n22-population252-depth5-physical-support-v1"
    record["scope"].update(
        {
            "n": N,
            "target_population": TARGET_POPULATION,
            "target_wastage": TARGET_WASTAGE,
            "straight_side_length": N - 10,
        }
    )
    record["theorem"] = {
        "mandatory_anchor_threshold": TARGET_WASTAGE // 4,
        "support_completeness": (
            "Every directed four-cycle of total charge at most 48 has an "
            "arc of charge at most 12. Every such anchor and every exact "
            "three-arc return is included by min-plus support."
        ),
        "physical_completeness": (
            "All physical depth-five corners are enumerated. A corner is "
            "retained exactly when its excess over a supported side minimum "
            "fits the target slack, then quotiented only by its exact "
            "exposed-frontier connectivity future."
        ),
    }
    record["engine"]["base_wrapper_path"] = str(BASE_PATH.relative_to(PROJECT))
    record["engine"]["base_wrapper_sha256"] = hashlib.sha256(
        BASE_PATH.read_bytes()
    ).hexdigest()
    conclusion = record["conclusion"]
    conclusion.pop("population528_decided", None)
    conclusion["population252_decided"] = not record["stage"][
        "target_survives"
    ]
    conclusion["decision_if_empty"] = "C(22)<=251"
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    record = build()
    rendered = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    if arguments.verify:
        if json.loads(OUTPUT.read_text(encoding="utf-8")) != json.loads(rendered):
            raise SystemExit("stored n=22 depth-five support differs")
        print(f"VERIFIED {digest}")
        return
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(PROJECT)),
                "sha256": digest,
                "minimum": record["conclusion"]["minimum"],
                "global_slack": record["conclusion"]["global_slack"],
                "support_state_count": record["stage"].get(
                    "support_union", {}
                ).get("state_count"),
                "support_arc_count": record["stage"].get(
                    "support_union", {}
                ).get("arc_count"),
                "retained_physical_class_count": record["conclusion"][
                    "retained_physical_class_count"
                ],
                "target_survives": record["stage"]["target_survives"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
