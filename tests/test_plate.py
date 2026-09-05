"""The overview must show exactly the populations in the exact prefix."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def test_all_twenty_five_boards_in_plate():
    root=Path(__file__).resolve().parents[1]
    prefix=json.loads((root/"data/bounds.json").read_text())["exact_prefix"]
    svg=ET.parse(root/"docs/optima_1_25.svg").getroot()
    ns="{http://www.w3.org/2000/svg}"
    panels=[g for g in svg.findall(ns+"g") if g.get("transform","").startswith("translate")]
    assert len(panels)==25
    for n,panel in enumerate(panels,1):
        assert panel.find(ns+"text").text==f"n = {n} · C(n) = {prefix[n-1]}"
        assert sum(p.get("d","").count("M") for p in panel.iter(ns+"path"))==prefix[n-1]
