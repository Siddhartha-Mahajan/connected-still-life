#!/usr/bin/env python3
"""Compile and run the row programs using only package-local build paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_BUILD = ROOT / "build" / "n13_row_dp"


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def compiler(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise SystemExit(f"compiler not found: {name}")
    return resolved


def compile_program(source: Path, output: Path, compiler_name: str) -> None:
    run(
        [
            compiler(compiler_name),
            "-O3",
            "-std=c++20",
            "-DNDEBUG",
            str(source),
            "-o",
            str(output),
        ]
    )


def normalized_record(path: Path) -> object:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value.pop("seconds", None)
        value.pop("compiler", None)
        value.pop("source_sha256", None)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument(
        "--compiler",
        action="append",
        choices=("g++", "clang++"),
        help="repeat to request both compilers; default is g++",
    )
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument(
        "--full-n13",
        action="store_true",
        help="run the several-billion-transition n=13 computation",
    )
    args = parser.parse_args()
    n = 13 if args.full_n13 else args.n
    if n == 13 and not args.full_n13:
        raise SystemExit("use --full-n13 to acknowledge the long n=13 run")
    if not 1 <= n <= 14:
        raise SystemExit("n must lie between 1 and 14")

    build = args.build_dir.resolve()
    build.mkdir(parents=True, exist_ok=True)
    compilers = args.compiler or ["g++"]
    records = []
    for compiler_name in compilers:
        stem = compiler_name.replace("+", "p")
        executable = build / f"blockfree_row_dp_{stem}"
        output = build / f"blockfree_n{n:02d}_{stem}.json"
        compile_program(HERE / "blockfree_row_dp.cpp", executable, compiler_name)
        run([str(executable), str(n), str(output), compiler_name])
        records.append(output)

    if n == 13:
        retained = ROOT / "certificates" / "rows" / "n13.json"
        for output in records:
            if normalized_record(output) != normalized_record(retained):
                raise SystemExit("fresh n=13 result differs from the retained certificate")
        print("MATCH retained n=13 certificate")

    if n in (10,11):
        retained = ROOT/"certificates/rows"/f"n{n:02d}.json"
        for output in records:
            if normalized_record(output) != normalized_record(retained):
                raise SystemExit(f"fresh n={n} result differs from the retained row certificate")
        print(f"MATCH retained n={n} certificate")

    if len(records) == 2:
        if normalized_record(records[0]) != normalized_record(records[1]):
            raise SystemExit("compiler-independent payloads differ")
        print("MATCH", records[0], records[1])


if __name__ == "__main__":
    main()
