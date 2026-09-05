# Reproduction

Run commands from the repository root. Python 3.11+ and NumPy are required;
row computations need a C++20 compiler. Install `requirements-dev.txt` for tests.
No SAT solver, conference service, network access or parent repository is
needed once dependencies are installed.

## Routine audit and small upper proofs

```sh
python -B scripts/audit_release.py
python -B scripts/audit_release.py --replay-small
python -m pytest -q
```

The first checks 49 boards with both verifiers, all bounds and exact values,
certificate consistency, n=22 source/preceding-layer hashes and the terminal
endpoint contradiction, and the full file manifest. The second additionally
compiles and completely regenerates the n=5,8,10,11 row proofs. Reports and
executables go under ignored `build/`. It does not replay the larger searches.

Individual commands:

```sh
python -B verifiers/life.py constructions/n25.json
python -B scripts/prove_small_by_rows.py 5 --verify
python -B scripts/prove_small_by_rows.py 8 --verify
python -B scripts/rows/run_row_dp.py --n 10
python -B scripts/rows/run_row_dp.py --n 11
python -B scripts/rows/run_row_dp.py --full-n13
```

The n=13 computation examines about 3.93 billion transitions and can take
several minutes. The row commands compare complete numerical records with
saved certificates, excluding compiler and elapsed-time labels.

## Boundary proofs

```sh
python -B scripts/replay_computations.py boundary
python -B scripts/replay_computations.py n14
python -B scripts/replay_computations.py n17
python -B scripts/replay_computations.py n18
python -B scripts/replay_computations.py n19
python -B scripts/replay_computations.py n22-fast
```

Add `--list` to inspect the commands. These are full enumerations and can
require substantial RAM and minutes to hours. JSON reports and logs go under
`build/replays/`. `--timeout SECONDS` limits each child process; a timeout is
an incomplete run, never an upper proof.

The boundary group includes all four residue-zero finite-base decompositions.
The n=22 group regenerates depths 5–11; `n22-fast` uses exact bitset cycle joins
at depths 8 onward. `n22` uses direct cycle enumeration. Both require complete
record equality. `--start-depth 8` resumes with earlier certificates as inputs
and must not be described as a complete replay of those earlier layers.

`src/engines/` contains the locally configured engines used by n=22. Use the
documented n=22 drivers, not internal helper modules as standalone programs.

## Lower-bound generators

```sh
python -B scripts/construction_families.py pond --n 31 --output build/pond31.json
python -B scripts/construction_families.py brick8 --n 50 --output build/brick50.json
python -B scripts/period54_family.py --k 1 --output build/period54_n154.json
python -B scripts/certify_brick_family.py
python -B scripts/replay_computations.py families
```

The family group checks finite local certificates and regressions through
n=80 for ponds/bricks and k=8 for period-54. The all-size claims depend on the
finite motif and connectivity proofs, not regression alone.

## Repository maintenance

```sh
python -B scripts/build_release_metadata.py
```

This regenerates the proof index, results table, 25-panel SVG and manifest.
It does not repair mathematical certificates or mark computations successful.
After changing proof code or inputs, regenerate the affected certificates in
dependency order before rebuilding the manifest. JSON is compact on disk;
use `python -m json.tool FILE` to inspect it with indentation.
