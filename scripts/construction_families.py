#!/usr/bin/env python3
"""Generate the period-six pond and period-eight capped-brick families."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VERIFIERS = ROOT / "verifiers"
if str(VERIFIERS) not in sys.path:
    sys.path.insert(0, str(VERIFIERS))

from life import verify_grid  # noqa: E402


POND = (
    (0, 1),
    (0, 2),
    (1, 0),
    (1, 3),
    (2, 0),
    (2, 3),
    (3, 1),
    (3, 2),
)
BRICK_TILE = (
    (0, 0, 0, 1, 1, 0, 0, 0),
    (1, 1, 1, 0, 0, 1, 1, 1),
)
THRESHOLDS = {
    0: 16,
    1: 17,
    2: 10,
    3: 11,
    4: 12,
    5: 13,
    6: 14,
    7: 15,
}
Role = tuple[str, int, int]


def pond_parameter(n: int) -> int:
    if n < 1:
        raise ValueError("n must be positive")
    return (n - 1) // 3


def pond_population(n: int) -> int:
    m = pond_parameter(n)
    even = (m + 1) // 2
    odd = m // 2
    return 8 * (even * even + odd * odd)


def pond_grid(n: int) -> list[list[int]]:
    m = pond_parameter(n)
    grid = [[0] * n for _ in range(n)]
    for i in range(m):
        for j in range(m):
            if (i - j) % 2:
                continue
            row0, column0 = 3 * i, 3 * j
            for dr, dc in POND:
                grid[row0 + dr][column0 + dc] = 1
    return grid


def parse_fraction(value: str) -> Fraction:
    numerator, separator, denominator = value.partition("/")
    return Fraction(
        int(numerator),
        int(denominator) if separator else 1,
    )


def cap_document(n: int) -> dict[str, Any]:
    residue = n % 8
    if n < THRESHOLDS[residue]:
        raise ValueError(
            f"residue {residue} begins at n={THRESHOLDS[residue]}"
        )
    path = ROOT / "data" / "caps" / f"r{residue}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if document["schema"] != "brick8-fixed-width-cap-v1":
        raise ValueError(f"unsupported cap schema in {path}")
    return document


def role_at(n: int, width: int, row: int, column: int) -> Role | None:
    if row < width and column < width:
        return ("tl", row, column)
    if row < width and column >= n - width:
        return ("tr", row, n - 1 - column)
    if row >= n - width and column < width:
        return ("bl", n - 1 - row, column)
    if row >= n - width and column >= n - width:
        return ("br", n - 1 - row, n - 1 - column)
    if row < width:
        return ("top", row, (column - width) % 8)
    if row >= n - width:
        return ("bottom", n - 1 - row, (column - width) % 8)
    if column < width:
        return ("left", (row - width) % 8, column)
    if column >= n - width:
        return ("right", (row - width) % 8, n - 1 - column)
    return None


def template_values(document: dict[str, Any]) -> dict[Role, int]:
    values = {}
    for encoded, value in document["template"].items():
        role, first, second = encoded.split("|")
        values[(role, int(first), int(second))] = int(value)
    return values


def brick_population(n: int, document: dict[str, Any]) -> int:
    formula = document["quadratic_formula"]
    value = (
        parse_fraction(formula["a"]) * n * n
        + parse_fraction(formula["b"]) * n
        + parse_fraction(formula["c"])
    )
    if value.denominator != 1:
        raise AssertionError("nonintegral population formula")
    return value.numerator


def brick_grid(n: int) -> list[list[int]]:
    document = cap_document(n)
    width = int(document["width"])
    row_phase = int(document["row_phase"])
    column_phase = int(document["column_phase"])
    values = template_values(document)
    grid = []
    for row in range(n):
        output_row = []
        for column in range(n):
            role = role_at(n, width, row, column)
            value = (
                values[role]
                if role is not None
                else BRICK_TILE[(row + row_phase) % 2][
                    (column + column_phase) % 8
                ]
            )
            output_row.append(value)
        grid.append(output_row)
    return grid


def payload(family: str, n: int) -> dict[str, Any]:
    if family == "pond":
        grid = pond_grid(n)
        population = pond_population(n)
        construction = "period-six parity pond lattice"
    elif family == "brick8":
        grid = brick_grid(n)
        population = brick_population(n, cap_document(n))
        construction = "period-eight capped brick"
    else:
        raise ValueError(family)
    check = verify_grid(grid, population)
    if not check.valid:
        raise AssertionError((family, n, check))
    return {
        "n": n,
        "claimed_cells": population,
        "construction": construction,
        "grid": grid,
    }


def certify(family: str, maximum_n: int) -> dict[str, Any]:
    if family == "pond":
        sizes = range(4, maximum_n + 1)
    else:
        sizes = [
            n
            for n in range(10, maximum_n + 1)
            if n >= THRESHOLDS[n % 8]
        ]
    rows = []
    for n in sizes:
        document = payload(family, n)
        rows.append(
            {
                "n": n,
                "population": document["claimed_cells"],
                "accepted": True,
            }
        )
    return {
        "family": family,
        "maximum_n": maximum_n,
        "all_accepted": all(row["accepted"] for row in rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("family", choices=("pond", "brick8"))
    parser.add_argument("--n", type=int)
    parser.add_argument("--certify-through", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if (args.n is None) == (args.certify_through is None):
        parser.error("provide exactly one of --n and --certify-through")
    result = (
        payload(args.family, args.n)
        if args.n is not None
        else certify(args.family, args.certify_through)
    )
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        target = (
            args.output
            if args.output.is_absolute()
            else ROOT / args.output
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding="utf-8")
        print(target)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
