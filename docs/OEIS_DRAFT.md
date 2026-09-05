# OEIS submission draft

This is a field-by-field draft for the OEIS new-sequence form, checked against
the [OEIS Style Sheet](https://oeis.org/wiki/Style_Sheet) on September 5, 2026.
Repeat a live duplicate search before submission. A direct OEIS search on
September 5, 2026 for the terms with the initial zero omitted returned no
results.

The [OEIS policy on AI](https://oeis.org/wiki/Use_of_AI_for_OEIS_Submissions)
makes the human submitter responsible for every statement and does not permit
submitting fully AI-written comments. Accordingly, the `COMMENTS` text below is
a factual scaffold: Siddhartha should verify and rewrite it in his own words.
Do not use AI to compose replies to OEIS editors.

## NAME

Maximum population of an 8-connected still life contained in an n X n square
in Conway's Game of Life, with a dead exterior.

## DATA

```text
0, 4, 6, 8, 11, 18, 28, 32, 43, 53, 63, 76, 88, 102, 119, 134, 151, 170, 188, 210, 230, 251, 276, 299, 325
```

Only the consecutive exact prefix belongs in this field. The isolated exact
values at n = 31, 32, 33, and 39 must not be appended after the gap.

## OFFSET

```text
1,2
```

## COMMENTS

Rewrite the following facts as personal prose before submitting:

- Two live cells are adjacent when they share an edge or a corner; all live
  cells must belong to one component under this adjacency.
- Stability is tested in the infinite plane with every cell outside the square
  dead. In particular, births immediately outside the square are forbidden.
- Empty margins inside the containing square are allowed. For n >= 2 the
  maximum is over nonempty patterns; a(1) = 0 is the empty-board convention.
- The terms through a(25) are proved exact. Further proved values are
  a(31) = 497, a(32) = 528, a(33) = 562, and a(39) = 782. The first unresolved
  term satisfies 349 <= a(26) <= 352.
- Each exact result has both a connected stable witness and a matching upper
  proof. The linked repository indexes the proof route and evidence for every
  claimed exact value.
- The problem appears as the Connected Maximum-density Still Life benchmark of
  the Fourth Answer Set Programming Competition in 2013. Siddhartha Mahajan
  found it there, recognized the associated integer-sequence question, and
  directed exact computation with AI assistance that established most of the
  optimal values reported here. The human submitter checked the claims and is
  responsible for the submission.

## REFERENCES

G. Chu and P. J. Stuckey, A complete solution to the Maximum Density Still Life
Problem, Artificial Intelligence, 184-185 (2012), 1-16.

## LINKS

Put the b-file first after an A-number has been assigned:

```html
S. Mahajan, <a href="/Axxxxxx/bxxxxxx.txt">Table of n, a(n) for n = 1..25</a>.
ASP Competition 2013, <a href="https://www.mat.unical.it/aspcomp2013/ConnectedMaximumDensityStillLife">Connected Maximum-density Still Life</a>.
G. Chu and P. J. Stuckey, <a href="https://doi.org/10.1016/j.artint.2012.02.001">A complete solution to the Maximum Density Still Life Problem</a>, Artificial Intelligence, 184-185 (2012), 1-16.
S. Mahajan, <a href="https://github.com/Siddhartha-Mahajan/connected-still-life/tree/v1.0.1">Maximum connected still lifes: witnesses, bounds, and reproducible optimality proofs</a>.
S. Mahajan, <a href="https://github.com/Siddhartha-Mahajan/connected-still-life/blob/v1.0.1/docs/optima_1_25.svg">Illustrations of the proved optima for n = 1..25</a>.
```

Use a permanent release tag or commit hash, not a moving branch URL. The
repository link should expose `data/proof_index.json`, the construction files,
and the reproduction instructions. The CAISc papers and their verified author
lists are collected in [REFERENCES.md](REFERENCES.md); they need not all be
placed in the short initial OEIS entry.

## FORMULA

```text
For n >= 14, a(n) <= floor((4*n^2 + 5*n - d(n mod 8))/8), where (d(0),...,d(7)) = (26,23,18,23,20,23,26,11).

a(n) <= A055397(n).

For k >= 0, a(100+54*k) >= 1458*k^2 + 5426*k + 5051.
```

The first two statements are proved upper bounds, not formulas for a(n). The
third is a proved constructive lower bound. The repository also proves
residue-dependent constructive lower bounds covering every n >= 10; omit them
from the initial entry unless their longer piecewise formula is genuinely
useful.

## EXAMPLE

```text
a(2) = 4, realized by the 2 X 2 block.

a(5) = 11. A complete block-free enumeration gives maximum population 12, but all 16 stable 12-cell candidates are disconnected; the repository supplies a connected stable 11-cell witness.

a(25) = 325, one less than the unrestricted still-life maximum A055397(25) = 326.
```

## MAPLE

Leave blank.

## MATHEMATICA

Leave blank.

## PROG

Leave blank. The repository contains Python and C++ programs for finite proofs,
witness verification, bounds, and lower-bound constructions, but no program
that computes the exact sequence for arbitrary n. Describe and link those
programs under `LINKS`; do not mislabel a bound generator as an exact sequence
program.

## CROSSREFS

```text
Cf. A055397.
```

## KEYWORD

```text
nonn,hard
```

## AUTHOR

```text
_Siddhartha Mahajan_, Sep 05 2026
```

The OEIS form fills this field automatically. Keep project acknowledgments and
the account of computational and AI assistance in `COMMENTS` or the linked
repository, not in `AUTHOR`.

## Final submission checks

- Search OEIS again using the data with the first term omitted.
- Re-run `python -B scripts/audit_release.py --replay-small` from the repository
  root and ensure it exits successfully.
- Compare `DATA` and the eventual b-file byte-for-byte with
  `data/exact_prefix.txt`.
- Replace `Axxxxxx` only after the assigned A-number exists; test every public
  link in a logged-out browser.
- Choose and record an explicit repository license before public release.
- Rewrite and personally verify `COMMENTS`, then sign any later edits or
  comments with four tildes as requested by OEIS.
