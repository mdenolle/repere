"""Pull the hidden evaluation splits from the gated Hugging Face dataset.

Why this exists
---------------
FrugalMind ships a PUBLIC `validation` split in-repo so anyone can develop
against the benchmark and reproduce the demo board on a laptop. The `test`
split — the answers a *ranked* score is computed from — is deliberately NOT in
git. A benchmark whose answers are public measures memorisation, not capability.

The hidden split lives in a **gated** HF dataset. Access is granted to people
(and to the scoring service), not to model developers by default.

Usage
-----
    huggingface-cli login          # or export HF_TOKEN=hf_...
    pixi run -e full python scripts/pull_eval_data.py

Files land in ``$FM_EVAL_DATA_DIR`` (default ``data/private/``), which is
gitignored. The suites pick them up automatically.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRIVATE_DIR = Path(os.environ.get("FM_EVAL_DATA_DIR", REPO / "data" / "private"))

# The gated dataset. Override for a fork / a different lab.
HF_REPO = os.environ.get("FM_HF_DATASET", "gaia-hazlab/frugalmind-hidden")

# Files the hidden dataset is expected to provide. Add one line per suite whose
# test split is hidden.
HIDDEN_FILES = [
    "synthetic_stalta_test.yaml",
    "lit_rag_ooi_rca_test.yaml",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=HF_REPO, help=f"HF dataset repo (default {HF_REPO})")
    ap.add_argument("--out", default=str(PRIVATE_DIR), help="destination dir")
    ap.add_argument(
        "--check",
        action="store_true",
        help="only report whether the hidden split is already present locally",
    )
    args = ap.parse_args()

    out = Path(args.out)

    if args.check:
        missing = [f for f in HIDDEN_FILES if not (out / f).exists()]
        if missing:
            print(f"hidden split NOT present in {out}: missing {missing}")
            return 1
        print(f"hidden split present in {out}: {HIDDEN_FILES}")
        return 0

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            "error: huggingface_hub is not installed.\n"
            "       pip install huggingface_hub    (or add it to the [eval] extra)",
            file=sys.stderr,
        )
        return 2

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    out.mkdir(parents=True, exist_ok=True)

    for name in HIDDEN_FILES:
        try:
            path = hf_hub_download(
                repo_id=args.repo,
                filename=name,
                repo_type="dataset",
                token=token,
                local_dir=str(out),
            )
        except Exception as exc:  # noqa: BLE001 — surface the real cause
            print(
                f"error: could not fetch {name!r} from {args.repo!r}: {exc}\n\n"
                "  This dataset is GATED. You need to:\n"
                "    1. request access on the HF dataset page, and\n"
                "    2. `huggingface-cli login` (or export HF_TOKEN=hf_...).\n"
                "  Without it you can still develop against the public "
                "`validation` split — only ranked scores need the hidden one.",
                file=sys.stderr,
            )
            return 1
        print(f"pulled {name} -> {path}")

    print(f"\nhidden split ready in {out} (gitignored). Suites will pick it up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
