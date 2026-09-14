"""RCA runner: records -> Inspect eval -> cost layer -> logged result.

Example (offline self-test, no credentials)::

    python -m frugalmind_suites.rca.run \\
        --ids rca-coding-qc-continuity-001 \\
        --solver scripted:src/frugalmind_suites/rca/seeds/coding/_selftest/good \\
        --model mockllm/model --epochs 3 --out results/rca

Example (live model)::

    python -m frugalmind_suites.rca.run --family coding --tier T2_execution \\
        --model anthropic/claude-haiku-4-5-20251001 --epochs 5 --out results/rca

What gets written to ``<out>/<run_id>/``:

``samples.jsonl``  one line per (record, epoch): score, void flag, stage
                   breakdown, model requested and reported, tokens, dollars,
                   wall-clock, working time, tool-call count, trace pointer.
``summary.json``   run header (model, price map version, sandbox backend,
                   git revision, package versions, flags) and per-record and
                   suite aggregates with a bootstrap CI over records.
``inspect/``       the Inspect ``.json`` log, i.e. the full trace.

Schema: ``rca.result.v0.1`` (documented in DESIGN.md §6).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import PRICES_PATH
from .cost import load_price_map, price_usage, sum_usage

RESULT_SCHEMA = "rca.result.v0.1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bootstrap_ci(
    values: list[float], *, n_boot: int = 2000, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float] | None:
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    means = []
    n = len(values)
    for _ in range(n_boot):
        means.append(sum(rng.choice(values) for _ in range(n)) / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (lo, hi)


def _make_solver(spec: str):
    if spec == "generate":
        return None
    if spec == "do_nothing":
        from .solvers import do_nothing

        return do_nothing()
    if spec.startswith("scripted:"):
        from .solvers import scripted

        return scripted(spec.split(":", 1)[1])
    if spec == "react":
        from frugalmind.agents.solver import frugal_react

        return frugal_react(
            tool_names=["python_session", "record_submit"],
            system_prompt=(
                "You are a scientific data assistant for the OOI Regional Cabled Array. "
                "Use python_session to run code against the files in your working directory. "
                "When done, submit your FINAL SCRIPT (a single fenced python block that calls "
                "record(...) with the requested keys) via record_submit."
            ),
        )
    raise SystemExit(f"unknown --solver {spec!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ids", help="comma-separated record ids")
    ap.add_argument("--family", choices=["coding", "litreview", "sensor"])
    ap.add_argument("--tier", choices=["T1_physics", "T2_execution", "T3_reference", "T4_judgment"])
    ap.add_argument("--split", default="validation", choices=["validation", "test"])
    ap.add_argument("--no-templates", action="store_true", help="exclude status=template records")
    ap.add_argument(
        "--model",
        default="mockllm/model",
        help="Inspect model id, e.g. anthropic/claude-haiku-4-5-20251001",
    )
    ap.add_argument(
        "--solver", default="generate", help="generate | do_nothing | react | scripted:<dir>"
    )
    ap.add_argument("--epochs", type=int, default=1, help="repeats per record")
    ap.add_argument("--pass-threshold", type=float, default=0.9)
    ap.add_argument("--price-map", default=str(PRICES_PATH))
    ap.add_argument("--allow-unverified-prices", action="store_true")
    ap.add_argument(
        "--allow-live-network",
        action="store_true",
        help="record mode: let network=allowlist items reach the live services",
    )
    ap.add_argument("--sandbox", default="host", choices=["host", "docker"])
    ap.add_argument("--out", default="results/rca")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--label", default=None, help="free-text condition label (skill, prompt version, ...)"
    )
    args = ap.parse_args(argv)

    if args.sandbox == "docker":
        os.environ["FM_USE_DOCKER_SANDBOX"] = "1"
    else:
        os.environ.pop("FM_USE_DOCKER_SANDBOX", None)

    from inspect_ai import eval as inspect_eval

    from .inspect_tasks import rca

    run_id = uuid.uuid4().hex[:12]
    out_dir = Path(args.out) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = out_dir / "inspect"

    task_obj = rca(
        ids=args.ids,
        family=args.family,
        tier=args.tier,
        split=args.split,
        include_templates=not args.no_templates,
        allow_live_network=args.allow_live_network,
    )
    solver = _make_solver(args.solver)

    t0 = time.time()
    eval_kwargs: dict[str, Any] = dict(
        model=args.model,
        epochs=args.epochs,
        log_dir=str(log_dir),
        log_format="json",
        display="none",
        fail_on_error=False,
    )
    if solver is not None:
        eval_kwargs["solver"] = solver
    logs = inspect_eval(task_obj, **eval_kwargs)
    wall = time.time() - t0
    log = logs[0]

    price_map = load_price_map(args.price_map)
    judge_model = os.environ.get("FM_RCA_JUDGE_MODEL")

    rows: list[dict[str, Any]] = []
    for s in log.samples or []:
        sc = (s.scores or {}).get("rca_scorer")
        md = dict(sc.metadata or {}) if sc else {}
        usage = dict(s.model_usage or {})
        if judge_model and judge_model in usage and judge_model != args.model:
            usage.pop(
                judge_model
            )  # TODO: exclude by scorer span, not by model id (agent-eval pattern)
        _, totals = sum_usage(usage)
        priced = price_usage(
            totals,
            model_requested=args.model,
            model_reported=getattr(s.output, "model", None) if s.output else None,
            price_map=price_map,
            allow_unverified=args.allow_unverified_prices,
        )
        tu = md.get("tool_use") or {}
        rows.append(
            {
                "schema": RESULT_SCHEMA,
                "run_id": run_id,
                "record_id": str(s.id),
                "epoch": s.epoch,
                "tier": md.get("tier"),
                "record_status": md.get("record_status"),
                "score": float(sc.value) if sc is not None and not md.get("void") else None,
                "void": bool(md.get("void", False)),
                "void_reason": md.get("void_reason"),
                "stages": md.get("stages"),
                "explanation": sc.explanation if sc else None,
                "model_requested": priced.model_requested,
                "model_reported": priced.model_reported,
                "model_unpinned": priced.model_unpinned,
                "price_card": priced.card_id,
                "price_map_version": priced.price_map_version,
                "cost_unverified": priced.cost_unverified,
                "input_tokens": priced.input_tokens,
                "output_tokens": priced.output_tokens,
                "cache_read_tokens": priced.cache_read_tokens,
                "cache_write_tokens": priced.cache_write_tokens,
                "cost_usd": priced.cost_usd,
                "cost_notes": priced.notes,
                "wall_clock_s": s.total_time,
                "working_time_s": s.working_time,
                "n_tool_calls": tu.get("n_tool_calls"),
                "n_tool_errors": tu.get("n_tool_errors"),
                "submitted": tu.get("submitted"),
                "error": str(s.error) if s.error else None,
                "trace": {"log": log.location, "sample_uuid": s.uuid},
            }
        )

    with open(out_dir / "samples.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")

    # Per-record aggregates over epochs (voids excluded), then suite aggregates over records.
    per_record: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = per_record.setdefault(
            r["record_id"],
            {
                "scores": [],
                "costs": [],
                "n_void": 0,
                "tier": r["tier"],
                "status": r["record_status"],
            },
        )
        if r["void"]:
            d["n_void"] += 1
            continue
        d["scores"].append(r["score"])
        if r["cost_usd"] is not None:
            d["costs"].append(r["cost_usd"])
    record_summaries = {}
    for rid, d in per_record.items():
        sc = d["scores"]
        record_summaries[rid] = {
            "tier": d["tier"],
            "status": d["status"],
            "n": len(sc),
            "n_void": d["n_void"],
            "mean": statistics.fmean(sc) if sc else None,
            "sd": statistics.stdev(sc) if len(sc) > 1 else (0.0 if sc else None),
            "min": min(sc) if sc else None,
            "max": max(sc) if sc else None,
            "pass_rate": (sum(1 for x in sc if x >= args.pass_threshold) / len(sc)) if sc else None,
            "all_pass": (all(x >= args.pass_threshold for x in sc)) if sc else None,
            "cost_usd_mean": statistics.fmean(d["costs"]) if d["costs"] else None,
            "cost_usd_total": sum(d["costs"]) if d["costs"] else None,
        }
    record_means = [v["mean"] for v in record_summaries.values() if v["mean"] is not None]
    suite = {
        "n_records": len(record_summaries),
        "n_records_scored": len(record_means),
        "n_samples": len(rows),
        "n_void": sum(1 for r in rows if r["void"]),
        "mean_of_record_means": statistics.fmean(record_means) if record_means else None,
        "bootstrap_ci95_over_records": _bootstrap_ci(record_means, seed=args.seed),
        "consistency_all_pass": (
            sum(1 for v in record_summaries.values() if v["all_pass"]) / len(record_means)
            if record_means
            else None
        ),
        "cost_usd_total": sum(r["cost_usd"] for r in rows if r["cost_usd"] is not None)
        if any(r["cost_usd"] is not None for r in rows)
        else None,
        "any_model_unpinned": any(r["model_unpinned"] for r in rows),
        "any_cost_unverified": any(r["cost_unverified"] for r in rows),
        "includes_templates": any(r["record_status"] == "template" for r in rows),
    }

    try:
        from importlib.metadata import version as _pkgver

        pkgs = {
            p: _pkgver(p) for p in ("inspect_ai", "frugalmind", "obspy", "numpy") if _safe_ver(p)
        }
    except Exception:  # pragma: no cover
        pkgs = {}
    ev = log.eval
    summary = {
        "schema": RESULT_SCHEMA,
        "run_id": run_id,
        "created": _now(),
        "suite": "rca",
        "label": args.label,
        "model_requested": args.model,
        "solver": args.solver,
        "epochs": args.epochs,
        "pass_threshold": args.pass_threshold,
        "price_map": {"path": args.price_map, "version": price_map.version},
        "allow_unverified_prices": args.allow_unverified_prices,
        "allow_live_network": args.allow_live_network,
        "sandbox_backend": args.sandbox,
        "sandbox_image": os.environ.get("FM_SANDBOX_IMAGE"),
        "revision": ev.revision.model_dump() if getattr(ev, "revision", None) else None,
        "packages": {**(getattr(ev, "packages", None) or {}), **pkgs},
        "inspect_status": log.status,
        "wall_clock_total_s": round(wall, 3),
        "records": record_summaries,
        "suite_aggregate": suite,
        "warnings": _warnings(suite),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")

    print(
        f"run {run_id}: {suite['n_samples']} samples, {suite['n_void']} void, "
        f"mean-of-records={suite['mean_of_record_means']}, CI95={suite['bootstrap_ci95_over_records']}, "
        f"cost_usd={suite['cost_usd_total']}"
    )
    for w in summary["warnings"]:
        print(f"  WARNING: {w}")
    print(f"  wrote {out_dir}/summary.json and samples.jsonl; trace: {log.location}")
    return 0 if log.status == "success" else 1


def _safe_ver(pkg: str) -> bool:
    try:
        from importlib.metadata import version

        version(pkg)
        return True
    except Exception:
        return False


def _warnings(suite: dict[str, Any]) -> list[str]:
    w = []
    if suite["includes_templates"]:
        w.append(
            "run includes status=template records; numbers are harness checks, not benchmark results"
        )
    if suite["any_model_unpinned"]:
        w.append(
            "model id is not pinned in the price map (model_unpinned); do not publish on the test split"
        )
    if suite["any_cost_unverified"]:
        w.append("price card unverified; cost figures are provisional")
    if suite["n_void"]:
        w.append(
            f"{suite['n_void']} sample(s) void (harness could not score); excluded from aggregates"
        )
    return w


if __name__ == "__main__":
    sys.exit(main())
