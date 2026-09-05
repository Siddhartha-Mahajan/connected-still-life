#!/usr/bin/env python3
"""Direct period-54 connected Chu-family construction and finite certificate.

A connected 154x154 board is split into fixed row blocks T/I/B of heights
42/54/58 and column blocks L/I/R of widths 48/54/52.  Repeating the I row
and I column blocks k times produces an n=100+54k board.  The proof has three
finite parts:

* population: count the nine macrotiles once;
* stability: Life has radius one, and every 3x3 window for k>=1 occurs in the
  k=2 member (which contains every cap, ordinary seam, and I-I seam type);
* connectivity: the nine tile-component types and their allowed interfaces
  form a connected macrograph for every k>=1.  The k=0 deletion member is
  checked separately.

This is a constructive lower bound for C(n), not an optimality theorem.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import sys
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VERIFIERS = ROOT / "verifiers"
sys.path.insert(0, str(VERIFIERS))

from life import NEIGHBOURS, verify_grid  # noqa: E402

BASE_PATH = ROOT / "data" / "period54_base_n154.json"
OUTDIR = ROOT / "build" / "period54"
PERIOD = 54
ROW_START = 42
COLUMN_START = 48
ROW_SEGMENTS = {"T": (0, 42), "I": (42, 96), "B": (96, 154)}
COLUMN_SEGMENTS = {"L": (0, 48), "I": (48, 102), "R": (102, 154)}


def delete_bands(
    grid: list[list[int]], row_start: int, column_start: int
) -> list[list[int]]:
    rows = grid[:row_start] + grid[row_start + PERIOD :]
    return [
        row[:column_start] + row[column_start + PERIOD :]
        for row in rows
    ]


def repeat_bands(
    base: list[list[int]], copies: int
) -> list[list[int]]:
    if copies < 1:
        raise ValueError("copies must be positive")
    rows = (
        base[:ROW_START]
        + base[ROW_START : ROW_START + PERIOD] * copies
        + base[ROW_START + PERIOD :]
    )
    return [
        row[:COLUMN_START]
        + row[COLUMN_START : COLUMN_START + PERIOD] * copies
        + row[COLUMN_START + PERIOD :]
        for row in rows
    ]


def load_base() -> list[list[int]]:
    payload = json.loads(BASE_PATH.read_text())
    grid = payload["grid"]
    check = verify_grid(grid, claimed_cells=11935)
    if not check.valid:
        raise AssertionError((BASE_PATH, check))
    return grid


def population(k: int) -> int:
    if k < 0:
        raise ValueError("k must be nonnegative")
    n = 100 + PERIOD * k
    # Equal forms on this even residue class.
    a = 1458 * k * k + 5426 * k + 5051
    b = n * n // 2 + 26 * k + 51
    c_num = 27 * n * n + 26 * n + 154
    if c_num % 54:
        raise AssertionError((k, n, c_num))
    c = c_num // 54  # n^2/2 + 13n/27 + 77/27
    if not (a == b == c):
        raise AssertionError((k, a, b, c))
    return a


def construct(k: int) -> list[list[int]]:
    if k < 0:
        raise ValueError("k must be nonnegative")
    base = load_base()
    if k == 0:
        grid = delete_bands(base, ROW_START, COLUMN_START)
    else:
        grid = repeat_bands(base, k)
    n = 100 + PERIOD * k
    if len(grid) != n or any(len(row) != n for row in grid):
        raise AssertionError((k, n, len(grid)))
    if sum(map(sum, grid)) != population(k):
        raise AssertionError((k, sum(map(sum, grid)), population(k)))
    return grid


def rectangular_components(grid: list[list[int]]) -> list[set[tuple[int, int]]]:
    rows = len(grid)
    columns = len(grid[0]) if rows else 0
    remaining = {
        (r, c)
        for r in range(rows)
        for c in range(columns)
        if grid[r][c]
    }
    result: list[set[tuple[int, int]]] = []
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque([start])
        while queue:
            r, c = queue.popleft()
            for dr, dc in NEIGHBOURS:
                point = (r + dr, c + dc)
                if point in remaining:
                    remaining.remove(point)
                    component.add(point)
                    queue.append(point)
        result.append(component)
    return sorted(result, key=lambda comp: (-len(comp), min(comp)))


def tiles(base: list[list[int]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row_name, (r0, r1) in ROW_SEGMENTS.items():
        for column_name, (c0, c1) in COLUMN_SEGMENTS.items():
            name = row_name + column_name
            grid = [row[c0:c1] for row in base[r0:r1]]
            components = rectangular_components(grid)
            component_index = {
                point: index
                for index, component in enumerate(components)
                for point in component
            }
            result[name] = {
                "grid": grid,
                "components": components,
                "component_index": component_index,
            }
    return result


def horizontal_edges(
    all_tiles: dict[str, dict[str, Any]], left: str, right: str
) -> list[tuple[int, int]]:
    left_grid = all_tiles[left]["grid"]
    right_grid = all_tiles[right]["grid"]
    left_index = all_tiles[left]["component_index"]
    right_index = all_tiles[right]["component_index"]
    last_column = len(left_grid[0]) - 1
    edges: set[tuple[int, int]] = set()
    for r in range(len(left_grid)):
        if not left_grid[r][last_column]:
            continue
        for dr in (-1, 0, 1):
            rr = r + dr
            if 0 <= rr < len(right_grid) and right_grid[rr][0]:
                edges.add(
                    (left_index[(r, last_column)], right_index[(rr, 0)])
                )
    return sorted(edges)


def vertical_edges(
    all_tiles: dict[str, dict[str, Any]], top: str, bottom: str
) -> list[tuple[int, int]]:
    top_grid = all_tiles[top]["grid"]
    bottom_grid = all_tiles[bottom]["grid"]
    top_index = all_tiles[top]["component_index"]
    bottom_index = all_tiles[bottom]["component_index"]
    last_row = len(top_grid) - 1
    edges: set[tuple[int, int]] = set()
    for c in range(len(top_grid[0])):
        if not top_grid[last_row][c]:
            continue
        for dc in (-1, 0, 1):
            cc = c + dc
            if 0 <= cc < len(bottom_grid[0]) and bottom_grid[0][cc]:
                edges.add(
                    (top_index[(last_row, c)], bottom_index[(0, cc)])
                )
    return sorted(edges)


def padded_window_signatures(grid: list[list[int]]) -> set[str]:
    """All radius-one binary windows, including centers in the dead ring."""
    n = len(grid)

    def value(r: int, c: int) -> int:
        return grid[r][c] if 0 <= r < n and 0 <= c < n else 0

    signatures = set()
    for r in range(-1, n + 1):
        for c in range(-1, n + 1):
            signatures.add(
                "".join(
                    str(value(r + dr, c + dc))
                    for dr in (-1, 0, 1)
                    for dc in (-1, 0, 1)
                )
            )
    return signatures


def macro_connectivity_certificate(base: list[list[int]]) -> dict[str, Any]:
    all_tiles = tiles(base)
    component_rows = {
        name: {
            "population": sum(map(sum, data["grid"])),
            "component_count": len(data["components"]),
            "component_sizes": [len(comp) for comp in data["components"]],
        }
        for name, data in sorted(all_tiles.items())
    }

    horizontal: dict[str, list[list[int]]] = {}
    for row_name in "TIB":
        for left, right in (("L", "I"), ("I", "I"), ("I", "R")):
            pair = row_name + left + "->" + row_name + right
            horizontal[pair] = [
                list(edge)
                for edge in horizontal_edges(
                    all_tiles, row_name + left, row_name + right
                )
            ]

    vertical: dict[str, list[list[int]]] = {}
    for column_name in "LIR":
        for top, bottom in (("T", "I"), ("I", "I"), ("I", "B")):
            pair = top + column_name + "->" + bottom + column_name
            vertical[pair] = [
                list(edge)
                for edge in vertical_edges(
                    all_tiles, top + column_name, bottom + column_name
                )
            ]

    # Every macrotile's largest component is component zero.  These main
    # components connect across every allowed neighboring macro-edge.
    main_edges_ok = all(
        [0, 0] in edges for edges in [*horizontal.values(), *vertical.values()]
    )

    # The only secondary components lie in TR, IR, and BR.  The following
    # interface incidences attach each one to a neighboring main component in
    # every possible position of the repeated right-edge column.
    secondary_requirements = {
        "TR_1_down_to_IR_main": [1, 0] in vertical["TR->IR"],
        "TR_2_down_to_IR_main": [2, 0] in vertical["TR->IR"],
        "IR_1_from_above_main_TR": [0, 1] in vertical["TR->IR"],
        "IR_2_from_above_main_TR": [0, 2] in vertical["TR->IR"],
        "IR_1_from_above_main_IR": [0, 1] in vertical["IR->IR"],
        "IR_2_from_above_main_IR": [0, 2] in vertical["IR->IR"],
        "IR_3_down_to_main_IR": [3, 0] in vertical["IR->IR"],
        "IR_4_down_to_main_IR": [4, 0] in vertical["IR->IR"],
        "IR_3_down_to_main_BR": [3, 0] in vertical["IR->BR"],
        "IR_4_down_to_main_BR": [4, 0] in vertical["IR->BR"],
        "BR_1_from_above_main_IR": [0, 1] in vertical["IR->BR"],
    }
    expected_secondary_counts = {
        "TL": 0, "TI": 0, "TR": 2,
        "IL": 0, "II": 0, "IR": 4,
        "BL": 0, "BI": 0, "BR": 1,
    }
    secondary_counts_ok = all(
        component_rows[name]["component_count"] - 1 == count
        for name, count in expected_secondary_counts.items()
    )

    accepted = (
        main_edges_ok
        and secondary_counts_ok
        and all(secondary_requirements.values())
    )
    if not accepted:
        raise AssertionError(
            (main_edges_ok, secondary_counts_ok, secondary_requirements)
        )
    return {
        "tile_components": component_rows,
        "horizontal_interface_component_edges": horizontal,
        "vertical_interface_component_edges": vertical,
        "main_component_grid_connected": main_edges_ok,
        "expected_secondary_component_counts": expected_secondary_counts,
        "secondary_counts_match": secondary_counts_ok,
        "secondary_attachment_requirements": secondary_requirements,
        "accepted": accepted,
        "proof": (
            "The component-zero part of every macrotile connects across every "
            "allowed horizontal and vertical macro-edge, so all main tile "
            "components form one component on the connected macrogrid. The "
            "only other tile components are the listed TR/IR/BR two-cell "
            "pieces; every such piece has a guaranteed edge to an adjacent "
            "main component, including first, interior, and last IR positions."
        ),
    }


def certify(regression_through: int = 16) -> dict[str, Any]:
    base = load_base()
    block_populations = {
        name: sum(map(sum, data["grid"]))
        for name, data in tiles(base).items()
    }
    constant = sum(block_populations[name] for name in ("TL", "TR", "BL", "BR"))
    linear = sum(block_populations[name] for name in ("TI", "IL", "IR", "BI"))
    quadratic = block_populations["II"]
    if (constant, linear, quadratic) != (5051, 5426, 1458):
        raise AssertionError((constant, linear, quadratic))

    basis = []
    basis_signatures: dict[int, set[str]] = {}
    for k in (0, 1, 2):
        grid = construct(k)
        check = verify_grid(grid, claimed_cells=population(k))
        if not check.valid:
            raise AssertionError((k, check))
        basis_signatures[k] = padded_window_signatures(grid)
        basis.append({
            "k": k,
            "n": len(grid),
            "population": check.population,
            "stable": check.stable,
            "connected": check.connected,
            "radius_one_window_types": len(basis_signatures[k]),
            "accepted": check.valid,
        })

    # k=2 contains every T/I/B local row type and L/I/R local column type,
    # including the I-I seam.  The following finite regression confirms the
    # predicted signature containment on larger members.
    regression = []
    sig2 = basis_signatures[2]
    for k in range(3, regression_through + 1):
        grid = construct(k)
        check = verify_grid(grid, claimed_cells=population(k))
        signatures = padded_window_signatures(grid)
        row = {
            "k": k,
            "n": len(grid),
            "population": check.population,
            "stable": check.stable,
            "connected": check.connected,
            "window_signatures_subset_of_k2": signatures <= sig2,
            "new_window_signatures": len(signatures - sig2),
            "accepted": check.valid and signatures <= sig2,
        }
        if not row["accepted"]:
            raise AssertionError(row)
        regression.append(row)

    macro = macro_connectivity_certificate(base)
    result = {
        "schema": "direct-periodic-connected-chu-family-v1",
        "claim_type": "constructive lower bound, not an exact formula for C(n)",
        "domain": "n=100+54k for every integer k>=0",
        "population_formulas": {
            "in_k": "1458*k^2 + 5426*k + 5051",
            "in_n_and_k": "n^2/2 + 26*k + 51",
            "in_n": "n^2/2 + 13*n/27 + 77/27",
            "ordinary_gap": "M(n) - population = 8*k+10",
        },
        "decomposition": {
            "row_blocks": {k: list(v) for k, v in ROW_SEGMENTS.items()},
            "column_blocks": {k: list(v) for k, v in COLUMN_SEGMENTS.items()},
            "repeat_rule": (
                "delete both I blocks for k=0; for k>=1 repeat the 54-row "
                "I block and 54-column I block k times"
            ),
            "macrotile_populations": dict(sorted(block_populations.items())),
            "constant_corner_sum": constant,
            "linear_strip_sum": linear,
            "quadratic_center_tile": quadratic,
        },
        "stability_certificate": {
            "basis_checks": basis,
            "finite_basis": "k=0 separately; k=2 for every k>=1",
            "proof": (
                "Life has radius one. All row segments and column segments "
                "have width at least 42. For k>=1, a 3x3 window is wholly "
                "inside a block or crosses one of T-I, I-I, I-B and L-I, "
                "I-I, I-R. Every Cartesian combination occurs in k=2, "
                "including the exterior dead ring. Since k=2 is stable, "
                "every k>=1 member is stable."
            ),
            "larger_member_regression": regression,
        },
        "connectivity_certificate": macro,
        "conclusion": (
            "C(100+54k) >= (100+54k)^2/2 + 26k + 51 for every k>=0."
        ),
        "all_finite_checks_accepted": (
            all(row["accepted"] for row in basis)
            and all(row["accepted"] for row in regression)
            and macro["accepted"]
        ),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--certify", action="store_true")
    parser.add_argument("--regression-through", type=int, default=16)
    args = parser.parse_args()
    if args.certify:
        payload = certify(args.regression_through)
        target = args.output or OUTDIR / "direct_periodic_family_certificate.json"
    else:
        if args.k is None:
            parser.error("provide --k or --certify")
        grid = construct(args.k)
        n = len(grid)
        payload = {
            "schema": "direct-periodic-connected-chu-witness-v1",
            "k": args.k,
            "n": n,
            "claimed_cells": population(args.k),
            "formula": "n^2/2 + 13*n/27 + 77/27",
            "source": str(BASE_PATH.relative_to(ROOT)),
            "grid": grid,
        }
        target = args.output or OUTDIR / f"connected_periodic_n{n}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n")
    print(target)


if __name__ == "__main__":
    main()
