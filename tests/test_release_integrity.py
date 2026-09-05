"""Regression checks for evidence failures, not merely saved success flags."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]


def audit_module():
    spec = importlib.util.spec_from_file_location("test_audit_release", ROOT/"scripts/audit_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changed_n22_certificate_breaks_chain(tmp_path):
    shutil.copytree(ROOT/"src", tmp_path/"src")
    shutil.copytree(ROOT/"certificates/exact_closures/n22", tmp_path/"certificates/exact_closures/n22")
    path = tmp_path/"certificates/exact_closures/n22/n22_population252_depth5_support.json"
    path.write_text(path.read_text()+"\n")
    audit = audit_module()
    audit.ROOT = tmp_path
    with pytest.raises(AssertionError, match="preceding certificate hash"):
        audit.n22_check()


def test_false_terminal_exclusion_is_detected(tmp_path):
    shutil.copytree(ROOT/"src", tmp_path/"src")
    shutil.copytree(ROOT/"certificates/exact_closures/n22", tmp_path/"certificates/exact_closures/n22")
    path = tmp_path/"certificates/exact_closures/n22/n22_population252_depth11_zero_slack_support.json"
    record = json.loads(path.read_text())
    # Preserve the asserted success flag but introduce a compatible endpoint.
    rows = record["terminal_identity_certificate"]["endpoint_minima"]
    rows[0][0] = rows[0][1]
    path.write_text(json.dumps(record))
    audit = audit_module()
    audit.ROOT = tmp_path
    with pytest.raises(AssertionError, match="terminal"):
        audit.n22_check()


def test_changed_witness_fails_manifest(tmp_path):
    (tmp_path/"board.json").write_text("changed")
    (tmp_path/"MANIFEST.sha256").write_text("0"*64+"  board.json\n")
    audit = audit_module()
    audit.ROOT = tmp_path
    with pytest.raises(AssertionError, match="manifest"):
        audit.manifest_check()
