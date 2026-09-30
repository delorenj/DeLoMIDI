"""Static rules for the script folder under test (FL has only the stdlib and its own API modules; Python 3.12).

Rules come from the project brief: compiles clean with warnings as errors, no dependencies beyond the stdlib and FL's
modules, LF line endings and consistent indentation in the tuned folder, no backup/runtime droppings, the entry
scripts declare `# name=`, and every difference from the stock scripts carries a `# KLT <finding-id>: why` comment."""
from __future__ import annotations

import ast
import difflib
import re
import sys
import tokenize
import warnings

import pytest

from tests.conftest import STOCK_DIR
from tests.flsim.loader import detect_scripts
from tests.flsim.surface import API_MODULES

FL_MODULES = set(API_MODULES) | {"callbacks"}


def py_files(target):
    return sorted(target.path.glob("*.py"))


def local_modules(target):
    return {p.stem for p in py_files(target)}


def test_python_is_the_version_fl_embeds():
    if sys.version_info[:2] != (3, 12):
        pytest.skip("FL 2026 embeds Python 3.12; run with `uv run --python 3.12` (found %s)" % sys.version.split()[0])


def test_every_file_compiles_with_warnings_as_errors(target):
    for p in py_files(target):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            compile(p.read_bytes(), str(p), "exec", dont_inherit=True)


def test_imports_are_stdlib_fl_modules_or_local_files(target):
    allowed = set(sys.stdlib_module_names) | FL_MODULES | local_modules(target)
    bad = []
    for p in py_files(target):
        tree = ast.parse(p.read_bytes(), str(p))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    bad.append("%s: relative import" % p.name)
                names = [node.module or ""]
            for n in names:
                if n.split(".")[0] not in allowed:
                    bad.append("%s imports %s" % (p.name, n))
    assert not bad, bad


def test_no_star_imports(target):
    bad = [p.name for p in py_files(target) if re.search(r"^\s*from\s+\S+\s+import\s+\*", p.read_text(encoding="utf-8"), re.M)]
    assert not bad, bad


def test_tuned_files_use_lf_line_endings(target):
    if target.is_stock:
        pytest.skip("Arturia's stock files are CRLF")
    bad = [p.name for p in py_files(target) if b"\r" in p.read_bytes()]
    assert not bad, bad


def test_indentation_is_consistent_within_each_file(target):
    for p in py_files(target):
        kinds = set()
        with open(p, "rb") as f:
            for tok in tokenize.tokenize(f.readline):
                if tok.type == tokenize.INDENT:
                    s = tok.string
                    assert not (" " in s and "\t" in s), "%s:%d mixes tabs and spaces" % (p.name, tok.start[0])
                    kinds.add("tab" if "\t" in s else "space")
        assert len(kinds) <= 1, "%s indents with both tabs and spaces" % p.name


def test_no_backups_or_runtime_droppings_in_the_folder(target):
    junk = [p.name for p in target.path.iterdir()
            if re.search(r"(\.bak|\.orig|~|\.pid|\.sock|\.log|\.db-wal|\.db-shm|\.pyc|-backup\..*)$", p.name) or
            (p.is_dir() and p.name in ("__pycache__", ".codegraph"))]
    assert not junk, junk


def test_device_scripts_declare_their_name_at_the_top(target):
    entry, fwd = detect_scripts(target.path)
    for p in (entry, fwd):
        head = "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[:6])
        assert re.search(r"^#\s*name\s*=\s*\S", head, re.M), "%s has no `# name=` in its first lines" % p.name


def test_the_forward_script_names_itself_in_receivefrom(target):
    """Guide/FL: a device script that shares another's interpreter names it; the stock header names itself."""
    _, fwd = detect_scripts(target.path)
    assert re.search(r"^#\s*receiveFrom\s*=", fwd.read_text(encoding="utf-8", errors="replace"), re.M)


def test_klt_annotations_name_a_finding_id(target):
    """`# KLT <finding-id>: why` where the id is F-nn (input), O-nn (output), G-nn (guide), R-nn (prior art) or H-name
    (a hardware-dependent switch)."""
    rx = re.compile(r"#\s*KLT\s+((?:[FOGR]-\d{2}|H-[A-Za-z0-9_-]+)(?:\s*,\s*(?:[FOGR]-\d{2}|H-[A-Za-z0-9_-]+))*)\s*:\s*\S")
    bad = []
    for p in py_files(target):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = re.search(r"#\s*KLT\b(?!\w)", line)
            if m and not rx.search(line):
                bad.append("%s:%d %s" % (p.name, i, line.strip()[:70]))
    assert not bad, bad


# ---- every change against the stock scripts must be annotated --------------------------------------------------

RENAMES = {
    "KeyLabmk2Dispatch": "KLTDispatch", "KeyLabmk2Display": "KLTDisplay", "KeyLabmk2Navigation": "KLTNavigation",
    "KeyLabmk2Pages": "KLTPages", "KeyLabmk2Plugin": "KLTPlugin", "KeyLabmk2Process": "KLTProcess",
    "KeyLabmk2Return": "KLTReturn", "KeyLabmk2SeqParam": "KLTSeqParam", "ArturiaCrossKeyboardKLmk2": "KLTCrossKeyboard",
    "ArturiaVCOL": "KLTVCOL", "device_KeyLabmkII": "device_KeyLabmk2Tuned",
}
FILE_PAIRS = {"KLTDispatch.py": "KeyLabmk2Dispatch.py", "KLTDisplay.py": "KeyLabmk2Display.py",
              "KLTNavigation.py": "KeyLabmk2Navigation.py", "KLTPages.py": "KeyLabmk2Pages.py",
              "KLTPlugin.py": "KeyLabmk2Plugin.py", "KLTProcess.py": "KeyLabmk2Process.py",
              "KLTReturn.py": "KeyLabmk2Return.py", "KLTSeqParam.py": "KeyLabmk2SeqParam.py",
              "KLTCrossKeyboard.py": "ArturiaCrossKeyboardKLmk2.py", "KLTVCOL.py": "ArturiaVCOL.py",
              "device_KeyLabmk2Tuned.py": "device_KeyLabmkII.py",
              "device_ForwardCCsPort10KeyLabMk2Tuned.py": "device_Forward CCs Port 10 KEYLAB MKII.py"}
HEADER_LINE = re.compile(r"^\s*#\s*(name|receiveFrom)\s*=")


def _norm(text):
    text = text.replace("\r\n", "\n")
    for a, b in RENAMES.items():
        text = text.replace(a, b)
    return [l.rstrip() for l in text.split("\n")]


def test_every_change_against_the_stock_scripts_carries_a_klt_comment(target):
    """Diff each tuned file against its stock counterpart (module renames and line endings normalised): every changed
    or added hunk must contain, or sit right below, a `# KLT <id>: why` comment."""
    if target.is_stock:
        pytest.skip("comparing the stock folder with itself")
    if not STOCK_DIR.is_dir():
        pytest.skip("stock folder not found: %s" % STOCK_DIR)
    problems = []
    for tuned_name, stock_name in FILE_PAIRS.items():
        t, s = target.path / tuned_name, STOCK_DIR / stock_name
        if not t.exists() or not s.exists():
            continue
        a, b = _norm(s.read_text(encoding="utf-8", errors="replace")), _norm(t.read_text(encoding="utf-8", errors="replace"))
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            new = b[j1:j2]
            if all(not l.strip() or HEADER_LINE.match(l) for l in new) and all(not l.strip() or HEADER_LINE.match(l) for l in a[i1:i2]):
                continue                                              # blank lines / the script's `# name=` header
            window = b[max(0, j1 - 3):j2 + 1]
            if not any(re.search(r"#\s*KLT\s+\S", l) for l in window):
                problems.append("%s:%d-%d changed without a `# KLT <id>: why` comment (%s)" % (
                    tuned_name, j1 + 1, max(j2, j1 + 1), (new[0].strip()[:50] if new else "deleted %d lines" % (i2 - i1))))
    assert not problems, "\n".join(problems[:12])
