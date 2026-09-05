#!/usr/bin/env python3
"""Fast semantic checks for the retained non-SAT structural certificates."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VERIFIERS = ROOT / "verifiers"
BOUNDARY = HERE / "boundary"
for directory in (VERIFIERS, BOUNDARY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from life import verify_file  # noqa: E402
from upper_bounds import (  # noqa: E402
    ORDINARY_MAXIMUM,
    all_residue_connected_upper,
)


def load(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def digest(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def compact_fixed_size_checks() -> dict[str, bool]:
    values = {8: 32, 9: 43, 10: 53, 11: 63}
    checks: dict[str, bool] = {}
    for n in values:
        witness = verify_file(ROOT / f"constructions/n{n:02d}.json")
        checks[f"n{n}_witness"] = (
            witness.valid and witness.population == values[n]
        )
    checks["n9_unrestricted_bound"] = ORDINARY_MAXIMUM[9] == 43
    for n in (10,11):
        record = load(f"certificates/rows/n{n:02d}.json")
        checks[f"n{n}_blockfree_upper"] = record["n"] == n and record["optimum"] == values[n]
        checks[f"n{n}_row_source"] = record["source_sha256"] == digest("scripts/rows/blockfree_row_dp.cpp")
    record = load("certificates/rows/n08.json")
    checks["n8_row_enumeration_record"] = (record["accepted"] and record["enumeration"]["n"] == 8
        and record["enumeration"]["threshold"] == record["enumeration"]["blockfree_optimum"] == 33
        and record["enumeration"]["board_count"] == 24 and record["component_histogram"] == {"2":8,"3":16})
    checks["n8_row_sources"] = all(digest(p) == h for p,h in record["source_sha256"].items())
    return checks


def upper_certificate_checks() -> dict[str, bool]:
    edge3 = load("certificates/upper_bounds/depth3_edge_certificate.json")
    ring3 = load("certificates/upper_bounds/depth3_ring_certificate.json")
    census4 = load("certificates/upper_bounds/depth4_boundary_census.json")
    ring4 = load("certificates/upper_bounds/depth4_ring_certificate.json")
    census5 = load("certificates/upper_bounds/depth5_boundary_census.json")
    ring5 = load("certificates/upper_bounds/depth5_ring_certificate.json")
    ring6 = load(
        "certificates/upper_bounds/corrected_depth6_ring_certificate.json"
    )
    ledger = load("data/bounds.json")
    checks = {
        "depth3_edge_nodes_214": (
            edge3["blockfree_width3_graph"]["node_count"] == 214
        ),
        "depth3_edge_arcs_771": (
            edge3["blockfree_width3_graph"]["edge_count"] == 771
        ),
        "depth3_edge_cycle_mean_3_over_8": (
            edge3["blockfree_width3_graph"]["target_cycle_mean"] == "3/8"
        ),
        "depth3_free_path_period_eight": (
            edge3["finite_free_segment"]["proved_recurrence"]
            == "f(L+8)=f(L)+3 for every L>=4"
        ),
        "depth3_ring_is_rigorous": (
            ring3["status"] == "rigorous boundary relaxation"
            and ring3["eventual_ring_recurrence"]["first_n"] == 26
        ),
        "depth4_census_dimensions": (
            census4["charged_depth"] == 4 and census4["halo_depth"] == 5
        ),
        "depth4_language_counts": (
            ring4["language"]["corner_output_state_count"] == 711
            and ring4["language"]["corner_transition_count"] == 9957
            and ring4["language"]["edge_state_count"] == 809
            and ring4["language"]["edge_transition_count"] == 3685
        ),
        "depth4_matrix_recurrence": (
            ring4["all_n_upper_formula"]["certified_for_every_n_at_least_14"]
            and ring4["restricted_edge_matrix_period"]["period"] == 8
            and ring4["restricted_edge_matrix_period"]["weight_increment"]
            == 3
        ),
        "depth5_census_dimensions": (
            census5["charged_depth"] == 5 and census5["halo_depth"] == 6
        ),
        "depth5_language_counts": (
            ring5["edge_state_count"] == 3051
            and ring5["edge_transition_count"] == 17649
            and ring5["corner_output_state_count"] == 2706
            and ring5["corner_transition_count"] == 179476
        ),
        "depth5_residue_five_theorem": bool(
            ring5["all_n_consequences"]["residue_5"]["certified"]
        ),
        "corrected_depth6_is_certified": (
            ring6["all_n_upper"]["certified"]
            and ring6["all_n_upper"][
                "all_finite_bases_exclude_equality_lifts"
            ]
        ),
        "corrected_depth6_finite_bases": (
            ring6["all_n_upper"]["finite_bases"] == [16, 24, 32, 40]
        ),
        "corrected_depth6_language_counts": (
            ring6["language"]["depth5_equality_corner_mapping_count"] == 23
            and ring6["language"]["depth6_corner_output_state_count"] == 266
            and ring6["language"]["depth6_edge_state_count"] == 10996
            and ring6["language"]["depth6_edge_transition_count"] == 55422
        ),
    }

    formula_dominates_ledger = True
    equality_outside_later_closures = True
    for row in ledger["bounds"]:
        n = int(row["n"])
        if n < 14:
            continue
        upper = min(
            ORDINARY_MAXIMUM.get(n, 10**18),
            all_residue_connected_upper(n),
        )
        formula_dominates_ledger &= row["upper_bound"] <= upper
        if n not in {14, 17, 18, 19, 22}:
            equality_outside_later_closures &= row["upper_bound"] == upper
    checks["all_bounds_through_50_respect_theorem_intersection"] = (
        formula_dominates_ledger
    )
    checks["theorem_intersection_is_used_except_later_closures"] = (
        equality_outside_later_closures
    )
    return checks


def exact_closure_checks() -> dict[str, bool]:
    n14 = load(
        "certificates/exact_closures/n14/all_low_slack_belt_census.json"
    )
    n17a = load("certificates/exact_closures/n17/depth5_probe.json")
    n17b = load(
        "certificates/exact_closures/n17/depth5_equality_orbits.json"
    )
    n17c = load(
        "certificates/exact_closures/n17/depth6_equality_lift.json"
    )
    n18 = load(
        "certificates/exact_closures/n18/"
        "population171_exclusion_certificate.json"
    )
    checks = {
        "n14_complete_belt_enumeration": (
            n14["n"] == 14
            and n14["target_population"] == 103
            and n14["abstract_cycles_mod_rotation"] == 2664
            and n14["processed_physical_combinations"] == 261225
            and not n14["census_only"]
            and not n14["stopped_at_limit"]
        ),
        "n14_all_103_completions_disconnected": (
            n14["stable_population_103_completions_examined"] == 224
            and n14["connected_population_103_completions"] == 0
        ),
        "n17_depth5_minimum_38": (
            n17a["n17_consequence"]["minimum_depth5_boundary_wastage"] == 38
        ),
        "n17_equality_language_21_states_50_arcs": (
            n17b["complete_equality_support"]["state_count"] == 21
            and n17b["complete_equality_support"]["arc_count"] == 50
        ),
        "n17_depth6_excludes_target_38": (
            not n17c["depth6"]["anchored_four_cycle_test"][
                "cycle_at_or_below_target_exists"
            ]
            and n17c["depth6"]["anchored_four_cycle_test"][
                "minimum_anchored_four_cycle_cost"
            ]
            == 39
        ),
        "n18_excludes_only_population_171": (
            n18["n"] == 18
            and n18["target_population_excluded"] == 171
            and n18["theorem"] == "C(18)<=170"
            and all(n18["checks"].values())
        ),
    }
    for n, population in {
        14: 102,
        16: 134,
        17: 151,
        18: 170,
    }.items():
        witness = verify_file(ROOT / f"constructions/n{n:02d}.json")
        checks[f"n{n}_retained_witness"] = (
            witness.valid and witness.population == population
        )
    return checks


def build() -> dict[str, Any]:
    groups = {
        "compact_fixed_sizes": compact_fixed_size_checks(),
        "boundary_upper_bounds": upper_certificate_checks(),
        "exact_closures": exact_closure_checks(),
    }
    all_checks = [
        result
        for group in groups.values()
        for result in group.values()
    ]
    return {
        "schema": "structural-certificate-audit-v1",
        "accepted": all(all_checks),
        "qualification": (
            "The compact n=8 through n=11 records preserve solver and "
            "independent-checker provenance but omit the very large proof "
            "traces. Full portable proof replay is retained for n=1 through "
            "n=7. The n=13 and boundary programs are retained as source."
        ),
        "groups": groups,
        "input_sha256": {
            "depth3_edge": digest(
                "certificates/upper_bounds/depth3_edge_certificate.json"
            ),
            "depth4_ring": digest(
                "certificates/upper_bounds/depth4_ring_certificate.json"
            ),
            "depth5_ring": digest(
                "certificates/upper_bounds/depth5_ring_certificate.json"
            ),
            "depth6_ring": digest(
                "certificates/upper_bounds/"
                "corrected_depth6_ring_certificate.json"
            ),
            "n14_census": digest(
                "certificates/exact_closures/n14/"
                "all_low_slack_belt_census.json"
            ),
            "n18_exclusion": digest(
                "certificates/exact_closures/n18/"
                "population171_exclusion_certificate.json"
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "certificates" / "claims" / "structural_audit.json",
    )
    args = parser.parse_args()
    record = build()
    target = args.output
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(record, separators=(",", ":"), sort_keys=True))
    raise SystemExit(0 if record["accepted"] else 1)


if __name__ == "__main__":
    main()
