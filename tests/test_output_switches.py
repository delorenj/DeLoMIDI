"""Housekeeping of the output-side KLTConfig switches: none is dead, none is undocumented, none is untested.

The switches of the '--- output side' section of KLTConfig.py must each (1) be used by a script of the folder, (2) be
described in docs/tuned/CHANGES-output.md and (3) be exercised by at least one tests/test_output_*.py (or review-round tests/test_review_fix_*.py) test."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import REPO
from tests.test_output_support import tuned_only  # noqa: F401

DOC = REPO / "docs" / "tuned" / "CHANGES-output.md"


def _output_switches(target):
    text = (target.path / "KLTConfig.py").read_text(encoding="utf-8")
    start = text.index("# ---- output side")
    end = text.index("# ---- input side")
    return re.findall(r"^([A-Z][A-Z0-9_]+)\s*=", text[start:end], re.M)


def test_the_output_section_has_switches(target):
    names = _output_switches(target)
    assert len(names) >= 20 and len(names) == len(set(names))


def test_every_output_switch_is_used_by_the_scripts(target):
    src = "\n".join(p.read_text(encoding="utf-8") for p in target.path.glob("*.py") if p.name != "KLTConfig.py")
    dead = [n for n in _output_switches(target) if not re.search(r"\b%s\b" % n, src)]
    assert dead == [], "switches nothing reads: %s" % dead


def test_every_output_switch_is_documented(target):
    if not DOC.exists():
        pytest.skip("no %s" % DOC)
    doc = DOC.read_text(encoding="utf-8")
    missing = [n for n in _output_switches(target) if n not in doc]
    assert missing == [], "switches missing from CHANGES-output.md: %s" % missing


def test_every_output_switch_is_exercised_by_a_test(target):
    here = Path(__file__).resolve()
    tests = "\n".join(p.read_text(encoding="utf-8") for pattern in ("test_output_*.py", "test_review_fix_*.py")
                      for p in here.parent.glob(pattern) if p != here)
    untested = [n for n in _output_switches(target) if not re.search(r"\b%s\b" % n, tests)]
    assert untested == [], "switches no tests/test_output_*.py test touches: %s" % untested
