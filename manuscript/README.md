# Extremal Connected Still Lifes in Square Boards (updated manuscript)

This folder holds an updated version of the paper. The original manuscript
(`connected_still_life_final_release/`, August 2026) was not modified.

## Layout of the paper

* Main text, pages 1 to 10: results, model, boundary upper bound, exact values,
  ledger through n = 50, band families and the uniform lower bound, open
  questions, acknowledgments, AI declaration, references.
* Appendices: A CAISc 2026 challenge and submissions; B boundary certificate
  data; C details of the specialized closures (n <= 11, 13, 14, 16, 17, 18, 19,
  22); D construction and repair methods; E earlier periodic families (pond,
  capped brick, period 54); F computational certificates; G atlas of every
  verified board for n = 2..50 and the optimal boards at n = 53, 57, 65.

## Contents

| Path | Purpose |
|:--|:--|
| `main.tex`, `main.pdf` | The paper (single author; October 2026) |
| `figures/` | `fig_*.tex` (TikZ/pgfplots), `atlas.tex` and `atlas/*.pdf` (one vector PDF per board), all generated; `periodic_families.pdf` is reused from the first version |
| `tables/` | `bounds_18_50.tex` (ledger) and `band_families.tex`, both generated |
| `ancillary/constructions/` | Verified boards that are new relative to the repository ledger: n = 26, 29, 35, 37, 40, 41, 43, 45, 46, 47, 49 (improved lower bounds) and n = 53, 55, 57, 65 |
| `ancillary/data/families.json` | The nine band-family seeds |
| `ancillary/data/ledger.json` | Lower and upper bounds for 2 <= n <= 50 (written by the audit script) |
| `ancillary/scripts/verify_manuscript.py` | Independent audit (standard library only) |
| `ancillary/scripts/make_figures.py` | Regenerates figures, the atlas, and tables from the ledger |
| `ancillary/AUDIT_RESULTS.txt` | Output of the last audit run |
| `MANIFEST.sha256` | SHA-256 of every file in this folder except itself |

## Build and audit

```sh
cd manuscript
python3 ancillary/scripts/verify_manuscript.py   # boards, ledger, band families
python3 ancillary/scripts/make_figures.py        # figures, atlas, tables
tectonic main.tex                                # or: pdflatex main.tex (twice)
```

The paper needs the packages of the first version plus `pgfplots`.

## What changed relative to the first version

* One author. Paras Chopra (Lossfunk mentor), Dr. Ankan Pal (reviewer), and
  the CAISc 2026 organizing team (Dhruv Trehan, Dhruv Kumar, Sasank Tripathi,
  Devansh Agarwal) are acknowledged. A short AI declaration names OpenAI's
  ChatGPT (Sol 5.6 and 6 Astra) for the search programs and proofs and
  Anthropic's Claude for help with the manuscript.
* Exact values: n = 1..25 (adds 18, 19, 22, 23, 24, 25), plus 29, 31, 32, 33,
  37, 39, 41, 45, 49, 53, 57, 65. The first open case is 350 <= C(26) <= 352.
* New closures at n = 18, 19, 22, and closure whenever a verified board meets
  the proved upper bound U(n).
* New lower bounds: the band families give C(n) >= n(n+1)/2 - 4 for every n,
  sharp at n = 5 and 8, with a connectivity argument for every repetition count.
* Shorter main text; technical details moved to appendices; the board atlas
  is now inside the paper and regenerated from the current boards.
* CAISc references: the vague "submission archive" entries were replaced by
  proper citations (authors, titles, OpenReview links); the home-page and
  call-for-papers entries were dropped. The brick motif is credited to Jaswal.
* The ASP competition citation now says Fourth (2013), not Third.

Left out on purpose: the band-period theorem and the width-eight strip-graph
obstruction from the continuation bundle.

## Scope of verification

The audit script recomputes board validity, the ledger arithmetic, the
statements about exact values and open intervals, the chains of exact values
whose increments equal 8n + 37, the comparisons with the capped bricks and
band families, and the full certification of the nine band families. It
reads the upper bounds from the repository ledger (`../data/bounds.json`) and
does not replay the boundary, row, or closure certificates; those are audited
by the repository's own scripts. The numbers quoted for the n = 19 and n = 22
closures were taken from `../certificates/exact_closures/`. The published
unrestricted maxima M(n) are cited, not recomputed.
