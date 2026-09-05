#!/usr/bin/env python3
"""Independent small-width audit for blockfree_row_dp_certified.cpp.

This deliberately uses exhaustive successor-row enumeration rather than the
column-pruned DFS used by the production C++ implementation.  It validates
(1) the DFS successor generator against exhaustive enumeration for all row
pairs through a chosen width and (2) the row-DP recurrence and terminal dead
rows for small n.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def popcount(x: int) -> int:
    return x.bit_count()


def cell_stable(n: int, a: int, b: int, c: int, j: int) -> bool:
    lo, hi = max(0, j - 1), min(n - 1, j + 1)
    window = ((1 << (hi - lo + 1)) - 1) << lo
    count = popcount(a & window) + popcount(c & window)
    if j > 0:
        count += (b >> (j - 1)) & 1
    if j + 1 < n:
        count += (b >> (j + 1)) & 1
    alive = (b >> j) & 1
    return count in (2, 3) if alive else count != 3


def valid_triple(n: int, a: int, b: int, c: int) -> bool:
    if (a & 1) and (b & 1) and (c & 1):
        return False
    right = 1 << (n - 1)
    if (a & right) and (b & right) and (c & right):
        return False
    if (b & (b >> 1)) & (c & (c >> 1)):
        return False
    return all(cell_stable(n, a, b, c, j) for j in range(n))


def dfs_successors(n: int, a: int, b: int) -> list[int]:
    out: list[int] = []
    stack: list[tuple[int, int]] = [(0, 0)]
    while stack:
        j, partial = stack.pop()
        if j == n:
            if not cell_stable(n, a, b, partial, n - 1):
                continue
            right = 1 << (n - 1)
            if (a & right) and (b & right) and (partial & right):
                continue
            out.append(partial)
            continue
        for value in (1, 0):
            c = partial | (value << j)
            if j == 0 and value and (a & 1) and (b & 1):
                continue
            if j >= 1:
                if value and ((c >> (j - 1)) & 1) and ((b >> (j - 1)) & 3) == 3:
                    continue
                if not cell_stable(n, a, b, c, j - 1):
                    continue
            stack.append((j + 1, c))
    return out


def exhaustive_successors(n: int, a: int, b: int) -> list[int]:
    return [c for c in range(1 << n) if valid_triple(n, a, b, c)]


def audit_generator(max_width: int) -> dict:
    checks = 0
    emitted = 0
    start = time.perf_counter()
    for n in range(1, max_width + 1):
        for a in range(1 << n):
            for b in range(1 << n):
                got = dfs_successors(n, a, b)
                expected = exhaustive_successors(n, a, b)
                if sorted(got) != expected:
                    raise AssertionError(
                        f"successor mismatch n={n} a={a} b={b}: {got} != {expected}"
                    )
                checks += 1
                emitted += len(got)
    return {
        "max_width": max_width,
        "row_pairs_checked": checks,
        "successors_checked": emitted,
        "seconds": time.perf_counter() - start,
    }


def solve_exhaustive_row_dp(n: int) -> dict:
    mask = (1 << n) - 1
    current: dict[tuple[int, int], int] = {(0, 0): 0}
    layers: list[dict] = []
    transitions = 0
    start = time.perf_counter()
    for row in range(n):
        nxt: dict[tuple[int, int], int] = {}
        for (a, b), value in current.items():
            for c in exhaustive_successors(n, a, b):
                transitions += 1
                key = (b, c)
                candidate = value + popcount(c)
                if candidate > nxt.get(key, -10**9):
                    nxt[key] = candidate
        current = nxt
        layers.append(
            {
                "index": row + 1,
                "states": len(current),
                "maximum": max(current.values(), default=-1),
                "transitions_cumulative": transitions,
            }
        )

    bottom: dict[tuple[int, int], int] = {}
    for (a, b), value in current.items():
        if valid_triple(n, a, b, 0):
            transitions += 1
            key = (b, 0)
            if value > bottom.get(key, -10**9):
                bottom[key] = value
    answer = max(
        (value for (a, b), value in bottom.items() if valid_triple(n, a, b, 0)),
        default=-1,
    )
    return {
        "n": n,
        "optimum": answer,
        "transitions_examined": transitions,
        "layers": layers,
        "bottom_1_states": len(bottom),
        "seconds": time.perf_counter() - start,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator-max-width", type=int, default=7)
    parser.add_argument("--dp-max-n", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = {
        "schema": "independent-python-blockfree-audit-v1",
        "generator_audit": audit_generator(args.generator_max_width),
        "row_dp_results": [solve_exhaustive_row_dp(n) for n in range(1, args.dp_max_n + 1)],
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.output:
        args.output.write_text(text)


if __name__ == "__main__":
    main()
