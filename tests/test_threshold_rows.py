import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from csl_verify import verify_grid

ROOT = Path(__file__).resolve().parents[1]


def test_complete_small_threshold_enumeration(tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++20 compiler required")
    binary = tmp_path/"threshold"
    subprocess.run([compiler,"-O2","-std=c++20",str(ROOT/"scripts/rows/enumerate_threshold.cpp"),"-o",str(binary)],check=True)
    output = tmp_path/"enumeration.json"
    subprocess.run([str(binary),"3","5",str(output)],check=True)
    record = json.loads(output.read_text())
    brute = set()
    for bits in range(1 << 9):
        rows = tuple((bits >> (3*r)) & 7 for r in range(3))
        if any((a & (a >> 1) & b & (b >> 1)) for a,b in zip(rows,rows[1:])):
            continue
        grid = [[(row >> c)&1 for c in range(3)] for row in rows]
        result = verify_grid(grid)
        if result.stable and result.population >= 5:
            brute.add(rows)
    assert set(map(tuple,record["row_masks"])) == brute
    assert record["board_count"] == len(brute)
    assert record["blockfree_optimum"] == max(sum(r.bit_count() for r in rows) for rows in brute)
