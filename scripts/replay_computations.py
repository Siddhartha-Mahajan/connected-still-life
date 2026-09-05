#!/usr/bin/env python3
"""Run explicit, potentially expensive certificate regeneration groups."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def jobs(group, start_depth=5):
    b = "scripts/boundary/"
    c = "scripts/closures/"
    if group == "n22-fast":
        return [job if depth < 8 else ["scripts/replay_n22_fast.py","--depth",str(depth)]
                for depth,job in zip(range(start_depth,12),jobs("n22",start_depth))]
    if group == "n22":
        p = "src/engines/n22/"
        return [[p+f"certify_n22_depth{d}_support.py", "--verify"] if d < 8 else
                [p+"certify_n22_zero_slack_lift.py", "--depth", str(d), "--verify"] for d in range(start_depth,12)]
    if group == "n19":
        return [[c+"n19/certify_n19_upper.py", "--verify"]]
    if group == "n18":
        return [[c+"n18/"+s+".py", "--verify"] for s in
                ("probe_depth5", "enumerate_depth5_equality_orbits", "lift_equality_to_depth6",
                 "enumerate_depth6_equality_orbits", "lift_depth6_to_depth7", "build_171_exclusion_certificate")]
    if group == "n17":
        return [[c+"n17/"+s+".py", "--verify"] for s in
                ("probe_depth5", "enumerate_equality_orbits", "certify_depth6_equality_lift")]
    if group == "boundary":
        prefix = [[b+s+".py", "--verify"] for s in
                ("certify_depth3_edge", "certify_depth3_ring", "depth4_boundary_census",
                 "certify_depth4_ring", "depth5_boundary_census", "certify_depth5_ring",
                 "depth6_zero_lift_census")]
        for n in (16,24,32,40):
            orbit = f"certificates/upper_bounds/residue0_equality_orbits_n{n}.json"
            decomposition = f"certificates/upper_bounds/residue0_arc_decomposition_n{n}.json"
            prefix += [[b+"enumerate_residue0_equality_orbits.py", "--n", str(n), "--output", orbit, "--verify"],
                       [b+"decompose_residue0_equality_arcs.py", "--n", str(n), "--orbit", orbit,
                        "--output", decomposition, "--verify"]]
        return prefix + [[b+s+".py", "--verify"] for s in
                         ("build_corrected_depth6_lifts", "certify_corrected_depth6_ring")]
    if group == "n14":
        return [[c+"n14/enumerate_all_low_slack_belts.py", "--output", str(ROOT/"build/n14_census.json"),
                 "--witness", str(ROOT/"build/n14_candidate.json")],
                [c+"n14/verify_n14_closure.py", "--census", str(ROOT/"build/n14_census.json"),
                 "--output", str(ROOT/"build/n14_closure.json")]]
    if group == "n13":
        return [["scripts/rows/run_row_dp.py", "--full-n13"]]
    if group == "families":
        return [["scripts/certify_brick_family.py"]]+[["scripts/construction_families.py", family, "--certify-through", "80", "--output", str(ROOT/f"build/{family}.json")]
                for family in ("pond","brick8")] + [["scripts/period54_family.py", "--certify", "--regression-through", "8", "--output", str(ROOT/"build/period54.json")]]
    raise ValueError(group)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=("boundary","n13","n14","n17","n18","n19","n22","n22-fast","families"))
    parser.add_argument("--start-depth", type=int, choices=range(5,12), default=5,
                        help="n22 only: resume at this depth; earlier certificates remain trusted inputs")
    parser.add_argument("--timeout", type=float, default=None, help="optional seconds per child process")
    parser.add_argument("--list", action="store_true", help="print commands without executing them")
    args = parser.parse_args()
    if args.list:
        for job in jobs(args.group,args.start_depth):
            print("python -B", " ".join(job))
        return
    require_dir = ROOT/"build/replays"
    require_dir.mkdir(parents=True, exist_ok=True)
    results = []
    report = require_dir/f"{args.group}_from_{args.start_depth}.json"
    for i, job in enumerate(jobs(args.group,args.start_depth)):
        started = time.monotonic()
        command = [sys.executable,"-B",str(ROOT/job[0]),*job[1:]]
        log = require_dir/f"{args.group}_{args.start_depth}_{i:02d}.log"
        print("RUN", " ".join(job), flush=True)
        with log.open("w") as stream:
            try:
                result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=args.timeout)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        results.append({"command":["python","-B",*job], "returncode":code,
                        "seconds":round(time.monotonic()-started,3), "log":str(log.relative_to(ROOT))})
        report.write_text(json.dumps({"group":args.group,"start_depth":args.start_depth,
                          "accepted":all(r["returncode"]==0 for r in results),
                          "complete":len(results)==len(jobs(args.group,args.start_depth)),"jobs":results},indent=2)+"\n")
        print("PASS" if code == 0 else "FAIL", f"{results[-1]['seconds']}s", flush=True)
        if code != 0:
            raise SystemExit(f"See {log}")


if __name__ == "__main__":
    main()
