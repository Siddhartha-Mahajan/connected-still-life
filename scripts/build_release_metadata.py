#!/usr/bin/env python3
"""Generate the proof index, results table, one optimal-board plate and manifest."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ledger = json.loads((ROOT/"data/bounds.json").read_text())
    common = [f"certificates/upper_bounds/{name}.json" for name in
              ("depth4_ring_certificate","depth5_ring_certificate","corrected_depth6_ring_certificate")]
    exact = []
    for row in ledger["bounds"]:
        if not row["exact"]: continue
        n = row["n"]
        if n == 1:
            method,files = "The only nonempty one-cell board dies; empty-board convention",["docs/MATHEMATICS.md"]
        elif n in (2,3,4,6,7,9,12,15,20,23,31,39):
            method,files = "Matches the unrestricted maximum of Chu and Stuckey (2012), Table 7",["docs/REFERENCES.md","scripts/boundary/upper_bounds.py"]
        elif n in (5,8):
            method = "Complete block-free row enumeration: all boards above the connected witness are disconnected"
            files = [f"certificates/rows/n{n:02d}.json","scripts/prove_small_by_rows.py","scripts/rows/enumerate_threshold.cpp","scripts/rows/blockfree_row_dp.cpp"]
        elif n in (10,11,13):
            method = "Block-free row-DP maximum matches a connected witness"
            files = [f"certificates/rows/n{n:02d}.json","scripts/rows/blockfree_row_dp.cpp","scripts/rows/run_row_dp.py"]
        elif n in (14,17,18,19,22):
            method = "Complete finite boundary exclusion, intersected with the general upper bound"
            files = [str(p.relative_to(ROOT)) for p in sorted((ROOT/f"certificates/exact_closures/n{n}").glob("*.json"))]+common
        else:
            method,files = "Matches the proved connected residue-eight upper bound",common.copy()
        if row["witness"]: files.insert(0,row["witness"])
        exact.append({"n":n,"value":row["lower_bound"],"upper_bound_method":method,"evidence_files":files})
    (ROOT/"data/proof_index.json").write_text(json.dumps({"exact_values":exact},sort_keys=True,separators=(",",":"))+"\n")
    lines = ["# Values and bounds", "", "A board proves the lower bound; the [proof index](../data/proof_index.json) identifies upper evidence for every exact value.","",
             "| n | Lower | Upper | Gap | Status | Board |","|---:|---:|---:|---:|:---|:---|"]
    for r in ledger["bounds"]:
        link = f"[JSON](../{r['witness']})" if r["witness"] else "empty convention"
        lines.append(f"| {r['n']} | {r['lower_bound']} | {r['upper_bound']} | {r['gap']} | {'exact' if r['exact'] else 'open'} | {link} |")
    (ROOT/"docs/RESULTS.md").write_text("\n".join(lines)+"\n")
    plate = ['<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1600" viewBox="0 0 1600 1740">',
             '<title>Maximum connected still lifes: proven optima for n=1 through 25</title>',
             '<desc>Twenty-five panels. Black squares are live; the gray ring is the dead exterior. Panel 1 is the empty-board convention. All other boards are stable and connected.</desc>',
             '<rect width="1600" height="1740" fill="#fafaf8"/>',
             '<g font-family="sans-serif" fill="#152b35"><text x="40" y="46" font-size="30">Maximum connected still lifes</text>',
             '<text x="40" y="76" font-size="18">Proven optima for n = 1–25 · black = live · gray ring = dead exterior</text></g>']
    for n in range(1,26):
        x = 25+315*((n-1)%5); y = 105+323*((n-1)//5)
        value = ledger["exact_prefix"][n-1]
        plate += [f'<g transform="translate({x},{y})"><rect width="290" height="305" rx="8" fill="white" stroke="#d5dcdf"/>',
                  f'<text x="14" y="28" font-family="sans-serif" font-size="20" fill="#152b35">n = {n} · C(n) = {value}</text>']
        scale = 245/(n+2)
        plate += [f'<g transform="translate(22,45) scale({scale:.8f})" shape-rendering="crispEdges">',
                  f'<rect width="{n+2}" height="{n+2}" fill="#e1e7e9"/><rect x="1" y="1" width="{n}" height="{n}" fill="white"/>']
        if n > 1:
            grid = json.loads((ROOT/f"constructions/n{n:02d}.json").read_text())["grid"]
            path = " ".join(f"M{c+1},{r+1}h1v1h-1z" for r in range(n) for c in range(n) if grid[r][c])
            plate.append(f'<path d="{path}" fill="#152b35"/>')
        plate.append('</g>')
        if n == 1: plate.append('<text x="45" y="184" font-family="sans-serif" font-size="15" fill="#52636b">empty convention</text>')
        plate.append('</g>')
    plate.append('</svg>')
    (ROOT/"docs/optima_1_25.svg").write_text("\n".join(plate)+"\n")
    manifest=[]
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or p.name in {"MANIFEST.sha256",".DS_Store"}: continue
        rel = p.relative_to(ROOT)
        if any(x in {"build",".git",".venv","__pycache__",".pytest_cache"} for x in rel.parts) or p.suffix == ".pyc": continue
        manifest.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}")
    (ROOT/"MANIFEST.sha256").write_text("\n".join(manifest)+"\n")
    print(f"{len(exact)} exact values; 25-panel plate; {len(manifest)} files")


if __name__ == "__main__": main()
