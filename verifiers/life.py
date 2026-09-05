#!/usr/bin/env python3
"""Independent verifier for finite 8-connected Conway still lifes."""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


NEIGHBOURS = tuple(
    (dr, dc)
    for dr in (-1, 0, 1)
    for dc in (-1, 0, 1)
    if dr or dc
)


@dataclass(frozen=True)
class Verification:
    valid: bool
    n: int
    population: int
    claimed_cells: int | None
    stable: bool
    connected: bool
    components: int
    component_sizes: tuple[int, ...]
    live_2x2_blocks: int
    violations: tuple[dict[str, Any], ...]
    grid_sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable record for proof-program reports."""

        return asdict(self)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_grid_shape(grid: Any) -> list[list[int]]:
    if not isinstance(grid, list) or not grid:
        raise ValueError("grid must be a nonempty list")
    n = len(grid)
    normalized: list[list[int]] = []
    for row in grid:
        if not isinstance(row, list) or len(row) != n:
            raise ValueError("grid must be square")
        if any(value not in (0, 1, False, True) for value in row):
            raise ValueError("grid entries must be binary")
        normalized.append([int(value) for value in row])
    return normalized


def cell(grid: list[list[int]], row: int, column: int) -> int:
    n = len(grid)
    return (
        grid[row][column]
        if 0 <= row < n and 0 <= column < n
        else 0
    )


def live_neighbour_count(
    grid: list[list[int]], row: int, column: int
) -> int:
    return sum(
        cell(grid, row + dr, column + dc)
        for dr, dc in NEIGHBOURS
    )


def connected_components(
    grid: list[list[int]],
) -> list[set[tuple[int, int]]]:
    n = len(grid)
    remaining = {
        (row, column)
        for row in range(n)
        for column in range(n)
        if grid[row][column]
    }
    components = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        component = {start}
        queue = deque([start])
        while queue:
            row, column = queue.popleft()
            for dr, dc in NEIGHBOURS:
                target = (row + dr, column + dc)
                if target in remaining:
                    remaining.remove(target)
                    component.add(target)
                    queue.append(target)
        components.append(component)
    return sorted(components, key=lambda group: (-len(group), min(group)))


def live_block_count(grid: list[list[int]]) -> int:
    n = len(grid)
    return sum(
        all(
            grid[row + dr][column + dc]
            for dr in (0, 1)
            for dc in (0, 1)
        )
        for row in range(n - 1)
        for column in range(n - 1)
    )


def verify_grid(
    grid: Any, claimed_cells: int | None = None
) -> Verification:
    normalized = validate_grid_shape(grid)
    n = len(normalized)
    population = sum(map(sum, normalized))
    violations: list[dict[str, Any]] = []
    for row in range(-1, n + 1):
        for column in range(-1, n + 1):
            state = cell(normalized, row, column)
            neighbours = live_neighbour_count(
                normalized, row, column
            )
            if state and neighbours not in (2, 3):
                violations.append(
                    {
                        "cell": [row, column],
                        "state": 1,
                        "live_neighbours": neighbours,
                        "kind": "survival",
                    }
                )
            if not state and neighbours == 3:
                violations.append(
                    {
                        "cell": [row, column],
                        "state": 0,
                        "live_neighbours": neighbours,
                        "kind": "birth",
                    }
                )
    components = connected_components(normalized)
    connected = len(components) == 1
    claim_matches = (
        claimed_cells is None or claimed_cells == population
    )
    stable = not violations
    return Verification(
        valid=stable and connected and claim_matches,
        n=n,
        population=population,
        claimed_cells=claimed_cells,
        stable=stable,
        connected=connected,
        components=len(components),
        component_sizes=tuple(len(group) for group in components),
        live_2x2_blocks=live_block_count(normalized),
        violations=tuple(violations),
        grid_sha256=canonical_digest(normalized),
    )


def verify_payload(payload: dict[str, Any]) -> Verification:
    grid = payload.get("grid")
    claimed = payload.get("claimed_cells")
    result = verify_grid(grid, claimed)
    if payload.get("n") != result.n:
        return Verification(
            **{
                **asdict(result),
                "valid": False,
                "violations": tuple(
                    [
                        *result.violations,
                        {
                            "kind": "dimension_claim",
                            "claimed_n": payload.get("n"),
                            "actual_n": result.n,
                        },
                    ]
                ),
            }
        )
    return result


def verify_file(path: Path) -> Verification:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top level must be an object")
    return verify_payload(payload)


def result_document(
    path: Path, result: Verification
) -> dict[str, Any]:
    return {
        "path": str(path),
        **asdict(result),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    rows = []
    accepted = True
    for path in args.paths:
        result = verify_file(path)
        rows.append(result_document(path, result))
        accepted &= result.valid
    print(json.dumps({"accepted": accepted, "results": rows}, indent=2))
    raise SystemExit(0 if accepted else 1)


if __name__ == "__main__":
    main()
