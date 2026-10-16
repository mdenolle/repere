"""The FrugalMind -> Repère rename must not reach codameter's own module names.

`codameter.frugalmind` is an upstream module in a separate, SHA-pinned package.
It is codameter's to rename, not ours. `src/repere_suites/dvv/scorers.py` has
carried a comment saying exactly that since the rename; `scripts/demo_dashboard.py`
had the comment's warning come true anyway, importing `codameter.repere` and
breaking every live dv/v run. The failure was invisible because codameter is an
optional dependency: without it installed, the import fails for the *other*
reason and looks like a missing package.

Hence a guard that needs neither codameter nor a live run.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SEARCH_DIRS = ("src", "scripts", "notebooks", "tests")

# The one true spelling of the upstream module.
UPSTREAM = "codameter.frugalmind"
BAD = re.compile(r"from\s+codameter\s+import\s+repere|codameter\.repere")


def _python_files():
    for d in SEARCH_DIRS:
        for path in (REPO / d).rglob("*.py"):
            if "__pycache__" in path.parts or path.name == Path(__file__).name:
                continue
            yield path


def _code_lines(path: Path):
    """Yield (lineno, line) for code only.

    Comments are excluded deliberately: the fix for this bug *documents* the
    wrong spelling so the next reader understands the warning, and a guard that
    cannot tell a citation from an import would forbid explaining itself.
    """
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        code = line.split("#", 1)[0]
        if code.strip():
            yield i, code


def test_nothing_imports_a_renamed_codameter_module():
    offenders = [
        f"{p.relative_to(REPO)}:{i}"
        for p in _python_files()
        for i, line in _code_lines(p)
        if BAD.search(line)
    ]
    assert not offenders, (
        "codameter's upstream module is `frugalmind`, not `repere`; the rename "
        f"leaked into: {offenders}"
    )


def test_the_two_call_sites_agree_on_the_module_name():
    """Both places that reach into codameter must spell it the same way."""
    scorers = (REPO / "src/repere_suites/dvv/scorers.py").read_text()
    dashboard = (REPO / "scripts/demo_dashboard.py").read_text()
    assert "codameter.frugalmind" in scorers or "from codameter import frugalmind" in scorers
    assert "from codameter import frugalmind" in dashboard


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("codameter") is None,
    reason="codameter not installed (optional, SHA-pinned dv/v backend)",
)
def test_the_installed_package_really_exposes_frugalmind():
    """When codameter *is* installed, confirm the name we import exists."""
    import pkgutil

    import codameter

    names = {m.name for m in pkgutil.iter_modules(codameter.__path__)}
    assert "frugalmind" in names, f"codameter has no frugalmind module; found {sorted(names)}"
    assert "repere" not in names, "codameter now ships `repere` too; update this guard"
