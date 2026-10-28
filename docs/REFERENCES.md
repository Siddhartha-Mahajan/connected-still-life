# References and attribution

## Problem origin and project attribution

The earliest public formulation of the connected optimization problem that we
located is the Fourth Answer Set Programming Competition's 2013 benchmark page:
[Connected Maximum-density Still Life](https://www.mat.unical.it/aspcomp2013/ConnectedMaximumDensityStillLife).
The page defines the square-grid problem, including diagonal connectivity, and
was last edited March 18, 2013 by Giovambattista Ianni. It should be cited as
the problem source; the edit credit alone is not evidence that Ianni originated
the mathematical question.

Siddhartha Mahajan found the problem on that page, recognized it as a candidate
integer sequence, and directed a computational investigation with AI assistance
that established most of the optimal values reported in this release. Siddhartha
remains responsible for checking and presenting the results. This wording
distinguishes discovery of the existing problem from authorship of its original
formulation.

The seven papers below are linked from the official
[CAISc 2026 accepted-papers page](https://caisc2026.github.io/accepted_papers.html).
Titles, author lists, and OpenReview identifiers follow that public listing,
checked September 5, 2026. The paper files are linked, not redistributed.
Conference acceptance is not used as evidence of optimality: the retained
mathematical evidence is indexed separately in [the proof index](../data/proof_index.json).

## Accepted CAISc connected-still-life papers

- **Venkata Pushpak Teja Menta.** [Verifier-Clean Connected Still Lifes Across All Box Sizes: A Complete CP-SAT Encoding with Annealing Polish](https://openreview.net/forum?id=4LBYPzoSUW). CAISc 2026. Full-board CP-SAT encoding and annealing methodology.
- **Akshat Singh Jaswal.** [How Dense Can a Connected Still Life Be? Records, Proven Optima, and Machine-Checked Certificates up to n = 32](https://openreview.net/forum?id=3WPIRgk9pS). CAISc 2026. Exact encodings, proof records, and the period-2-by-8 brick motif underlying this project's capped brick family. The residue caps and the family certification here are subsequent work.
- **Mike Collier and Brian Derfer.** [Connected Still Life Across an AI-Inclusive Cognitive Ecosystem: A Verifier-Attested Case Study](https://openreview.net/forum?id=2RLaZFD49N). CAISc 2026. Verifier-based search and construction comparison.
- **Sagar Reddy, John Michael Sujay Zakkam, Sai Rithvik Kanakamedala, Saili Myana, and Sri Sindhu Gunturi.** [Still Life, Still Living: An LLM Coding Agent's Trajectory on Connected Game-of-Life Patterns](https://openreview.net/forum?id=ojLUNf0fcA). CAISc 2026. Search methodology and construction comparison.
- **Praveen Sridhar.** [Hybrid Exact and Heuristic Search for Dense Connected Still Lifes](https://openreview.net/forum?id=BGHqGZz1iK). CAISc 2026. Hybrid exact/heuristic search and construction comparison.
- **Tanay Sodha.** [The Cost of Connectivity: Exact and Heuristic Bounds for the Connected Maximum Density Still Life Problem](https://openreview.net/forum?id=l3mTljsAht). CAISc 2026. Connectivity-constrained optimization and bounds.
- **Ahmad A Rushdi.** [A Spanning-Tree Encoding for the Connected Maximum Still-Life Problem](https://openreview.net/forum?id=c14oLVAvr5). CAISc 2026. Spanning-tree connectivity encoding.

## Mathematical sources

- **Geoffrey Chu and Peter J. Stuckey.** [A complete solution to the Maximum Density Still Life Problem](https://doi.org/10.1016/j.artint.2012.02.001), *Artificial Intelligence* 184–185 (2012), 1–16. Table 7 supplies the unrestricted maxima used here; the paper supplies the wastage framework and the original period-54 construction geometry. The connected period-54 family in this release uses a repaired connected seed.
- **Noam D. Elkies.** [The still-life density problem and its generalizations](https://arxiv.org/abs/math/9905194). Density bounds and the broader mathematical setting.
- **Stephen A. Silver.** [A055397: maximum population of an n × n stable pattern](https://oeis.org/A055397), OEIS. This is the unrestricted companion sequence. In particular its n=25 value is 326, whereas the connected value here is 325. The current OEIS values at n=24 and 26 are already corrected to 302 and 353.
- [CAISc 2026 verifiable problems](https://caisc2026.github.io/verifiable-problems/): the connected-still-life challenge from which this investigation developed.

Verification uses the two bundled implementations and does not require a
conference service or private review artifacts.
