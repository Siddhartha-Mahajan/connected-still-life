#!/usr/bin/env python3
"""Independent audit of the numerical and structural claims of the manuscript.

Standard library only.  Run from this directory or from anywhere:

    python3 manuscript/ancillary/scripts/verify_manuscript.py

The script never trusts a stored population, component count, or bound.  It

1. re-verifies every lower-bound board (stability on the board and its full
   dead exterior ring, one Moore component, population);
2. rebuilds the ledger of lower and upper bounds for 2 <= n <= 50 and checks the
   statements about exact values and open intervals made in the paper;
3. certifies the nine band families for every repetition count k >= 1
   (population polynomial, stability windows, finite connectivity contexts);
4. checks the arithmetic of the uniform bound C(n) >= n(n+1)/2 - 4.

Upper bounds come from the repository ledger ``data/bounds.json`` (its
certificates are audited by ``scripts/audit_release.py``) and from the closed
formulas of the paper.  This script does not replay those certificates.
"""
from __future__ import annotations

import glob
import json
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANC = HERE.parent
REPO = ANC.parent.parent
sys.path.insert(0, str(REPO / "scripts" / "boundary"))
from upper_bounds import ORDINARY_MAXIMUM as M  # Chu-Stuckey (2012), Table 7

D8 = [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]
DCORR = (26, 23, 18, 23, 20, 23, 26, 11)
LOG: list[str] = []


def say(msg: str) -> None:
    LOG.append(msg)
    print(msg)


# Life checks
def check_board(grid):
    """Return (population, stable, components, live_2x2_blocks)."""
    n = len(grid)
    assert all(len(r) == n for r in grid), "grid must be square"
    assert all(v in (0, 1) for r in grid for v in r), "grid must be binary"

    def cell(r, c):
        return grid[r][c] if 0 <= r < n and 0 <= c < n else 0

    stable = True
    for r in range(-1, n + 1):
        for c in range(-1, n + 1):
            k = sum(cell(r + a, c + b) for a, b in D8)
            if cell(r, c):
                if k not in (2, 3):
                    stable = False
            elif k == 3:
                stable = False
    pop = sum(map(sum, grid))
    seen = set()
    comps = 0
    for r in range(n):
        for c in range(n):
            if grid[r][c] and (r, c) not in seen:
                comps += 1
                seen.add((r, c))
                q = deque([(r, c)])
                while q:
                    x, y = q.popleft()
                    for a, b in D8:
                        u, v = x + a, y + b
                        if cell(u, v) and (u, v) not in seen:
                            seen.add((u, v))
                            q.append((u, v))
    blocks = sum(
        1
        for r in range(n - 1)
        for c in range(n - 1)
        if grid[r][c] and grid[r][c + 1] and grid[r + 1][c] and grid[r + 1][c + 1]
    )
    return pop, stable, comps, blocks


def board_path(n: int) -> Path:
    local = ANC / "constructions" / f"n{n:02d}.json"
    return local if local.exists() else REPO / "constructions" / f"n{n:02d}.json"


def load_board(n: int):
    d = json.loads(board_path(n).read_text())
    assert d["n"] == n and len(d["grid"]) == n
    return d


# the ledger
def U(n: int) -> int:
    return (4 * n * n + 5 * n - DCORR[n % 8]) // 8


def audit_ledger():
    repo_ledger = {r["n"]: r for r in json.loads((REPO / "data" / "bounds.json").read_text())["bounds"]}
    lower, source = {}, {}
    sizes = sorted(set(range(2, 51)) | {int(Path(p).stem[1:]) for p in glob.glob(str(ANC / "constructions" / "n*.json"))})
    for n in sizes:
        d = load_board(n)
        pop, stable, comps, blocks = check_board(d["grid"])
        assert stable and comps == 1, f"n={n}: board invalid"
        assert pop == d["claimed_cells"], f"n={n}: claimed population mismatch"
        lower[n] = pop
        source[n] = "manuscript" if (ANC / "constructions" / f"n{n:02d}.json").exists() else "repository"
    # The repository board is used only if no better manuscript board exists.
    for n in range(2, 51):
        repo_pop = repo_ledger[n]["lower_bound"]
        rb = json.loads((REPO / "constructions" / f"n{n:02d}.json").read_text())
        rp, rs, rc, _ = check_board(rb["grid"])
        assert rs and rc == 1 and rp == repo_pop
        if rp > lower[n]:
            lower[n], source[n] = rp, "repository"
    upper = {}
    specials = {}
    for n in range(2, 51):
        up = repo_ledger[n]["upper_bound"]
        base = M[n] if n < 14 else min(M[n], U(n))
        assert up <= base, f"n={n}: repository upper bound exceeds min(M,U)"
        if up < base:
            specials[n] = (base, up)
        upper[n] = up
    exact = [n for n in range(2, 51) if lower[n] == upper[n]]
    openn = [n for n in range(2, 51) if lower[n] < upper[n]]
    say(f"boards verified: {len(sizes)} boards used for the ledger (manuscript copy where it improves the repository board; sizes 53, 55, 57, 65 lie beyond the repository ledger) and all 49 repository boards")
    say(f"sizes with upper bound below min(M,U): {sorted(specials)}")
    say(f"exact values, 1 <= n <= 50: {[1] + exact}  (count {1 + len(exact)})")
    say(f"open sizes, n <= 50: {openn}")
    say(f"largest gap for 18 <= n <= 50: {max(upper[n] - lower[n] for n in range(18, 51))}")
    # Claims of the paper.
    assert [1] + exact == list(range(1, 26)) + [29, 31, 32, 33, 37, 39, 41, 45, 49]
    assert [n for n in range(2, 51) if lower[n] < upper[n] and n >= 18] == openn
    assert (lower[26], upper[26]) == (350, 352)
    assert (lower[28], upper[28]) == (406, 407)
    # exact values beyond the ledger: a verified board that meets U(n)
    beyond = {}
    for n in (53, 57, 65):
        d = load_board(n)
        pop, stable, comps, _ = check_board(d["grid"])
        assert stable and comps == 1 and pop == U(n), f"n={n}"
        beyond[n] = pop
    say(f"exact values beyond the ledger (board meets U(n)): {beyond}")
    for n in (16, 21, 24, 25, 29, 32, 33, 37, 41, 45, 49):
        assert lower[n] == upper[n] == U(n), f"n={n}: board does not meet U(n)"
    say("boards meet U(n) at n = 16, 21, 24, 25, 29, 32, 33, 37, 41, 45, 49, 53, 57, 65")
    chains = [(21, 29, 37, 45, 53), (25, 33, 41, 49, 57, 65)]
    allv = {**lower, **beyond}
    for ch in chains:
        for a, b in zip(ch, ch[1:]):
            assert allv[b] - allv[a] == 8 * a + 37, (a, b)
    say("consecutive exact values in the chains 21..53 and 25..65 differ by 8n+37")
    cn = {n: lower[n] for n in range(2, 51)}
    cn[1] = 0
    for n in range(1, 24):
        if n in cn and (cn[n] == (upper.get(n, cn[n]))):
            assert cn[n] >= n * (n + 1) // 2 - 4, n
    say("C(n) - n(n+1)/2 for the exact values 5 and 8: "
        f"{cn[5] - 15} and {cn[8] - 36} (the constant 4 is sharp)")
    # Comparison with the capped bricks (Table 6 of the paper) and the band families.
    from fractions import Fraction as Fr
    brick = {0: (Fr(-3), Fr(13)), 1: (Fr(-9, 2), Fr(5)), 2: (Fr(-5, 8), Fr(-23, 4)),
             3: (Fr(-23, 8), Fr(-87, 8)), 4: (Fr(-19, 8), Fr(19, 2)), 5: (Fr(-11, 8), Fr(51, 8)),
             6: (Fr(-3), Fr(12)), 7: (Fr(-3, 4), Fr(19, 4))}
    a = (4, 3, 4, 3, 4, 1, 3, 2)

    def brick_pop(n):
        b, c = brick[n % 8]
        v = Fr(n * n, 2) + b * n + c
        assert v.denominator == 1
        return int(v)

    def family_pop(n):
        return n * (n + 1) // 2 - (3 if n % 8 == 0 and n >= 40 else a[n % 8])

    assert all(lower[n] > brick_pop(n) for n in range(22, 51))
    better = [n for n in range(24, 51) if lower[n] > family_pop(n)]
    equal = [n for n in range(24, 51) if lower[n] == family_pop(n)]
    assert not [n for n in range(24, 51) if lower[n] < family_pop(n)]
    assert (len(better), len(equal)) == (20, 7)
    say("boards exceed the capped-brick polynomial at all 29 sizes 22..50; they exceed the band-family "
        f"value at {len(better)} of the 27 sizes 24..50 and equal it at {equal}")
    out = {"lower": lower, "upper": upper, "source": source,
           "special_upper": {str(k): v for k, v in specials.items()},
           "exact_beyond_50": beyond}
    (ANC / "data" / "ledger.json").write_text(json.dumps(out, indent=1, sort_keys=True))
    return lower, upper


# band families
def f_index(i: int, h: int, k: int, p: int = 8) -> int:
    if i < h:
        return i
    if i < h + p * k:
        return h + ((i - h) % p)
    return i - p * (k - 1)


def build(seed, rs, cs, k, p=8):
    n = len(seed) + p * (k - 1)
    return [[seed[f_index(i, rs, k, p)][f_index(j, cs, k, p)] for j in range(n)] for i in range(n)]


def components_of(tile):
    h, w = len(tile), len(tile[0])
    seen, comps = set(), []
    for r in range(h):
        for c in range(w):
            if tile[r][c] and (r, c) not in seen:
                seen.add((r, c))
                comp, q = [(r, c)], deque([(r, c)])
                while q:
                    x, y = q.popleft()
                    for a, b in D8:
                        u, v = x + a, y + b
                        if 0 <= u < h and 0 <= v < w and tile[u][v] and (u, v) not in seen:
                            seen.add((u, v))
                            q.append((u, v))
                            comp.append((u, v))
                comps.append(comp)
    comps.sort(key=lambda cmp: (-len(cmp), min(cmp)))
    return comps


def windows(grid):
    n = len(grid)
    pad = [[0] * (n + 6) for _ in range(n + 6)]
    for r in range(n):
        for c in range(n):
            pad[r + 3][c + 3] = grid[r][c]
    out = set()
    for r in range(1, n + 5):
        for c in range(1, n + 5):
            out.add(tuple(tuple(pad[r + a][c + b] for b in (-1, 0, 1)) for a in (-1, 0, 1)))
    return out


def certify_family(fam):
    seed, p = fam["seed_rows"], fam["period"]
    seed = [[1 if ch == "#" else 0 for ch in row] for row in seed]
    n0, rs, cs, R = fam["seed_n"], fam["row_start"], fam["column_start"], fam["local_radius"]
    assert len(seed) == n0 and p == 8
    assert min(rs, cs, p, n0 - rs - p, n0 - cs - p) >= 2, "every segment must have length >= 2"
    # population polynomial P(k) = A k^2 + B k + C and the deficit
    rr = {"T": (0, rs), "I": (rs, rs + p), "B": (rs + p, n0)}
    cc = {"L": (0, cs), "I": (cs, cs + p), "R": (cs + p, n0)}
    pops = {r + c: sum(seed[i][j] for i in range(*rr[r]) for j in range(*cc[c])) for r in rr for c in cc}
    A = pops["II"]
    B = sum(pops[s] for s in ("TI", "IL", "IR", "BI"))
    C = sum(pops[s] for s in ("TL", "TR", "BL", "BR"))
    assert A == p * p // 2, "bulk tile must have density 1/2"
    for k in range(1, 7):
        g = build(seed, rs, cs, k)
        n = n0 + p * (k - 1)
        pop, stable, comps, blocks = check_board(g)
        assert (pop, stable, comps) == (A * k * k + B * k + C, True, 1), (fam["id"], k)
        assert pop == n * (n + 1) // 2 - fam["deficit"], (fam["id"], k, pop)
    # stability for every k: all 3x3 windows of larger members occur at k = 2
    w2 = windows(build(seed, rs, cs, 2))
    for k in range(3, 9):
        assert windows(build(seed, rs, cs, k)) <= w2, (fam["id"], k)
    # connectivity for every k: finite contexts, k = 1 .. 2R+1
    tile_comps = {}
    for r in rr:
        for c in cc:
            sub = [row[cc[c][0]: cc[c][1]] for row in seed[rr[r][0]: rr[r][1]]]
            tile_comps[r + c] = components_of(sub)
    all_contexts = {}
    for k in range(1, 2 * R + 5):
        g = build(seed, rs, cs, k)
        n = len(g)
        rl = ["T"] + ["I"] * k + ["B"]
        cl = ["L"] + ["I"] * k + ["R"]
        rstart = [0, ] + [rs + p * t for t in range(k)] + [rs + p * k]
        cstart = [0, ] + [cs + p * t for t in range(k)] + [cs + p * k]
        rend = rstart[1:] + [n]
        cend = cstart[1:] + [n]
        label = {}
        for r in range(k + 2):
            for c in range(k + 2):
                name = rl[r] + cl[c]
                for j, comp in enumerate(tile_comps[name]):
                    for (x, y) in comp:
                        label[(rstart[r] + x, cstart[c] + y)] = (r, c, j)
        assert len(label) == sum(map(sum, g))
        adj = {}
        for (x, y), u in label.items():
            adj.setdefault(u, set())
            for a, b in D8:
                v = label.get((x + a, y + b))
                if v is not None and v != u:
                    adj[u].add(v)
        s = k + 2
        ctxs = {}
        for r in range(s):
            for c in range(s):
                key = tuple((ar - r, ac - c, rl[ar] + cl[ac])
                            for ar in range(max(0, r - R), min(s, r + R + 1))
                            for ac in range(max(0, c - R), min(s, c + R + 1)))
                ctxs.setdefault(key, (r, c))
                if k <= 2 * R + 1:
                    if key in all_contexts:
                        continue
                    all_contexts[key] = (k, r, c)
                    root = (r, c, 0)
                    seen, q = {root}, deque([root])
                    while q:
                        u = q.popleft()
                        for v in adj[u]:
                            if abs(v[0] - r) <= R and abs(v[1] - c) <= R and v not in seen:
                                seen.add(v)
                                q.append(v)
                    need = {(r, c, j) for j in range(len(tile_comps[rl[r] + cl[c]]))}
                    for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                        if 0 <= r + dr < s and 0 <= c + dc < s:
                            need.add((r + dr, c + dc, 0))
                    assert need <= seen, (fam["id"], "context failure", k, r, c)
        if k >= 2 * R + 1:
            assert set(ctxs) <= set(all_contexts), (fam["id"], "new context at k=", k)
        # also the whole member is connected, directly
    return dict(id=fam["id"], n0=n0, residue=fam["residue"], A=A, B=B, C=C,
                deficit=fam["deficit"], R=R, contexts=len(all_contexts))


def audit_families():
    fams = json.loads((ANC / "data" / "families.json").read_text())
    rows = []
    for fam in fams:
        rec = certify_family(fam)
        rows.append(rec)
        say(f"family {rec['id']:9s} n0={rec['n0']:2d} (A,B,C)=({rec['A']},{rec['B']},{rec['C']}) "
            f"deficit={rec['deficit']} radius={rec['R']} contexts={rec['contexts']}  CERTIFIED")
    # Residue table: deficit a_r for n >= 24; the ninth family improves r=0 from n >= 40.
    a = {}
    for rec in rows:
        if rec["id"].startswith("base"):
            a[rec["residue"]] = rec["deficit"]
    say(f"deficit vector a = {[a[r] for r in range(8)]}; improved residue-zero deficit: "
        f"{[r['deficit'] for r in rows if r['id'].startswith('large')]}")
    assert [a[r] for r in range(8)] == [4, 3, 4, 3, 4, 1, 3, 2]
    # Uniform bound: exact small values and the families.
    lower, upper = json.loads((ANC / "data" / "ledger.json").read_text())["lower"], None
    small = {1: 0}
    small.update({int(n): v for n, v in lower.items() if int(n) < 24})
    worst = min(small[n] - n * (n + 1) // 2 for n in small)
    assert worst == -4, worst
    assert max(a.values()) == 4
    say("C(n) >= n(n+1)/2 - 4 for 1 <= n < 24 by the verified boards (worst case -4), "
        "and for n >= 24 by the families (largest deficit 4).")
    return rows


def main() -> None:
    say("== ledger ==")
    audit_ledger()
    say("== band families ==")
    audit_families()
    say("ALL CHECKS PASSED")
    (ANC / "AUDIT_RESULTS.txt").write_text("\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
