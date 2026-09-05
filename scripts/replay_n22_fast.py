#!/usr/bin/env python3
"""Replay n=22 depth 8..11 with exact bitset-join cycle acceleration.

The generated mathematical record must equal the saved record in full.
The run report separately identifies the accelerated cycle evaluator and its
source hashes, in addition to the boundary engine's recorded source hashes.
Earlier depths remain inputs: this command alone is not the complete proof.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cycle_join import accelerate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth", type=int, choices=range(8,12), required=True)
    args = parser.parse_args()
    path = ROOT / "src/engines/n22/certify_n22_zero_slack_lift.py"
    spec = importlib.util.spec_from_file_location("fast_n22_driver", path)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    original_load = driver.load_base
    joins = []

    def load_base():
        base = original_load()
        original_streaming = base.load_streaming
        def load_streaming():
            streaming = original_streaming()
            fast = accelerate(streaming.sparse_four_cycle_support)
            def evaluate(sources, transfer, target):
                started = time.monotonic()
                result = fast(sources, transfer, target)
                joins.append({"transfer_arcs":len(transfer), "seconds":time.monotonic()-started,
                              "supported_arcs":len(result[0]["union"]["arc_state_indices"]) if result[0] else 0})
                print("FAST JOIN", json.dumps(joins[-1]), flush=True)
                return result
            streaming.sparse_four_cycle_support = evaluate
            return streaming
        base.load_streaming = load_streaming
        return base
    driver.load_base = load_base
    started = time.monotonic()
    actual = driver.build(args.depth)
    expected_path = driver.certificate_path(args.depth)
    expected = json.loads(expected_path.read_text())
    if actual != expected:
        raise AssertionError("accelerated result differs from retained certificate")
    report = {"depth":args.depth, "accepted":True, "comparison":"complete JSON equality",
              "seconds":time.monotonic()-started, "joins":joins,
              "certificate":str(expected_path.relative_to(ROOT)),
              "certificate_sha256":hashlib.sha256(expected_path.read_bytes()).hexdigest(),
              "runtime_override_sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                                         for p in ("src/cycle_join.py", "scripts/replay_n22_fast.py")}}
    output = ROOT / f"build/fast_n22_depth{args.depth}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
