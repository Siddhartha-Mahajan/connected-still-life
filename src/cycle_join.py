"""Exact bounded four-cycle support by integer-bitset joins.

No dependency on Life or on the boundary engine. Nonnegative integer
arc weights are required. Self-loops and repeated vertices are allowed.
"""
from collections import defaultdict


def supported_arcs(transfer, target):
    """Return precisely the arcs on a directed four-step walk of cost <= target.

    Every such closed walk has an anchor of cost <= floor(target/4).
    For anchor a->b and next arc b->c, join c->d at exact cost w with
    d->a at cost <= target-cost(a,b)-cost(b,c)-w. Bit intersections perform
    this join exactly; no numerical relaxation or heuristic filtering is used.
    """
    if not isinstance(target, int) or target < 0:
        raise ValueError("target must be a nonnegative integer")
    outgoing = defaultdict(list)
    buckets = defaultdict(dict)
    incoming = defaultdict(dict)
    for (a, b), cost in transfer.items():
        if not all(isinstance(x, int) and x >= 0 for x in (a, b, cost)):
            raise ValueError("state indices and costs must be nonnegative integers")
        if cost > target:
            continue
        outgoing[a].append((b, cost))
        buckets[a][cost] = buckets[a].get(cost, 0) | (1 << b)
        incoming[b][cost] = incoming[b].get(cost, 0) | (1 << a)
    cumulative = {}
    for a, by_cost in incoming.items():
        masks = []
        bits = 0
        for cost in range(target + 1):
            bits |= by_cost.get(cost, 0)
            masks.append(bits)
        cumulative[a] = masks
    minimum_out = {a: min(by_cost) for a, by_cost in buckets.items()}
    minimum_in = {a: min(by_cost) for a, by_cost in incoming.items()}
    ordered_buckets = {a: sorted(by_cost.items()) for a, by_cost in buckets.items()}
    support = set()
    for a, b in sorted(transfer):
        first_cost = transfer[a, b]
        if first_cost > target // 4 or a not in cumulative:
            continue
        returns = cumulative[a]
        last_min = minimum_in[a]
        for c, second_cost in outgoing.get(b, ()):
            budget = target - first_cost - second_cost
            if budget < minimum_out.get(c, target + 1) + last_min:
                continue
            for third_cost, destinations in ordered_buckets[c]:
                if third_cost + last_min > budget:
                    break
                matches = destinations & returns[budget - third_cost]
                if matches:
                    support.add((a, b))
                    support.add((b, c))
                while matches:
                    bit = matches & -matches
                    d = bit.bit_length() - 1
                    support.add((c, d))
                    support.add((d, a))
                    matches ^= bit
    return support


def accelerate(reference):
    """Preserve the reference report, counts and sample order exactly.

    The reference enumerator now runs only on the supported subgraph. This
    cannot add or remove a feasible cycle. Restore the original anchor count
    (which includes anchors not lying on a feasible cycle).
    """
    def evaluate(sources, transfer, target):
        support = supported_arcs(transfer, target)
        reduced = {arc: transfer[arc] for arc in support}
        result, minimum_test, minimum = reference(sources, reduced, target)
        minimum_test["anchor_arc_count"] = sum(c <= target // 4 for c in transfer.values())
        return result, minimum_test, minimum
    return evaluate
