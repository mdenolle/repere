#!/usr/bin/env python3
"""Fetch the external, pinned inputs of the RCA suite into data/external/ (gitignored).

Nothing here is invented: every file is pinned to a commit or a service URL
and to a sha256 computed on 2026-09-14. A hash mismatch aborts, because a
silently different corpus or correction table would change scores.

    python scripts/rca_fetch_external.py            # everything
    python scripts/rca_fetch_external.py chronfix    # one group
    python scripts/rca_fetch_external.py --list

Groups
------
chronfix   coszo-hub/chronfix @ 486f05b, examples/HYS14/{hour_times.npy,
           delta_t_hourly_clean.npy, trigger_periods.csv}: the T1 reference.
           MIT licence (LICENSE in that repo).
arcada     mhemmett/arcada @ 14294bc, catalog/{instruments.json, papers.json,
           pdf-chunks.json, pi-pages.json}: the corpus snapshots for T3 and
           the sensor family. Code is MIT; the data files carry no separate
           licence statement (see docs/rca/prior_art/arcada.md §8) -- TODO
           confirm redistribution terms with the authors before any public
           release of derived records.
mhz        one UTC day (2023-03-15) of OO.HYS14..MHZ and OO.HYS12..MHZ from
           the EarthScope FDSN dataselect service, for the T1 offset item.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src" / "frugalmind_suites" / "rca" / "data" / "external"

GIT_GROUPS = {
    "chronfix": {
        "repo": "https://github.com/coszo-hub/chronfix",
        "commit": "486f05bcdaad26a1855ee90c987c41b7d36b835a",
        "dest": DEST / "chronfix" / "HYS14",
        "files": {
            "examples/HYS14/hour_times.npy": "f8659368764b86c20af6c9573d91280ed6fa32782abc6c96aa016dd9dae6ee3d",
            "examples/HYS14/delta_t_hourly_clean.npy": "cdffb9b52f69a67f3fab1be6bbf7c74a9561e231e8b7be854eda848dc63c751c",
            "examples/HYS14/trigger_periods.csv": "826163757834b4bbcfa66c71ab2903948660288601855cf6925cac06e11580e9",
            "examples/HYS14/delta_t_hourly.csv": "e5e15d61151f60e711e8c60e4ebc628de37580a824480c2ee22670a94b2b550b",
        },
    },
    "arcada": {
        "repo": "https://github.com/mhemmett/arcada",
        "commit": "14294bca45ce5f65fd6541bea68ab40fbc870659",
        "dest": DEST / "arcada",
        "files": {
            "catalog/instruments.json": "f3a6d7fc53f9fb658cfac40e82199317f17b47abb11432ba1e5027ccec9009e0",
            "catalog/papers.json": "3d9f119612aa948c1a619254bbb5e9cd84125735f7bca1d8bd2abc817622f6b1",
            "catalog/pdf-chunks.json": "0ac1bf6f43d49543da7c3050a5474a690e274641edea7493f497b0714970bd3d",
            "catalog/pi-pages.json": "26c724af0dc1b5fddac88244cc2661eb47de75923e08cbbcee1362fcd2bb83d6",
        },
    },
}

URL_GROUPS = {
    "mhz": {
        "dest": DEST / "mhz",
        "files": {
            "OO.HYS14..MHZ.2023-03-15.mseed": (
                "https://service.earthscope.org/fdsnws/dataselect/1/query?net=OO&sta=HYS14&loc=--&cha=MHZ&start=2023-03-15T00:00:00&end=2023-03-16T00:00:00&format=miniseed",
                "19603b8ba18338d83b1caee4b5169be80c09c8485d59382d909527e6e1d72261",
            ),
            "OO.HYS12..MHZ.2023-03-15.mseed": (
                "https://service.earthscope.org/fdsnws/dataselect/1/query?net=OO&sta=HYS12&loc=--&cha=MHZ&start=2023-03-15T00:00:00&end=2023-03-16T00:00:00&format=miniseed",
                "2aeb401fe99c93cd9a1904fd59e4d3580fdb708145d942c114705d1169ce3cab",
            ),
        },
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_git(name: str, spec: dict) -> int:
    dest: Path = spec["dest"]
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout", spec["repo"], tmp],
            check=True,
        )
        subprocess.run(
            ["git", "-C", tmp, "checkout", "--quiet", spec["commit"], "--", *spec["files"]],
            check=True,
        )
        bad = 0
        for rel, want in spec["files"].items():
            src = Path(tmp) / rel
            got = sha256(src)
            if got != want:
                print(f"  HASH MISMATCH {rel}: {got} != {want}")
                bad += 1
                continue
            shutil.copy2(src, dest / Path(rel).name)
            print(f"  ok {rel} -> {dest / Path(rel).name}")
    (dest / "PIN.txt").write_text(f"{spec['repo']}@{spec['commit']}\n")
    return bad


def fetch_urls(name: str, spec: dict) -> int:
    dest: Path = spec["dest"]
    dest.mkdir(parents=True, exist_ok=True)
    bad = 0
    for fname, (url, want) in spec["files"].items():
        target = dest / fname
        print(f"  GET {url}")
        urllib.request.urlretrieve(url, target)  # noqa: S310 - fixed https URL
        got = sha256(target)
        if want.startswith("SHA256_"):
            print(f"  {fname}: sha256 {got} (pin not yet recorded; paste into this script)")
        elif got != want:
            print(f"  HASH MISMATCH {fname}: {got} != {want}")
            bad += 1
        else:
            print(f"  ok {fname}")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("groups", nargs="*", default=[])
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    names = list(GIT_GROUPS) + list(URL_GROUPS)
    if a.list:
        print("\n".join(names))
        return 0
    wanted = a.groups or names
    bad = 0
    for n in wanted:
        print(f"[{n}]")
        if n in GIT_GROUPS:
            bad += fetch_git(n, GIT_GROUPS[n])
        elif n in URL_GROUPS:
            bad += fetch_urls(n, URL_GROUPS[n])
        else:
            print(f"  unknown group {n!r}; known: {names}")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
