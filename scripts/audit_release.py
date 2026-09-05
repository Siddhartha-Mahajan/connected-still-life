#!/usr/bin/env python3
"""Audit the current release. Never interpret record checks as a deep replay."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "verifiers"), str(ROOT / "src"), str(ROOT / "scripts/boundary")]
from life import verify_file
from csl_verify import verify_grid
from upper_bounds import ORDINARY_MAXIMUM, all_residue_connected_upper


def load(path):
    return json.loads((ROOT / path).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def n22_check():
    folder = "certificates/exact_closures/n22"
    records = []
    for depth in range(5, 12):
        suffix = "_zero_slack" if depth >= 8 else ""
        relative = f"{folder}/n22_population252_depth{depth}{suffix}_support.json"
        record = load(relative)
        scope = record["scope"]
        require((scope["n"], scope["target_population"], scope["target_wastage"]) == (22, 252, 48), "n22 scope")
        require(scope["depth"] == depth and scope["straight_side_length"] == 22 - 2 * depth, "n22 depth")
        if depth > 5:
            source = record["source"]
            require(digest(ROOT / source["path"]) == source["sha256"], "n22 preceding certificate hash")
        engine = record["engine"]
        for key, hash_key in (("path", "sha256"), ("base_path", "base_sha256"), ("base_wrapper_path", "base_wrapper_sha256")):
            if key in engine:
                require(digest(ROOT / engine[key]) == engine[hash_key], "n22 source implementation hash")
        records.append(record)
    terminal = records[-1]
    relation = terminal["terminal_identity_certificate"]["endpoint_minima"]
    ins = {tuple(row[0]) for row in relation}
    outs = {tuple(row[1]) for row in relation}
    require(len(relation) == 2592 and len(ins) == len(outs) == 180, "n22 terminal dimensions")
    require(not ins.intersection(outs), "n22 terminal state sets must be disjoint")
    require(terminal["conclusion"]["population252_decided"] and not terminal["conclusion"]["target_survives"], "n22 terminal exclusion")
    return {"checked": "certificate chain hashes and independently recomputed terminal state intersection",
            "depths": list(range(5,12)), "terminal_mappings": len(relation),
            "terminal_intersection": 0, "full_enumeration_replayed": False}


def compact_audit():
    for path in (ROOT/"certificates").rglob("*.json"):
        record = json.loads(path.read_text())
        key = "record_sha256_excluding_this_field"
        if key in record:
            stored = record[key]
            record[key] = None
            observed = hashlib.sha256(json.dumps(record,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            require(observed == stored, f"internal certificate digest: {path.relative_to(ROOT)}")
        for name, stored in record.get("file_sha256",{}).items():
            require((ROOT/name).is_file() and digest(ROOT/name) == stored, f"certificate dependency: {name}")
    ledger = load("data/bounds.json")
    rows = ledger["bounds"]
    require([r["n"] for r in rows] == list(range(1,51)), "ledger coverage")
    checked = []
    for row in rows:
        n, lower, upper = row["n"], row["lower_bound"], row["upper_bound"]
        require(lower <= upper and row["gap"] == upper-lower and row["exact"] == (lower==upper), f"ledger n={n}")
        if n == 1:
            require(lower == upper == 0 and row["witness"] is None, "empty-box convention")
        else:
            path = ROOT / row["witness"]
            payload = json.loads(path.read_text())
            a = verify_file(path)
            b = verify_grid(payload["grid"], claimed_cells=lower)
            require(a.valid and b.valid and a.n == b.n == n and a.population == b.population == lower, f"witness n={n}")
            checked.append({"n": n, "population": lower, "sha256": digest(path), "two_verifiers_accept": True})
        if n >= 14:
            expected = min(ORDINARY_MAXIMUM[n], all_residue_connected_upper(n))
            expected = min(expected, {14:102,17:151,18:170,19:188,22:251}.get(n,expected))
            require(upper == expected, f"upper arithmetic n={n}")
    exact = [r["n"] for r in rows if r["exact"]]
    require(exact == ledger["known_exact_indices"] == list(range(1,26))+[31,32,33,39], "exact indices")
    prefix = [r["lower_bound"] for r in rows[:25]]
    require(prefix == ledger["exact_prefix"] and ledger["exact_prefix_end"] == 25, "exact prefix")
    bfile = [list(map(int,line.split())) for line in (ROOT / "data/exact_prefix.txt").read_text().splitlines()]
    require(bfile == [[i+1,v] for i,v in enumerate(prefix)], "b-file")
    structural = module("scripts/audit_structural_certificates.py", "release_structural").build()
    require(structural["accepted"], f"structural certificate checks: {structural['groups']}")
    row13 = load("certificates/rows/n13.json")
    require(row13["n"] == 13 and row13["optimum"] == 88 and row13["transitions_examined"] == 3926925326, "n13 row computation")
    require(row13["source_sha256"] == digest(ROOT/"scripts/rows/blockfree_row_dp.cpp"), "n13 row source")
    n17 = module("scripts/closures/n17/verify_n17_closure.py", "release_n17").build()
    n18 = module("scripts/closures/n18/build_171_exclusion_certificate.py", "release_n18").build()
    require(n18 == load("certificates/exact_closures/n18/population171_exclusion_certificate.json"), "n18 assembled certificate")
    n19 = load("certificates/exact_closures/n19/population189_exclusion.json")
    require(n19["conclusion"]["connected_upper_bound"] == 188 and n19["conclusion"]["population_189_excluded"], "n19 conclusion")
    require([s["depth"] for s in n19["stages"]] == [5,6,7,8,9], "n19 stages")
    require([s.get("minimum") for s in n19["stages"]] == [40,42,42,42,None], "n19 minima")
    terminal = n19["stages"][-1]
    require(not terminal["target_survives"] and not terminal["minimum_test"]["finite_anchor_return_exists"], "n19 terminal exclusion")
    row_checker = module("scripts/prove_small_by_rows.py", "release_row_candidates")
    for n,hist,maximum in ((5,{2:16},12),(8,{2:8,3:16},33)):
        record = load(f"certificates/rows/n{n:02d}.json")
        require(record["enumeration"]["n"] == n and record["enumeration"]["threshold"] == maximum == record["enumeration"]["blockfree_optimum"], "row enumeration scope")
        require(row_checker.check_candidates(record["enumeration"]) == hist, "all threshold boards disconnected, both verifiers")
        require(all(digest(ROOT/p) == h for p,h in record["source_sha256"].items()), "row enumerator source")
    brick = load("certificates/claims/brick8_certificate.json")
    require(brick["accepted"] and brick["covers_every_n_at_least"] == 10 and set(brick["residues"]) == set(map(str,range(8))), "brick family scope")
    require(all(all(r["checks"].values()) for r in brick["residues"].values()), "brick finite proof obligations")
    proof_index = load("data/proof_index.json")
    require([r["n"] for r in proof_index["exact_values"]] == exact, "proof index coverage")
    for row in proof_index["exact_values"]:
        require(row["value"] == rows[row["n"]-1]["lower_bound"], "proof index value")
        for path in row["evidence_files"]:
            require((ROOT/path).is_file(), f"missing evidence {path}")
    return {"accepted": True, "scope": "current witnesses, bounds arithmetic, retained certificate consistency, n22 terminal relation",
            "does_not_replay_all_exhaustive_searches": True, "witnesses": checked,
            "exact_indices": exact, "prefix_end": 25,
            "structural": structural, "n13": row13, "n17": n17,
            "n18_certificate_reassembled": True, "n19_record_checked": True, "n22": n22_check()}


def manifest_check():
    path = ROOT / "MANIFEST.sha256"
    require(path.is_file(), "missing manifest; run scripts/build_release_metadata.py")
    count = 0
    for line in path.read_text().splitlines():
        sha, relative = line.split(None, 1)
        file = ROOT / relative.lstrip(" *")
        require(file.is_relative_to(ROOT) and file.is_file() and digest(file) == sha, f"manifest: {relative}")
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-small", action="store_true", help="also regenerate the complete n=5,8,10,11 row proofs")
    parser.add_argument("--output", type=Path, default=ROOT/"build/audit.json")
    args = parser.parse_args()
    report = compact_audit()
    report["manifest_files_checked"] = manifest_check()
    if args.replay_small:
        for n in (5,8):
            subprocess.run([sys.executable,"-B",str(ROOT/"scripts/prove_small_by_rows.py"),str(n),"--verify"],cwd=ROOT,check=True)
        for n in (10,11):
            subprocess.run([sys.executable,"-B",str(ROOT/"scripts/rows/run_row_dp.py"),"--n",str(n)],cwd=ROOT,check=True)
        report["small_row_proofs_replayed"] = [5,8,10,11]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"accepted": True, "witnesses": len(report["witnesses"]), "exact_values": len(report["exact_indices"]),
                      "prefix_end":25, "manifest_files":report["manifest_files_checked"], "small_proofs_replayed":args.replay_small}))


if __name__ == "__main__":
    main()
