#!/usr/bin/env python3
"""Independent verifier for finite connected Conway still lifes.

The submitted grid is interpreted as a finite subset of the infinite Life
universe: every cell outside the grid is dead.  It is enough to inspect the
grid and its complete one-cell exterior ring, i.e. positions
``[-1, n] x [-1, n]`` for an ``n x n`` grid.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Sequence


NEIGHBOURS = tuple(
    (dr, dc)
    for dr in (-1, 0, 1)
    for dc in (-1, 0, 1)
    if (dr, dc) != (0, 0)
)


@dataclass(frozen=True)
class Verification:
    valid: bool
    n: int
    population: int
    stable: bool
    connected: bool
    components: int
    violations: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["violations"] = list(self.violations)
        return result


def normalize_grid(value: Any) -> list[list[int]]:
    """Return a strict square 0/1 grid or raise ``ValueError``."""
    if not isinstance(value, list):
        raise ValueError("grid must be a list of rows")
    n = len(value)
    if n == 0:
        raise ValueError("grid must have at least one row")
    grid: list[list[int]] = []
    for r, row in enumerate(value):
        if not isinstance(row, list) or len(row) != n:
            length = len(row) if isinstance(row, list) else "non-list"
            raise ValueError(f"row {r} has length {length}; expected {n}")
        clean: list[int] = []
        for c, cell in enumerate(row):
            if isinstance(cell, bool):
                cell = int(cell)
            if isinstance(cell, float) and cell.is_integer():
                cell = int(cell)
            if type(cell) is not int or cell not in (0, 1):
                raise ValueError(f"grid[{r}][{c}]={cell!r} is not 0 or 1")
            clean.append(cell)
        grid.append(clean)
    return grid


def live_neighbour_count(
    grid: Sequence[Sequence[int]], r: int, c: int
) -> int:
    n = len(grid)
    return sum(
        grid[r + dr][c + dc]
        for dr, dc in NEIGHBOURS
        if 0 <= r + dr < n and 0 <= c + dc < n
    )


def connected_components(
    grid: Sequence[Sequence[int]],
) -> list[set[tuple[int, int]]]:
    n = len(grid)
    unseen = {
        (r, c)
        for r in range(n)
        for c in range(n)
        if grid[r][c] == 1
    }
    components: list[set[tuple[int, int]]] = []
    while unseen:
        start = min(unseen)
        component = {start}
        unseen.remove(start)
        queue = deque([start])
        while queue:
            r, c = queue.popleft()
            for dr, dc in NEIGHBOURS:
                cell = (r + dr, c + dc)
                if cell in unseen:
                    unseen.remove(cell)
                    component.add(cell)
                    queue.append(cell)
        components.append(component)
    return components


def verify_grid(
    value: Any,
    *,
    claimed_cells: int | None = None,
    max_violations: int = 50,
) -> Verification:
    grid = normalize_grid(value)
    n = len(grid)
    population = sum(map(sum, grid))
    violations: list[dict[str, Any]] = []

    if claimed_cells is not None and claimed_cells != population:
        violations.append(
            {
                "type": "count",
                "claimed": claimed_cells,
                "actual": population,
            }
        )

    # The full (n+2) x (n+2) box includes all in-box cells and every exterior
    # position that could have a live neighbour.  Farther cells see zero live
    # neighbours and therefore cannot change.
    for r in range(-1, n + 1):
        for c in range(-1, n + 1):
            neighbours = live_neighbour_count(grid, r, c)
            alive = 0 <= r < n and 0 <= c < n and grid[r][c] == 1
            bad = (alive and neighbours not in (2, 3)) or (
                not alive and neighbours == 3
            )
            if bad and len(violations) < max_violations:
                violations.append(
                    {
                        "type": "survival" if alive else "birth",
                        "cell": [r, c],
                        "neighbours": neighbours,
                    }
                )

    components = connected_components(grid)
    connected = len(components) == 1
    if not connected and len(violations) < max_violations:
        violations.append(
            {
                "type": "connectivity",
                "components": len(components),
                "component_sizes": sorted(
                    (len(component) for component in components), reverse=True
                ),
            }
        )

    stable = not any(
        violation["type"] in {"survival", "birth"}
        for violation in violations
    )
    valid = (
        population > 0
        and stable
        and connected
        and not any(v["type"] == "count" for v in violations)
    )
    return Verification(
        valid=valid,
        n=n,
        population=population,
        stable=stable,
        connected=connected,
        components=len(components),
        violations=tuple(violations),
    )


def verify_payload(payload: Any) -> Verification:
    if not isinstance(payload, dict) or "grid" not in payload:
        raise ValueError("payload must be an object containing grid")
    claimed = payload.get("claimed_cells")
    if claimed is not None:
        if isinstance(claimed, bool):
            raise ValueError("claimed_cells must be an integer")
        try:
            claimed = int(claimed)
        except (TypeError, ValueError) as exc:
            raise ValueError("claimed_cells must be an integer") from exc
    result = verify_grid(payload["grid"], claimed_cells=claimed)
    if "n" in payload and int(payload["n"]) != result.n:
        violations = list(result.violations)
        violations.insert(
            0,
            {
                "type": "dimension",
                "claimed_n": int(payload["n"]),
                "actual_n": result.n,
            },
        )
        return Verification(
            valid=False,
            n=result.n,
            population=result.population,
            stable=result.stable,
            connected=result.connected,
            components=result.components,
            violations=tuple(violations),
        )
    return result


def pad_grid(
    grid: Sequence[Sequence[int]],
    n: int,
    *,
    row_offset: int = 0,
    col_offset: int = 0,
) -> list[list[int]]:
    source = normalize_grid([list(row) for row in grid])
    m = len(source)
    if n < m or row_offset < 0 or col_offset < 0:
        raise ValueError("source does not fit in requested destination")
    if row_offset + m > n or col_offset + m > n:
        raise ValueError("source does not fit at requested offset")
    result = [[0] * n for _ in range(n)]
    for r in range(m):
        result[r + row_offset][col_offset : col_offset + m] = source[r]
    return result


def bounding_square(
    grid: Sequence[Sequence[int]],
) -> tuple[list[list[int]], tuple[int, int, int, int]]:
    """Crop to the live bounding rectangle and pad it to a top-left square."""
    clean = normalize_grid([list(row) for row in grid])
    live = [
        (r, c)
        for r, row in enumerate(clean)
        for c, value in enumerate(row)
        if value
    ]
    if not live:
        raise ValueError("empty pattern has no live bounding square")
    r0 = min(r for r, _ in live)
    r1 = max(r for r, _ in live)
    c0 = min(c for _, c in live)
    c1 = max(c for _, c in live)
    height = r1 - r0 + 1
    width = c1 - c0 + 1
    size = max(height, width)
    cropped = [[0] * size for _ in range(size)]
    for r in range(height):
        for c in range(width):
            cropped[r][c] = clean[r0 + r][c0 + c]
    return cropped, (r0, r1, c0, c1)


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify_payload(_load(args.payload))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2))
        return 2
    print(
        json.dumps(
            result.to_dict(),
            indent=2 if args.pretty else None,
            sort_keys=True,
        )
    )
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

