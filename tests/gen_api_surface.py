#!/usr/bin/env python3
"""Generate tests/fl_api_surface.json, a machine-readable FL Studio MIDI-scripting API surface.

The surface is derived statically (AST only, nothing from the stubs is imported or executed)
from the official FL Studio API stubs package:

    https://github.com/IL-Group/FL-Studio-API-Stubs   (LGPL-3.0-only, unmaintained since 2024-08)

Usage:
    gen_api_surface.py STUBS_DIR [--out PATH] [--midi-py PATH] [--manual-html PATH] [--fl-engine PATH]

    STUBS_DIR       root of a checkout of FL-Studio-API-Stubs (or its src/midi_controller_scripting
                    directory, or a build_lib/midi_controller_scripting directory)
    --out           output file (default: fl_api_surface.json next to this script)
    --midi-py       optional: the real FL Studio Shared/Python/Lib/midi.py. Adds constants.midi_fl_real
                    and a per-name comparison in _meta.midi_vs_real.
    --fl-lib        optional: the real Shared/Python/Lib directory (midi.py + utils.py). Implies --midi-py
                    and adds utils functions that the stubs lack (source "fl_lib").
    --fl-version    optional free-form string recorded in _meta.inputs (e.g. 25.2.3).
    --manual-html   optional: a saved copy of the Image-Line online manual page midi_scripting.htm.
                    Adds per-function manual_* fields and _meta.manual_only / _meta.stub_only lists.
    --fl-engine     optional: FLEngine_x64.dll of a real FL Studio install (a binary is scanned for
                    identifier strings). Adds per-function in_engine (name string present in the
                    binary; necessary, not sufficient, evidence that FL implements it).

Output shape (all optional fields are omitted when their source was not supplied):

    {
      "_meta": {...provenance, warnings, cross-check lists...},
      "<module>": {                       # arrangement channels device general launchMapPages mixer
        "<function>": {                   # patterns playlist plugins screen transport ui utils midi
          "params":   ["name", ...],      # in call order (positional-only, positional, keyword-only)
          "required": <int>,              # params without a default
          "returns":  "type string",
          "param_types": ["int", ...],    # aligned with params ("" when the stub has no annotation)
          "defaults":  {"name": "repr"},  # only params that have a default
          "positional_only": [...],       # only when non-empty
          "keyword_only":    [...],       # only when non-empty
          "varargs": "args" | null,       # *args name (stub uses (*args) for undocumented functions)
          "varkw":   "kwargs" | null,
          "overloads": <int>,             # number of @overload variants that the stub declares
          "since_api": <int|null>,        # from the stub docstring "Included since API version N"
          "deprecated": <bool>,
          "source": "stubs" | "manual" | "fl_lib",   # where the signature came from
          "in_fl_scan_2024": <bool>,      # listed in data/fl_stubs.json (dir() dump of a real FL, 2024-04)
          "in_manual": <bool>, "manual_args": "...", "manual_returns": "...", "manual_version": "...",
          "manual_drift": ["param_count" | "param_names" | "required"],   # stub and manual disagree
          "manual_params": [...], "manual_required": <int>,               # the manual's view (only on drift)
          "in_engine": <bool>,            # identifier string present in the FL engine binary
          "in_fl_lib": <bool>             # utils only: function exists in the real utils.py
        }
      },
      "callbacks": {"OnInit": {...same shape...}},   # script events FL calls (user-defined functions)
      "classes":   {"FlMidiMsg": {"properties": {"status": {"type": "int", "writable": false}}, ...}},
      "constants": {"midi": {"MIDI_NOTEON": 144, ...},   # what the stubs define
                    "midi_fl_real": {...}}               # what the real midi.py defines (prefer this one)
    }

Reading guide for a strict simulator: entries with source "stubs" and no manual_drift are the most reliable.
Where manual_drift is present the stub and the Image-Line manual disagree; the manual is newer (the stubs
stopped at API 36 in 2024-08) but is itself sometimes irregular, so prefer manual_params/manual_required for
functions the stubs are known to lag on. Entries with source "manual" exist only because the stubs lack them
(API 37-45).

The generator uses only the standard library. It is deterministic: same inputs, same bytes.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

# Modules that FL provides natively (built into the FL executable) plus the two Python files that
# ship in Shared/Python/Lib (midi.py, utils.py).
API_MODULES = [
    "arrangement", "channels", "device", "general", "launchMapPages", "mixer",
    "patterns", "playlist", "plugins", "screen", "transport", "ui",
]
PY_LIB_MODULES = ["midi", "utils"]
SPECIAL = {"callbacks", "fl_classes"}

MANUAL_SECTIONS = {
    "Playlist module": "playlist", "Channels module": "channels", "Mixer module": "mixer",
    "Patterns module": "patterns", "Arrangement module": "arrangement",
    "User interface module": "ui", "Transport module": "transport", "Device module": "device",
    "Plugins module": "plugins", "General module": "general",
    "LaunchMapPages module": "launchMapPages", "Script events": "callbacks",
}

warnings: list[str] = []


def warn(msg: str) -> None:
    warnings.append(msg)
    print("warning:", msg, file=sys.stderr)


# --------------------------------------------------------------------------- stub location


def find_pkg_dir(stubs: Path) -> Path:
    for rel in ("src/midi_controller_scripting", "build_lib/midi_controller_scripting", "."):
        p = (stubs / rel).resolve()
        if (p / "channels" / "__init__.py").exists():
            return p
    sys.exit(f"cannot find midi_controller_scripting package under {stubs}")


def git_info(stubs: Path) -> dict:
    root = stubs
    for cand in (stubs, *stubs.parents):
        if (cand / ".git").exists():
            root = cand
            break
    out = {}
    for key, cmd in (
        ("commit", ["git", "rev-parse", "HEAD"]),
        ("commit_date", ["git", "log", "-1", "--format=%cs"]),
        ("describe", ["git", "describe", "--tags", "--always"]),
    ):
        try:
            out[key] = subprocess.check_output(cmd, cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            out[key] = None
    pp = root / "pyproject.toml"
    if pp.exists():
        m = re.search(r'^version\s*=\s*"([^"]+)"', pp.read_text(), re.M)
        out["package_version"] = m.group(1) if m else None
        m = re.search(r'^license\s*=\s*"([^"]+)"', pp.read_text(), re.M)
        out["license"] = m.group(1) if m else None
    return out


# --------------------------------------------------------------------------- AST helpers


class ModuleFile:
    """A parsed stub source file."""

    def __init__(self, path: Path):
        self.path = path
        self.tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        self.funcs: dict[str, list[ast.FunctionDef]] = {}
        self.classes: dict[str, ast.ClassDef] = {}
        self.assigns: dict[str, ast.expr] = {}
        self.imports: dict[str, tuple[int, str, str]] = {}  # local name -> (level, relative module, original name)
        self.all_names: list[str] | None = None
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef):
                self.funcs.setdefault(node.name, []).append(node)
            elif isinstance(node, ast.ClassDef):
                self.classes[node.name] = node
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        if t.id == "__all__":
                            try:
                                self.all_names = list(ast.literal_eval(node.value))
                            except Exception:
                                warn(f"{path}: cannot literal_eval __all__")
                        else:
                            self.assigns[t.id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                self.assigns[node.target.id] = node.value
            elif isinstance(node, ast.ImportFrom) and node.level >= 1 and node.module:
                for a in node.names:
                    self.imports[a.asname or a.name] = (node.level, node.module, a.name)


class Package:
    def __init__(self, root: Path):
        self.root = root
        self._cache: dict[Path, ModuleFile] = {}

    def load(self, p: Path) -> ModuleFile:
        if p not in self._cache:
            self._cache[p] = ModuleFile(p)
        return self._cache[p]

    def resolve_import(self, base: Path, level: int, module: str) -> Path | None:
        d = base.parent
        for _ in range(level - 1):
            d = d.parent
        cand = d / f"{module}.py"
        if cand.exists():
            return cand
        cand = d / module / "__init__.py"
        return cand if cand.exists() else None

    def lookup(self, mf: ModuleFile, name: str, kind: str, _seen=None):
        """Find the defining node for `name` starting in `mf`, following relative re-exports."""
        _seen = _seen or set()
        if (mf.path, name) in _seen:
            return None
        _seen.add((mf.path, name))
        table = {"func": mf.funcs, "class": mf.classes, "const": mf.assigns}[kind]
        if name in table:
            return mf, table[name]
        if name in mf.imports:
            level, mod, orig = mf.imports[name]
            p = self.resolve_import(mf.path, level, mod)
            if p:
                return self.lookup(self.load(p), orig, kind, _seen)
        return None


def ann(node: ast.expr | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()
    return ast.unparse(node)


def is_overload(fn: ast.FunctionDef) -> bool:
    for d in fn.decorator_list:
        n = d.attr if isinstance(d, ast.Attribute) else getattr(d, "id", "")
        if n == "overload":
            return True
    return False


def describe_function(defs: list[ast.FunctionDef]) -> dict:
    impl = [d for d in defs if not is_overload(d)]
    fn = impl[-1] if impl else defs[-1]
    a = fn.args
    pos = list(a.posonlyargs) + list(a.args)
    ndef = len(a.defaults)
    params, ptypes, defaults = [], [], {}
    for i, arg in enumerate(pos):
        params.append(arg.arg)
        ptypes.append(ann(arg.annotation))
        di = i - (len(pos) - ndef)
        if di >= 0:
            defaults[arg.arg] = ast.unparse(a.defaults[di])
    required = len(pos) - ndef
    kwonly = []
    for arg, dflt in zip(a.kwonlyargs, a.kw_defaults):
        params.append(arg.arg)
        ptypes.append(ann(arg.annotation))
        kwonly.append(arg.arg)
        if dflt is None:
            required += 1
        else:
            defaults[arg.arg] = ast.unparse(dflt)
    doc = ast.get_docstring(fn) or ""
    since = None
    m = re.search(r"Included since API version\s*(\d+)", doc, re.I)
    if m:
        since = int(m.group(1))
    out = {
        "params": params,
        "required": required,
        "returns": ann(fn.returns) or "None",
        "param_types": ptypes,
        "defaults": defaults,
    }
    if a.posonlyargs:
        out["positional_only"] = [x.arg for x in a.posonlyargs]
    if kwonly:
        out["keyword_only"] = kwonly
    out["varargs"] = a.vararg.arg if a.vararg else None
    out["varkw"] = a.kwarg.arg if a.kwarg else None
    out["overloads"] = sum(1 for d in defs if is_overload(d))
    out["since_api"] = since
    out["deprecated"] = bool(re.search(r"deprecated", doc, re.I))
    return out


# --------------------------------------------------------------------------- constants


class Unevaluable(Exception):
    pass


def eval_const(node: ast.expr, env: dict):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise Unevaluable(node.id)
    if isinstance(node, ast.UnaryOp):
        v = eval_const(node.operand, env)
        return {ast.USub: lambda x: -x, ast.UAdd: lambda x: +x, ast.Invert: lambda x: ~x, ast.Not: lambda x: not x}[type(node.op)](v)
    if isinstance(node, ast.BinOp):
        l, r = eval_const(node.left, env), eval_const(node.right, env)
        ops = {
            ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
            ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
            ast.LShift: lambda a, b: a << b, ast.RShift: lambda a, b: a >> b,
            ast.BitOr: lambda a, b: a | b, ast.BitAnd: lambda a, b: a & b, ast.BitXor: lambda a, b: a ^ b,
            ast.Pow: lambda a, b: a ** b,
        }
        return ops[type(node.op)](l, r)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [eval_const(e, env) for e in node.elts]
    raise Unevaluable(ast.dump(node)[:60])


def module_constants(pkg: Package, mod_dir: Path) -> dict[str, object]:
    """All constants reachable from a module's public names (recursively following re-exports)."""
    init = pkg.load(mod_dir / "__init__.py")
    names = list(init.all_names or [])
    # Names imported into __init__ but absent from __all__ are still importable from the module.
    for n in init.imports:
        if n not in names:
            names.append(n)
    for n in init.assigns:
        if n not in names and not n.startswith("_"):
            names.append(n)
    result: dict[str, object] = {}

    def value_of(mf: ModuleFile, name: str, stack=()):
        found = pkg.lookup(mf, name, "const")
        if not found:
            raise Unevaluable(name)
        owner, node = found
        if (owner.path, name) in stack:
            raise Unevaluable("cycle " + name)
        env = _EnvProxy(lambda n: value_of(owner, n, stack + ((owner.path, name),)))
        return eval_const(node, env)

    for n in names:
        if pkg.lookup(init, n, "func") or pkg.lookup(init, n, "class"):
            continue
        if not pkg.lookup(init, n, "const"):
            continue
        try:
            v = value_of(init, n)
        except (Unevaluable, KeyError, TypeError, ZeroDivisionError):
            warn(f"{mod_dir.name}.{n}: constant is not statically evaluable; omitted")
            continue
        if isinstance(v, (int, float, str, bool, list)) or v is None:
            result[n] = v
    return result


class _EnvProxy(dict):
    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def __contains__(self, k):
        try:
            self._fn(k)
            return True
        except Unevaluable:
            return False

    def __getitem__(self, k):
        return self._fn(k)


# --------------------------------------------------------------------------- functions per module


def module_functions(pkg: Package, mod_dir: Path) -> dict[str, dict]:
    init = pkg.load(mod_dir / "__init__.py")
    exported = list(init.all_names) if init.all_names is not None else None
    candidates = list(exported) if exported is not None else []
    for n in list(init.imports) + list(init.funcs):
        if n not in candidates and not n.startswith("_"):
            candidates.append(n)
    out: dict[str, dict] = {}
    for n in sorted(candidates):
        found = pkg.lookup(init, n, "func")
        if found:
            out[n] = describe_function(found[1])
    if exported is not None:
        defined_not_exported = sorted(
            n for n in list(init.imports) + list(init.funcs)
            if n in out and n not in exported
        )
        if defined_not_exported:
            warn(f"{mod_dir.name}: defined/imported but not in __all__: {defined_not_exported}")
        missing = [n for n in exported if n not in out and not pkg.lookup(init, n, "const") and not pkg.lookup(init, n, "class")]
        if missing:
            warn(f"{mod_dir.name}: __all__ names with no definition: {missing}")
    return out


def class_properties(pkg: Package, mod_dir: Path, wanted: list[str] | None = None) -> dict:
    init = pkg.load(mod_dir / "__init__.py")
    out = {}
    for cname, cnode in init.classes.items():
        if wanted and cname not in wanted:
            continue
        props: dict[str, dict] = {}
        methods: dict[str, dict] = {}
        for item in cnode.body:
            if isinstance(item, ast.FunctionDef):
                decos = {getattr(d, "id", getattr(d, "attr", "")) for d in item.decorator_list}
                setter = [d for d in item.decorator_list if isinstance(d, ast.Attribute) and d.attr == "setter"]
                if "property" in decos:
                    props[item.name] = {"type": ann(item.returns), "writable": False}
                elif setter:
                    props.setdefault(item.name, {"type": "", "writable": True})["writable"] = True
                elif not item.name.startswith("_") or item.name == "__init__":
                    methods[item.name] = describe_function([item])
        out[cname] = {
            "bases": [ast.unparse(b) for b in cnode.bases],
            "properties": dict(sorted(props.items())),
            "methods": dict(sorted(methods.items())),
        }
    return out


# --------------------------------------------------------------------------- optional cross-checks


class _ManualParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section = None
        self.in_h = None
        self.htext = ""
        self.tables: list[dict] = []
        self.cur = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "h4"):
            self.in_h, self.htext = tag, ""
        elif tag == "table":
            self.cur = {"section": self.section, "rows": []}
        elif tag == "tr" and self.cur is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = ""
        elif tag == "br" and self.cell is not None:
            self.cell += "\n"

    def handle_endtag(self, tag):
        if tag == self.in_h:
            self.section, self.in_h = re.sub(r"\s+", " ", self.htext).strip(), None
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(re.sub(r"\s+", " ", self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.cur["rows"].append(self.row)
            self.row = None
        elif tag == "table" and self.cur is not None:
            self.tables.append(self.cur)
            self.cur = None

    def handle_data(self, d):
        if self.in_h:
            self.htext += d
        if self.cell is not None:
            self.cell += d


def parse_manual(path: Path) -> dict[str, dict[str, dict]]:
    p = _ManualParser()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    out: dict[str, dict[str, dict]] = {}
    for t in p.tables:
        mod = MANUAL_SECTIONS.get(t["section"])
        if not mod:
            continue
        for r in t["rows"][1:]:
            if mod == "callbacks":
                if len(r) < 4 or not re.match(r"^On\w+$", r[0]):
                    continue
                out.setdefault(mod, {})[r[0]] = {"args": r[1], "returns": "", "version": r[-1]}
            else:
                if len(r) < 4 or not re.match(r"^[A-Za-z_]\w*$", r[0]):
                    continue
                # A few manual rows omit the Documentation or the Version cell (4 cells instead of 5).
                version = r[-1] if len(r) >= 5 or re.fullmatch(r"[\d,\s*]+", r[-1]) else ""
                out.setdefault(mod, {})[r[0]] = {"args": r[1], "returns": r[2], "version": version}
    return out


def parse_manual_args(text: str):
    """Parse an Image-Line manual argument cell such as "int index, (bool useGlobalIndex* = False)".

    Returns (params, required, types, defaults) or None when the cell is not in the expected shape.
    Parenthesised items are optional; a trailing * marks a footnote (API version of that parameter).
    """
    text = text.strip()
    if text in ("", "-", "None"):
        return [], 0, [], {}
    def split_top(t: str) -> list[str]:
        out, depth, cur = [], 0, ""
        for ch in t:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            if ch == "," and depth == 0:
                out.append(cur)
                cur = ""
            else:
                cur += ch
        out.append(cur)
        return out

    parts = []
    for raw in split_top(text):
        raw = raw.strip()
        inner = raw.rstrip("*").strip()
        if inner.startswith("(") and inner.endswith(")") and len(split_top(inner[1:-1])) > 1:
            parts.extend("(" + x.strip() + ")" for x in split_top(inner[1:-1]))  # "(int a, int b)": all optional
        else:
            parts.append(raw)
    params, types, defaults, required = [], [], {}, 0
    for part in parts:
        part = part.strip()
        optional = part.startswith("(")
        part = part.replace("*", "").strip().strip("()").strip()
        if not part:
            return None
        default = None
        if "=" in part:
            part, default = (x.strip() for x in part.split("=", 1))
            optional = True
        toks = part.replace(":", " ").split()  # tolerate "newValue: bool"
        if not toks or not all(re.fullmatch(r"[A-Za-z_][\w/]*", t) for t in toks):
            return None
        if len(toks) == 1:
            if toks[0] == "eventData":
                name, typ = "eventData", "eventData"
            elif toks[0] in MANUAL_TYPE_WORDS:
                return None  # a bare type with no parameter name; cannot compare
            else:
                name, typ = toks[0], ""
        elif toks[-1] in MANUAL_TYPE_WORDS and toks[0] not in MANUAL_TYPE_WORDS:
            name, typ = toks[0], toks[-1]  # irregular manual row "index int"
        else:
            name, typ = toks[-1], " ".join(toks[:-1])
        params.append(name)
        types.append(typ)
        if optional:
            defaults[name] = default if default is not None else ""
        else:
            required += 1
    return params, required, types, defaults


MANUAL_TYPE_WORDS = {"int", "bool", "float", "string", "str", "eventData"}
MANUAL_TYPE_MAP = {"-": "None", "": "None", "string": "str", "int/float": "int | float", "float/int": "int | float"}


def manual_only_entry(mrow: dict, engine: set[str] | None, name: str) -> dict:
    parsed = parse_manual_args(mrow["args"])
    ver = [int(x) for x in re.findall(r"\d+", mrow["version"])]
    ret = MANUAL_TYPE_MAP.get(mrow["returns"].strip(), mrow["returns"].strip() or "None")
    entry = {"source": "manual", "in_manual": True}
    if parsed is None:
        entry.update({"params": [], "required": 0, "returns": ret, "manual_args": mrow["args"], "unparsed_manual_args": True})
    else:
        params, required, types, defaults = parsed
        entry.update({
            "params": params, "required": required, "returns": ret,
            "param_types": types, "defaults": defaults,
            "varargs": None, "varkw": None, "overloads": 0,
            "since_api": ver[0] if ver else None, "deprecated": False,
            "manual_args": mrow["args"], "manual_returns": mrow["returns"], "manual_version": mrow["version"],
        })
    if engine is not None:
        entry["in_engine"] = name in engine
    return entry


def engine_names(path: Path) -> set[str]:
    """Identifier-shaped C strings (ASCII, and UTF-16LE for the event names) found in a binary."""
    data = path.read_bytes()
    names = {m.decode() for m in re.findall(rb"[A-Za-z_][A-Za-z0-9_]{1,63}(?=\x00)", data)}
    names |= {m.decode("utf-16-le") for m in re.findall(rb"(?:[A-Za-z_]\x00(?:[A-Za-z0-9_]\x00){1,63})(?=\x00\x00)", data)}
    return names


import hashlib


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def real_utils_functions(path: Path) -> dict[str, dict]:
    """Function signatures from the real Shared/Python/Lib/utils.py (never executed)."""
    out = {}
    for node in ast.parse(path.read_text(encoding="utf-8", errors="replace")).body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            d = describe_function([node])
            d["source"] = "fl_lib"
            d["returns"] = d["returns"] if node.returns else "unknown"
            out[node.name] = d
    return out


def real_midi_constants(path: Path) -> dict[str, object]:
    """Statically evaluate the constants in the real midi.py (never executes it)."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    env: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                env[node.targets[0].id] = eval_const(node.value, env)
            except (Unevaluable, KeyError, TypeError, ZeroDivisionError):
                warn(f"real midi.py: {node.targets[0].id} is not statically evaluable")
    return {k: v for k, v in env.items() if isinstance(v, (int, float, str, list)) or v is None}


# --------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stubs")
    ap.add_argument("--out", default=str(Path(__file__).with_name("fl_api_surface.json")))
    ap.add_argument("--midi-py")
    ap.add_argument("--fl-lib", help="Shared/Python/Lib of a real FL install (midi.py and utils.py); implies --midi-py")
    ap.add_argument("--fl-version", help="free-form FL Studio version string to record in _meta (e.g. 25.2.3)")
    ap.add_argument("--manual-html")
    ap.add_argument("--fl-engine")
    args = ap.parse_args()
    if args.fl_lib and not args.midi_py:
        args.midi_py = str(Path(args.fl_lib) / "midi.py")

    stubs = Path(args.stubs)
    pkg = Package(find_pkg_dir(stubs))
    surface: dict[str, object] = {}
    meta: dict[str, object] = {
        "generator": "tests/gen_api_surface.py",
        "stubs_source": "https://github.com/IL-Group/FL-Studio-API-Stubs",
        "stubs": git_info(stubs),
        "notes": [
            "Signatures come from the official stubs, which were last updated 2024-08 (stub API <= 36). "
            "They can lag real FL Studio; see manual_* / in_manual / in_engine cross-checks when present.",
            "No documentation text is copied; only names, parameter lists, annotations and API-version numbers.",
        ],
    }

    fl_scan_path = None
    for cand in (stubs, *stubs.parents):
        if (cand / "data" / "fl_stubs.json").exists():
            fl_scan_path = cand / "data" / "fl_stubs.json"
            break
    fl_scan = json.loads(fl_scan_path.read_text()) if fl_scan_path else None
    manual = parse_manual(Path(args.manual_html)) if args.manual_html else None
    engine = engine_names(Path(args.fl_engine)) if args.fl_engine else None

    all_dirs = sorted(d for d in pkg.root.iterdir() if d.is_dir() and (d / "__init__.py").exists())
    discovered = {d.name for d in all_dirs}
    unknown = discovered - set(API_MODULES) - set(PY_LIB_MODULES) - SPECIAL
    if unknown:
        warn(f"stub modules not classified by the generator: {sorted(unknown)}")

    for name in API_MODULES + PY_LIB_MODULES:
        d = pkg.root / name
        if not d.exists():
            warn(f"module {name} missing from stubs")
            continue
        fns = module_functions(pkg, d)
        for fname, info in fns.items():
            if fl_scan is not None and name in fl_scan:
                info["in_fl_scan_2024"] = fname in fl_scan[name]
            info["source"] = "stubs"
            if manual is not None and name in API_MODULES:
                mrow = manual.get(name, {}).get(fname)
                info["in_manual"] = mrow is not None
                if mrow:
                    info["manual_args"] = mrow["args"]
                    info["manual_returns"] = mrow["returns"]
                    info["manual_version"] = mrow["version"]
                    parsed = parse_manual_args(mrow["args"])
                    if parsed is not None:
                        mp, mreq, _mt, mdef = parsed
                        drift = []
                        if len(mp) != len(info["params"]):
                            drift.append("param_count")
                        elif mp != info["params"] and not info.get("varargs"):
                            drift.append("param_names")
                        if mreq != info["required"] and not info.get("varargs"):
                            drift.append("required")
                        if drift:
                            info["manual_drift"] = drift
                            info["manual_params"] = mp
                            info["manual_required"] = mreq
            if engine is not None and name in API_MODULES:
                info["in_engine"] = fname in engine
        if manual is not None and name in API_MODULES:
            for fname, mrow in manual.get(name, {}).items():
                if fname not in fns:
                    fns[fname] = manual_only_entry(mrow, engine, fname)
        surface[name] = dict(sorted(fns.items()))

    if args.fl_lib and (Path(args.fl_lib) / "utils.py").exists() and "utils" in surface:
        real_utils = real_utils_functions(Path(args.fl_lib) / "utils.py")
        for fname, info in surface["utils"].items():
            info["in_fl_lib"] = fname in real_utils
        for fname, info in real_utils.items():
            if fname not in surface["utils"]:
                info["in_fl_lib"] = True
                surface["utils"][fname] = info
        surface["utils"] = dict(sorted(surface["utils"].items()))

    surface["callbacks"] = module_functions(pkg, pkg.root / "callbacks") if (pkg.root / "callbacks").exists() else {}
    for info in surface["callbacks"].values():
        info["source"] = "stubs"
    if manual is not None:
        for fname, info in surface["callbacks"].items():
            mrow = manual.get("callbacks", {}).get(fname)
            info["in_manual"] = mrow is not None
            info["source"] = "stubs"
            if engine is not None:
                info["in_engine"] = fname in engine
            if mrow:
                info["manual_version"] = mrow["version"]
                info["manual_args"] = mrow["args"]
                parsed = parse_manual_args(mrow["args"])
                if parsed is not None and len(parsed[0]) != len(info["params"]):
                    info["manual_drift"] = ["param_count"]
                    info["manual_params"] = parsed[0]
                    info["manual_required"] = parsed[1]
    surface["classes"] = {}
    if (pkg.root / "fl_classes").exists():
        surface["classes"].update(class_properties(pkg, pkg.root / "fl_classes"))
    if (pkg.root / "utils").exists():
        surface["classes"].update(class_properties(pkg, pkg.root / "utils"))

    constants: dict[str, dict] = {}
    for name in API_MODULES + PY_LIB_MODULES:
        d = pkg.root / name
        if d.exists():
            c = module_constants(pkg, d)
            if c:
                constants[name] = dict(sorted(c.items()))
    if args.midi_py:
        real = real_midi_constants(Path(args.midi_py))
        constants["midi_fl_real"] = dict(sorted(real.items()))
        stub_midi = constants.get("midi", {})
        meta["midi_vs_real"] = {
            "real_only": sorted(set(real) - set(stub_midi)),
            "stub_only": sorted(set(stub_midi) - set(real)),
            "value_mismatch": sorted(k for k in set(real) & set(stub_midi) if real[k] != stub_midi[k]),
        }
    surface["constants"] = constants

    if manual is not None:
        meta["manual_only"] = {}
        meta["stub_only"] = {}
        for mod in MANUAL_SECTIONS.values():
            mset = set(manual.get(mod, {}))
            sset = {n for n, f in surface.get(mod, {}).items() if f.get("source", "stubs") == "stubs"}
            if mod == "callbacks":
                pass
            if mset - sset:
                meta["manual_only"][mod] = sorted(mset - sset)
            if sset - mset and mod != "callbacks":
                meta["stub_only"][mod] = sorted(sset - mset)
        meta["manual_only"] = dict(sorted(meta["manual_only"].items()))
        meta["stub_only"] = dict(sorted(meta["stub_only"].items()))
    if fl_scan is not None:
        meta["fl_scan_2024_only"] = {
            m: sorted(set(fl_scan[m]) - set(surface.get(m, {})))
            for m in sorted(fl_scan)
            if set(fl_scan[m]) - set(surface.get(m, {}))
        }
    since = [
        f["since_api"] for m in API_MODULES for f in surface.get(m, {}).values()
        if f.get("since_api") is not None and f.get("source") == "stubs"
    ]
    meta["api_versions"] = {"stubs_max_since_api": max(since) if since else None}
    if manual is not None:
        mv = [int(x) for m in manual.values() for row in m.values() for x in re.findall(r"\d+", row["version"])]
        meta["api_versions"]["manual_max_version"] = max(mv) if mv else None
    inputs: dict[str, object] = {"fl_version": args.fl_version}
    if args.midi_py:
        inputs["midi_py"] = {"file": Path(args.midi_py).name, "sha256": sha256_of(Path(args.midi_py))}
    if args.manual_html:
        inputs["manual_html"] = {"file": Path(args.manual_html).name, "sha256": sha256_of(Path(args.manual_html))}
    if args.fl_engine:
        inputs["fl_engine"] = {"file": Path(args.fl_engine).name, "sha256": sha256_of(Path(args.fl_engine))}
    if fl_scan_path:
        inputs["fl_scan_2024"] = {"file": "data/fl_stubs.json", "sha256": sha256_of(fl_scan_path)}
    meta["inputs"] = inputs
    meta["counts"] = {m: len(surface[m]) for m in API_MODULES + PY_LIB_MODULES + ["callbacks"] if m in surface}
    meta["counts"]["constants_midi"] = len(constants.get("midi", {}))
    meta["warnings"] = sorted(warnings)

    ordered = {"_meta": meta}
    ordered.update(surface)
    Path(args.out).write_text(json.dumps(ordered, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: " + ", ".join(f"{k}={v}" for k, v in meta["counts"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
