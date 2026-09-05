# Validation scope

The release contains 49 nonempty lower-bound witnesses and evidence for 29
exact values: n=1,...,25 and n=31,32,33,39.

The routine audit verifies both board implementations, bounds arithmetic,
complete candidate disconnection for n=5 and n=8, row-result/source consistency,
the finite closure summaries, n=22 dependency hashes and its terminal endpoint
contradiction, proof-index coverage and every distributed checksum.

The small-proof replay regenerates all 16 block-free threshold boards at n=5
and all 24 at n=8, and the entire n=10 and n=11 row computations. The n=13
certificate represents 3,926,925,326 transitions and optimum 88. Its source
and full regeneration command are included, as is an independent small-width
transition audit.

The finite n=19 and n=22 proofs retain all necessary boundary layers, not only
their terminal contradictions. The large proof generators were checked against
their complete records. Moving files and changing JSON whitespace requires
updated dependency hashes, not a change to the enumerated mathematical states.
Use the explicit full replay commands when independently verifying completeness;
the quick audit does not regenerate those states.

All 11 regression tests pass. The tests cover the exterior ring, diagonal connectivity, exact cycle-join
equivalence on random and adversarial graphs, complete small-board threshold
enumeration, and deliberate certificate corruption. A copied release can be
tested without the surrounding research project. The isolated-directory audit
and complete small-proof replay also pass. The reorganized n=22 drivers
regenerated depths 5–8, including complete accelerated record equality at depth
eight, and the n=19 exclusion regenerated completely. The full n=22 chain
remains included for independent regeneration through depth eleven.

No solver success summary substitutes for a proof in this release. The trust
boundary remains the mathematical completeness and correct implementation of
the row and boundary enumerators, plus the cited unrestricted maxima. No
proof-assistant formalization is claimed.
