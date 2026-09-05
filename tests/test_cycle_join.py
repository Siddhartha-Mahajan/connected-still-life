import importlib.util
from pathlib import Path
import random
import sys

from cycle_join import accelerate, supported_arcs


def reference():
    root = Path(__file__).resolve().parents[1]
    path = root / "src/engines/streaming/certify_n19_supported_streaming.py"
    spec = importlib.util.spec_from_file_location("cycle_reference_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.progress = lambda _: None
    return module.sparse_four_cycle_support


def brute(transfer, target):
    vertices = sorted({v for arc in transfer for v in arc})
    support = set()
    for a in vertices:
        for b in vertices:
            for c in vertices:
                for d in vertices:
                    arcs = ((a,b),(b,c),(c,d),(d,a))
                    if all(arc in transfer for arc in arcs) and sum(transfer[x] for x in arcs) <= target:
                        support.update(arcs)
    return support


def test_random_join_and_full_report():
    rng = random.Random(20260905)
    old = reference()
    fast = accelerate(old)
    for _ in range(180):
        n = rng.randrange(1, 8)
        target = rng.randrange(0, 25)
        transfer = {(a,b): rng.randrange(0, 15) for a in range(n) for b in range(n) if rng.random() < .6}
        assert supported_arcs(transfer, target) == brute(transfer, target)
        assert fast(list(range(n)), transfer, target) == old(list(range(n)), transfer, target)


def test_dense_zero_cost_samples_and_unbalanced_cycle():
    old = reference()
    for transfer, target in [({(a,b):0 for a in range(5) for b in range(5)}, 0),
                             ({(0,1):0,(1,2):0,(2,3):0,(3,0):48},48),
                             ({(0,0):12,(1,1):13},48), ({},48)]:
        assert supported_arcs(transfer,target) == brute(transfer,target)
        assert accelerate(old)([],transfer,target) == old([],transfer,target)
