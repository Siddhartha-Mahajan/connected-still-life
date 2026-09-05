# Definition, proofs and generators

C(n) maximizes the live-cell count among finite B3/S23 still lifes in an n × n
square whose live cells form one king-connected component. The surrounding
universe is dead. Checking the square and its full one-cell exterior ring
suffices for stability: farther cells have no live neighbors. C(1)=0 is the
empty-board convention. For n≥2 the maximum is over nonempty patterns.

## Lower and upper certificates

Each board in `constructions/` is a lower-bound certificate. Both bundled
verifiers check population, stability, the exterior and connectivity. The
[proof index](../data/proof_index.json) gives an upper-proof route for every
exact value. No exactness claim rests on a witness alone.

A live 2 × 2 block is an entire connected component of a still life: its four
cells already have three live neighbors each, so an additional adjacent live
cell would overpopulate at least one. Therefore every connected still life of
population greater than four is block-free. Maximizing over all block-free
still lifes, including disconnected ones, gives a valid upper relaxation.

| Sizes | Upper proof |
|:---|:---|
| 1 | A single live cell dies |
| 2,3,4,6,7,9,12,15,20,23,31,39 | Connected witness meets the unrestricted optimum in Chu–Stuckey, Table 7 |
| 5 | Block-free maximum 12; all 16 maximizing boards have two components |
| 8 | Block-free maximum 33; eight maximizing boards have two components and sixteen have three |
| 10,11,13 | Complete block-free row-DP maxima 53,63,88 match connected witnesses |
| 16,21,24,25,32,33 | Connected witness meets the general bound below |
| 14,17,18,19,22 | Complete finite boundary exclusions sharpen the general bound |

The row DP records the previous two row masks. Successor rows are generated
exhaustively, requiring stability of the middle row and side-exterior cells
and forbidding live 2 × 2 blocks. Two forced zero rows validate the bottom
and its exterior; two initial zero rows validate the top.

For n=5,8 an exact suffix maximum F(r,a,b) supports complete enumeration above
the proposed optimum: prune a prefix only if its population plus F cannot
reach the threshold. No symmetry filter is applied. All surviving boards are
stored in the row certificates and independently checked to be disconnected.

## General upper bound

For every n≥14, define

```text
U(n) = floor((4n² + 5n − d[n mod 8])/8),
d = [26,23,18,23,20,23,26,11].
```

Then C(n)≤U(n). Intersect with the unrestricted maximum M(n) where known.
The implementation is `scripts/boundary/upper_bounds.py` and the finite
certificates are in `certificates/upper_bounds/`.

The proof uses nonnegative local wastage with total W=2n²+4n−4P. A boundary
strip state records two column masks; exact physical corners connect strip
states. Four side-and-corner transfers form a directed closed walk. Ignoring
the unconstrained interior relaxes the problem, so the minimum boundary charge
is a lower bound on W and hence gives an upper bound on population P.

Depth four gives residues 1,2,3,4,6,7; depth five sharpens residue 5; the
depth-six equality lift handles residue 0. The certificates include finite
bases and exact min-plus matrix equalities. An equality T^(k+8)=T^k+3 propagates
to all larger powers by multiplying by T: this is not extrapolation from a
finite list of scalar observations. For residue 0 the finite bases are
n=16,24,32,40.

The recurrence U(n+8)−U(n)=8n+37 is for the **upper bound**, not C(n).
Boundary feasibility does not guarantee a connected interior completion.
The bound is attained at several listed sizes but no exact all-n formula is
claimed.

## Exceptional finite exclusions

- n=14: all 261,225 physical low-slack belts and their center completions are
  enumerated; all 224 population-103 completions are disconnected.
- n=17: complete target-charge-38 support has 21 states and 50 arcs. Keeping
  every tied physical corner, the next-layer minimum is 39, excluding 152.
- n=18: complete charge-36 equality support becomes empty at depth seven,
  excluding population 171.
- n=19: charge-42 support retains all physical realizations within the initial
  two units of slack. Minima at depths 5–8 are 40,42,42,42; support is empty at
  depth nine, excluding population 189.
- n=22: complete charge-48 support is lifted through depth eleven. Its 2,592
  terminal corner mappings have 180 distinct incoming and 180 outgoing states;
  these sets are disjoint, so no zero-length side can join successive corners.
  This excludes population 252. The earlier support layers are essential to
  the proof; the terminal intersection alone is not sufficient.

Larger populations are already excluded by the general bounds. These arguments
do not assume that deleting a live cell preserves stability.

The exact cycle join in `src/cycle_join.py` accelerates these finite supports.
Every four-step closed walk of total charge ≤K has an arc of charge ≤floor(K/4).
For each such anchor a→b and next arc b→c, intersect the exact-cost set
{d:T(c,d)=w} with {d:T(d,a)≤K−T(a,b)−T(b,c)−w}. Integer bitsets perform these
joins exactly. The supported subgraph preserves all feasible cycles, including
repeated vertices. Regression tests compare it with direct exhaustive enumeration.

## Constructive lower bounds

These formulas count actual generated connected stable patterns; they are not
formulas for the optimum. Their finite local checks and connectivity arguments
are implemented by the generator certification commands.

**Pond family.** For n≥4 let m=floor((n−1)/3), e=ceil(m/2), o=floor(m/2).
Place eight-cell ponds at offsets (3i,3j) for 0≤i,j<m with i≡j (mod 2).
The population is 8(e²+o²), with asymptotic density 4/9. The generator's local
and connectivity checks cover the small cases as well as the repeating motif.

**Capped brick family.** The repeating 2 × 8 tile has eight live cells. Fixed
caps for each residue give L(n)=n²/2+b_r n+c_r on the domains below.

| r=n mod 8 | First n | b_r | c_r |
|---:|---:|---:|---:|
| 0 | 16 | −3 | 13 |
| 1 | 17 | −9/2 | 5 |
| 2 | 10 | −5/8 | −23/4 |
| 3 | 11 | −23/8 | −87/8 |
| 4 | 12 | −19/8 | 19/2 |
| 5 | 13 | −11/8 | 51/8 |
| 6 | 14 | −3 | 12 |
| 7 | 15 | −3/4 | 19/4 |

Every n≥10 is covered. The cap certificates establish repetition safety and
connectivity, not merely agreement of several fitted population samples.
`scripts/certify_brick_family.py` checks the finite induction data. Local
neighborhoods are fixed corner, periodic edge or 2 × 8 bulk types; after
opposing corners separate, adding eight introduces no new type. A periodic
eight-row/eight-column extension attaches every new bulk component to the
connected core. Each frame cell has a bounded path to that core; separated
corner zones and a representative of every live edge role make those paths
translatable to all larger sizes. All smaller sizes below the translation
thresholds are checked directly. Complete periods also make the population
quadratic, independently of the numerical sample check.

**Period-54 family.** For every k≥0, n=100+54k admits a connected still life
with population

```text
1458k² + 5426k + 5051 = n²/2 + 13n/27 + 77/27.
```

The finite proof checks macrotile neighborhoods, connectivity ports and the
population polynomial; k=0 is checked explicitly. Arbitrary dead padding
embeds any such board in a larger square without changing stability or
connectivity. The same padding observation applies to every lower witness.

The brick family and U establish leading density 1/2. Neither determines the
exact optimum for every n. The first unresolved term remains n=26.

## Trust boundary

Checksums detect altered files; they do not prove an encoding complete. Upper
proofs require the stated local reductions and complete transition, corner and
support enumerations. The source and finite certificates are included for
inspection and regeneration. No proof-assistant formalization is claimed.
Published unrestricted maxima are cited dependencies, not reproduced searches.
