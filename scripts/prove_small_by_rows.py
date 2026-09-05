#!/usr/bin/env python3
"""Prove C(5)=11 or C(8)=32 by complete block-free threshold enumeration."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"src"))
from csl_verify import verify_grid as verify_second
from verifiers.life import verify_grid


def check_candidates(record):
    n, target = record["n"], record["threshold"]
    rows = record["row_masks"]
    if len(rows) != record["board_count"] or len({tuple(r) for r in rows}) != len(rows):
        raise AssertionError("candidate list count or uniqueness mismatch")
    hist = Counter()
    for masks in rows:
        if len(masks) != n or any(type(r) is not int or not 0 <= r < 1 << n for r in masks):
            raise AssertionError("invalid row masks")
        grid = [[(r >> c) & 1 for c in range(n)] for r in masks]
        first, second = verify_grid(grid), verify_second(grid)
        if not (first.stable and second.stable and first.population >= target and
                first.population == second.population and first.live_2x2_blocks == 0):
            raise AssertionError("invalid enumerated candidate")
        if first.components != second.components:
            raise AssertionError("component verifiers disagree")
        hist[first.components] += 1
    return dict(sorted(hist.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("n",type=int,choices=(5,8))
    parser.add_argument("--verify",action="store_true")
    args = parser.parse_args()
    n = args.n
    upper = {5:11,8:32}[n]
    build = ROOT/"build"
    build.mkdir(exist_ok=True)
    binary = build/f"enumerate_threshold_n{n}"
    subprocess.run(["c++","-O3","-std=c++20",str(ROOT/"scripts/rows/enumerate_threshold.cpp"),"-o",str(binary)],check=True)
    output = build/f"n{n:02d}_threshold.json"
    started = time.monotonic()
    subprocess.run([str(binary),str(n),str(upper+1),str(output)],check=True)
    enumeration_seconds = time.monotonic()-started
    record = json.loads(output.read_text())
    histogram = check_candidates(record)
    if record["blockfree_optimum"] != upper+1 or histogram.get(1,0):
        raise AssertionError("the proposed upper bound was not established")
    witness = json.loads((ROOT/f"constructions/n{n:02d}.json").read_text())["grid"]
    if not verify_grid(witness,claimed_cells=upper).valid or not verify_second(witness).valid:
        raise AssertionError("matching lower witness failed")
    report = {"accepted":True,"conclusion":f"C({n})={upper}","enumeration":record,
              "component_histogram":histogram,"enumeration_seconds":enumeration_seconds,
              "source_sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                               ("scripts/rows/blockfree_row_dp.cpp","scripts/rows/enumerate_threshold.cpp",
                                "scripts/prove_small_by_rows.py","verifiers/life.py","src/csl_verify.py")}}
    rendered = json.dumps(report,sort_keys=True,separators=(",",":"))+"\n"
    (build/f"n{n:02d}_row_proof.json").write_text(rendered)
    if args.verify:
        expected = json.loads((ROOT/f"certificates/rows/n{n:02d}.json").read_text())
        normalize = lambda r: {k:v for k,v in r.items() if k != "enumeration_seconds"}
        if normalize(json.loads(rendered)) != normalize(expected):
            raise AssertionError("enumeration differs from saved certificate")
    print(json.dumps({k:v for k,v in report.items() if k != "enumeration"},indent=2))


if __name__ == "__main__":
    main()
