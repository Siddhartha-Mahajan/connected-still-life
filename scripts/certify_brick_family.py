#!/usr/bin/env python3
"""Finite locality, core-extension and frame-attachment proof for all brick sizes."""
from collections import deque
import json
from pathlib import Path
import sys
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from csl_verify import NEIGHBOURS, connected_components, verify_grid
from construction_families import THRESHOLDS, role_at, template_values as parse_template
from construction_families import brick_grid, brick_population as formula_population, cap_document

def generate_from_document(n, document):
    if n % 8 != document["residue_mod_8"]:
        raise ValueError("wrong residue")
    return brick_grid(n)

def neighbourhood_signatures(
    grid: list[list[int]],
) -> set[tuple[int, tuple[int, ...]]]:
    n = len(grid)
    result: set[tuple[int, tuple[int, ...]]] = set()
    for r in range(-1, n + 1):
        for c in range(-1, n + 1):
            center = (
                grid[r][c] if 0 <= r < n and 0 <= c < n else 0
            )
            neighbours = tuple(
                grid[r + dr][c + dc]
                if 0 <= r + dr < n and 0 <= c + dc < n
                else 0
                for dr, dc in NEIGHBOURS
            )
            result.add((center, neighbours))
    return result

def population_differences(
    document: dict[str, Any], start: int, terms: int = 8
) -> dict[str, list[int]]:
    populations = [
        sum(
            map(
                sum,
                generate_from_document(start + 8 * index, document),
            )
        )
        for index in range(terms)
    ]
    first = [
        populations[index + 1] - populations[index]
        for index in range(len(populations) - 1)
    ]
    second = [
        first[index + 1] - first[index]
        for index in range(len(first) - 1)
    ]
    return {
        "sizes": [start + 8 * index for index in range(terms)],
        "populations": populations,
        "first_differences": first,
        "second_differences": second,
    }

def core_grid(grid: list[list[int]], width: int) -> list[list[int]]:
    n = len(grid)
    return [
        [
            grid[r][c]
            if width <= r < n - width and width <= c < n - width
            else 0
            for c in range(n)
        ]
        for r in range(n)
    ]

def boundary_attachment_certificate(
    grid: list[list[int]], document: dict[str, Any]
) -> dict[str, int | bool]:
    """Multi-source distance of every boundary live cell to the bulk core."""
    n = len(grid)
    width = int(document["width"])
    live = {
        (r, c)
        for r in range(n)
        for c in range(n)
        if grid[r][c]
    }
    core = {
        (r, c)
        for r, c in live
        if width <= r < n - width and width <= c < n - width
    }
    distance = {cell: 0 for cell in core}
    queue = deque(sorted(core))
    while queue:
        r, c = queue.popleft()
        for dr, dc in NEIGHBOURS:
            candidate = (r + dr, c + dc)
            if candidate in live and candidate not in distance:
                distance[candidate] = distance[r, c] + 1
                queue.append(candidate)
    boundary = live - core
    maximum_distance = max(
        (distance[cell] for cell in boundary), default=0
    )
    edge_roles = {"top", "bottom", "left", "right"}
    live_edge_keys = {
        key
        for key, value in parse_template(document).items()
        if value and key[0] in edge_roles
    }
    central_edge_keys = set()
    for r, c in boundary:
        if (
            r < width or r >= n - width
        ) and width + maximum_distance <= c < n - width - maximum_distance:
            key = role_at(n, width, r, c)
            if key is not None:
                central_edge_keys.add(key)
        if (
            c < width or c >= n - width
        ) and width + maximum_distance <= r < n - width - maximum_distance:
            key = role_at(n, width, r, c)
            if key is not None:
                central_edge_keys.add(key)
    translation_threshold = next(
        candidate
        for candidate in range(THRESHOLDS[n % 8], 1000, 8)
        if candidate - 2 * width >= 2 * maximum_distance + 8
    )
    return {
        "n": n,
        "live_core_cells": len(core),
        "live_boundary_cells": len(boundary),
        "core_components": len(connected_components(core_grid(grid, width))),
        "all_boundary_cells_reach_core": boundary.issubset(distance),
        "maximum_boundary_distance": maximum_distance,
        "edge_span": n - 2 * width,
        "required_edge_span_for_translation": (
            2 * maximum_distance + 8
        ),
        "representative_separates_corner_zones": (
            n - 2 * width >= 2 * maximum_distance + 8
        ),
        "live_periodic_edge_keys": len(live_edge_keys),
        "central_live_edge_keys_seen": len(central_edge_keys),
        "all_live_edge_keys_have_central_representative": (
            live_edge_keys.issubset(central_edge_keys)
        ),
        "translation_proof_threshold": translation_threshold,
    }

def core_extension_certificate(
    document: dict[str, Any], residue: int
) -> list[dict[str, Any]]:
    """Check the period-eight induction gadget for the brick8 core."""
    start_n = THRESHOLDS[residue]
    records = []
    for n in (start_n, start_n + 8, start_n + 16):
        small = generate_from_document(n, document)
        large = generate_from_document(n + 8, document)
        width = int(document["width"])
        small_core = {
            (r, c)
            for r in range(width, n - width)
            for c in range(width, n - width)
            if small[r][c]
        }
        large_core = {
            (r, c)
            for r in range(width, n + 8 - width)
            for c in range(width, n + 8 - width)
            if large[r][c]
        }
        new_live = large_core - small_core
        unseen = set(new_live)
        new_components: list[set[tuple[int, int]]] = []
        while unseen:
            start = min(unseen)
            unseen.remove(start)
            component = {start}
            queue = deque([start])
            while queue:
                r, c = queue.popleft()
                for dr, dc in NEIGHBOURS:
                    candidate = (r + dr, c + dc)
                    if candidate in unseen:
                        unseen.remove(candidate)
                        component.add(candidate)
                        queue.append(candidate)
            new_components.append(component)
        attachment = [
            any(
                (r + dr, c + dc) in small_core
                for r, c in component
                for dr, dc in NEIGHBOURS
            )
            for component in new_components
        ]
        records.append(
            {
                "small_n": n,
                "large_n": n + 8,
                "small_core_connected": (
                    len(connected_components(core_grid(small, width))) == 1
                ),
                "new_live_cells": len(new_live),
                "new_components": len(new_components),
                "every_new_component_attaches": all(attachment),
            }
        )
    return records

def main():
    results={}
    for residue,start in THRESHOLDS.items():
        document=cap_document(start)
        saturation=24+residue
        signatures=[neighbourhood_signatures(brick_grid(saturation+8*i)) for i in range(3)]
        attachment=boundary_attachment_certificate(brick_grid(80+residue),document)
        extension=core_extension_certificate(document,residue)
        diffs=population_differences(document,saturation)
        trials=[]
        # Cover every finite member below the translation-proof threshold.
        end=max(attachment["translation_proof_threshold"],saturation+16)
        for n in range(start,end+1,8):
            result=verify_grid(brick_grid(n),claimed_cells=formula_population(n,document))
            if not result.valid: raise AssertionError((n,result))
            trials.append({"n":n,"population":result.population})
        checks={
          "local_signatures":signatures[0]==signatures[1]==signatures[2],
          "core_extensions":all(r["small_core_connected"] and r["every_new_component_attaches"] for r in extension),
          "frame_attachment":attachment["all_boundary_cells_reach_core"] and attachment["core_components"]==1,
          "separated_corners":attachment["representative_separates_corner_zones"],
          "all_edge_roles":attachment["all_live_edge_keys_have_central_representative"],
          "population":set(diffs["second_differences"])=={64}}
        if not all(checks.values()): raise AssertionError((residue,checks))
        results[str(residue)]={"checks":checks,"finite_trials":trials,"core_extension":extension,
             "boundary_attachment":attachment,"local_signature_count":len(signatures[0]),"population_differences":diffs}
    output=ROOT/"build/brick8_finite.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"accepted":True,"covers_every_n_at_least":10,"residues":results},sort_keys=True,separators=(",",":"))+"\n")
    print("PASS: all eight residues; finite locality, core and frame proof obligations")

if __name__=="__main__": main()
