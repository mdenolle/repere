"""Inspect substrate for the RCA suite: one ``@task`` and one tier-dispatching ``@scorer``.

Run (mock model, offline)::

    inspect eval src/repere_suites/rca/inspect_tasks.py@rca \\
        -T ids=rca-coding-qc-continuity-001 --model mockllm/model

or through the runner, which adds the cost layer, repeats and the logged
result: ``python -m repere_suites.rca.run --help``.

Isolation rule (ABC T.5): the ``Sample`` handed to the solver carries the
prompt and the *public* part of the record. Reference outputs, reference
citations, checker ``expected`` values and oracle arguments are stripped from
``Sample.metadata`` and live only in the scorer's closure, keyed by sample id.

Void vs fail (ABC T.3): when the harness cannot score a sample for a reason
that is not the agent's fault (network policy not satisfiable, fixture hash
mismatch, oracle has no reference at that hour, judge not calibrated) the
scorer returns value 0.0 with ``metadata.void = True`` and a reason. The
runner excludes voids from every aggregate and reports them separately; a
plain 0.0 without ``void`` is a real failure.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, mean, scorer, std, stderr
from inspect_ai.solver import TaskState, generate

from repere.agents.metrics import tool_use_stats

from . import HERE, PUBLIC_DATA_DIR, load_records, private_data_dir
from .checkers import CheckOutcome, resolve_checker, staged_score

__all__ = ["public_view", "rca", "rca_scorer", "samples_from_records"]


# ---------------------------------------------------------------------------
# Sample construction
# ---------------------------------------------------------------------------


def public_view(rec: dict[str, Any]) -> dict[str, Any]:
    """The record minus everything a solver must not see."""
    v = copy.deepcopy(rec)
    v.pop("_path", None)
    v.pop("reference_output", None)
    v.pop("reference_citations", None)
    scoring = v.get("scoring") or {}
    chk = scoring.get("checker")
    if isinstance(chk, dict):
        chk.pop("args", None)
    orc = scoring.get("oracle")
    if isinstance(orc, dict):
        orc.pop("args", None)
    ref = scoring.get("reference")
    if isinstance(ref, dict):
        ref.pop("required_terms", None)
        ref.pop("forbidden_terms", None)
    return v


def samples_from_records(records: list[dict[str, Any]]) -> MemoryDataset:
    samples = [
        Sample(id=rec["id"], input=rec["prompt"], target="", metadata=public_view(rec))
        for rec in records
    ]
    return MemoryDataset(samples=samples, name="rca")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _void(reason: str, completion: str = "") -> Score:
    return Score(
        value=0.0,
        answer=completion,
        explanation=f"VOID: {reason}",
        metadata={"void": True, "void_reason": reason},
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_input_files(rec: dict[str, Any]) -> dict[str, str] | str:
    """Return ``{basename: host_path}`` or an error string."""
    out: dict[str, str] = {}
    priv = private_data_dir()
    for f in (rec.get("inputs") or {}).get("files") or []:
        rel = f["path"]
        candidates = [PUBLIC_DATA_DIR / rel, HERE / "data" / "external" / rel]
        if priv:
            candidates.append(priv / rel)
        found = next((c for c in candidates if c.is_file()), None)
        if found is None:
            return f"input file not found: {rel}"
        want = f.get("sha256", "TODO")
        if want != "TODO" and _sha256(found) != want:
            return f"sha256 mismatch for {rel}"
        out[Path(rel).name] = str(found)
    return out


_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    m = _JSON_OBJ.search(text or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _network_ok(rec: dict[str, Any], allow_live: bool) -> str | None:
    net = (rec.get("sandbox") or {}).get("network", "none")
    if net == "none":
        return None
    if net == "replay":
        return "network=replay: the replay proxy is not implemented yet (DESIGN.md §5.3); record mode needs --allow-live-network"
    if net == "allowlist" and not allow_live:
        return "network=allowlist requires --allow-live-network (record mode); refusing to score a live run silently"
    return None


async def _execute(rec: dict[str, Any], code: str) -> Any:
    from repere_suites.sta_lta.sandbox import run_snippet

    sb = rec.get("sandbox") or {}
    files = _resolve_input_files(rec)
    if isinstance(files, str):
        raise RuntimeError(files)
    return await asyncio.to_thread(
        run_snippet,
        code,
        timeout_s=float(sb.get("timeout_s", 60)),
        input_files=files or None,
        image=sb.get("image"),
    )


# ---------------------------------------------------------------------------
# Tier scorers
# ---------------------------------------------------------------------------


async def _score_t2(rec: dict[str, Any], state: TaskState, *, allow_live: bool) -> Score:
    from repere_suites.sta_lta.sandbox import extract_code

    completion = state.output.completion if state.output else ""
    reason = _network_ok(rec, allow_live)
    if reason:
        return _void(reason, completion)
    code = extract_code(completion)
    weights = (rec["scoring"].get("checker") or {}).get("stage_weights")
    keys = list((rec.get("task") or {}).get("artifact_keys") or [])
    if not code:
        value, detail = staged_score(
            code_extracted=False,
            ran_ok=False,
            artifacts={},
            artifact_keys=keys,
            outcome=None,
            stage_weights=weights,
        )
        return Score(
            value=value,
            answer=completion,
            explanation="no code block in completion",
            metadata=detail,
        )
    try:
        res = await _execute(rec, code)
    except RuntimeError as exc:
        return _void(str(exc), completion)
    try:
        checker = resolve_checker(rec["scoring"]["checker"])
        outcome: CheckOutcome | None = checker(res, rec["scoring"]["checker"].get("args") or {})
    except Exception as exc:  # checker bugs are harness faults, not agent faults
        return _void(f"checker error: {type(exc).__name__}: {exc}", completion)
    value, detail = staged_score(
        code_extracted=True,
        ran_ok=bool(res.ok),
        artifacts=res.artifacts,
        artifact_keys=keys,
        outcome=outcome,
        stage_weights=weights,
    )
    detail.update(
        {
            "exec_ok": res.ok,
            "timed_out": res.timed_out,
            "returncode": res.returncode,
            "artifacts": res.artifacts,
            "stdout_tail": (res.stdout or "")[-2000:],
            "stderr_tail": (res.stderr or "")[-2000:],
            "checker": outcome.explanation if outcome else None,
            "checker_details": outcome.details if outcome else None,
        }
    )
    return Score(
        value=value,
        answer=completion,
        explanation=outcome.explanation if outcome else "",
        metadata=detail,
    )


async def _score_t1(rec: dict[str, Any], state: TaskState, *, allow_live: bool) -> Score:
    """Oracle comparison. The agent's numbers come either from executing its
    code (shape B, preferred) or from a JSON object in the completion."""
    from repere_suites.sta_lta.sandbox import extract_code

    from .oracles import resolve_oracle

    completion = state.output.completion if state.output else ""
    reason = _network_ok(rec, allow_live)
    if reason:
        return _void(reason, completion)
    spec = rec["scoring"]["oracle"]
    try:
        oracle = resolve_oracle(spec)
        ref = oracle(**(spec.get("args") or {}))
    except FileNotFoundError as exc:
        return _void(f"oracle inputs missing: {exc}", completion)
    except Exception as exc:
        return _void(f"oracle error: {type(exc).__name__}: {exc}", completion)

    keys = list((rec.get("task") or {}).get("artifact_keys") or [])
    got: dict[str, Any] = {}
    exec_meta: dict[str, Any] = {}
    code = extract_code(completion) if rec.get("shape") == "B_tool" else ""
    if code:
        try:
            res = await _execute(rec, code)
        except RuntimeError as exc:
            return _void(str(exc), completion)
        got = dict(res.artifacts or {})
        exec_meta = {"exec_ok": res.ok, "stderr_tail": (res.stderr or "")[-1000:]}
    if not got:
        got = _parse_json_object(completion) or {}

    tol = spec.get("tolerance") or {}
    abs_tol = float(tol.get("abs", 0.0))
    rel_tol = float(tol.get("rel", 0.0))
    per_key: dict[str, Any] = {}
    values: list[float] = []
    for k in keys:
        r = ref.get(k)
        if r is None:
            return _void(f"oracle has no reference for {k!r}: {ref.get('reason', '')}", completion)
        g = got.get(k)
        if g is None:
            per_key[k] = {"got": None, "ref": r, "score": 0.0}
            values.append(0.0)
            continue
        try:
            resid = abs(float(g) - float(r))
        except (TypeError, ValueError):
            per_key[k] = {"got": g, "ref": r, "score": 0.0}
            values.append(0.0)
            continue
        t = max(abs_tol, rel_tol * abs(float(r)))
        # 1.0 inside the tolerance, linear decay to 0 at 4x the tolerance.
        s = 1.0 if resid <= t else max(0.0, 1.0 - (resid - t) / (3.0 * t)) if t > 0 else 0.0
        per_key[k] = {
            "got": float(g),
            "ref": float(r),
            "residual": resid,
            "tolerance": t,
            "score": s,
        }
        values.append(s)
    value = sum(values) / len(values) if values else 0.0
    return Score(
        value=value,
        answer=completion,
        explanation="; ".join(f"{k}: resid={v.get('residual')}" for k, v in per_key.items()),
        metadata={"per_key": per_key, "oracle": spec.get("solver"), **exec_meta},
    )


_ABSTAIN = (
    "no paper",
    "no papers",
    "not in the corpus",
    "none before",
    "cannot find",
    "no publication",
)


async def _score_t3(rec: dict[str, Any], state: TaskState) -> Score:
    from repere_suites.lit_rag.scorers import make_scorer_from_spec

    completion = state.output.completion if state.output else ""
    method = rec["scoring"]["method"]
    refspec = rec["scoring"].get("reference") or {}
    cits = rec.get("reference_citations") or []
    gold = [c["id"] for c in cits if int(c.get("grade", 0)) >= 2]
    negatives = [c["id"] for c in cits if int(c.get("grade", 0)) == 0]
    cited_negatives = [n for n in negatives if n in completion]

    if method == "retrieval_metrics":
        if not gold:
            return _void(
                "reference_citations has no graded-relevant ids (template not filled)", completion
            )
        spec = {
            "name": "retrieval_metrics",
            "config": {
                "metric": refspec.get("metric", "ndcg_at_k"),
                "k": int(refspec.get("k", 10)),
            },
        }
        fn = make_scorer_from_spec(spec)
        value = float(await asyncio.to_thread(fn, completion, gold))
    elif method == "citation_support":
        if not (refspec.get("valid_sources") or gold) and not refspec.get("required_terms"):
            return _void(
                "citation_support has neither valid sources nor required terms (template not filled)",
                completion,
            )
        spec = {
            "name": "citation_support",
            "config": {
                "valid_sources": refspec.get("valid_sources") or gold,
                "required_terms": refspec.get("required_terms") or [],
                "forbidden_terms": refspec.get("forbidden_terms") or [],
            },
        }
        fn = make_scorer_from_spec(spec)
        value = float(await asyncio.to_thread(fn, completion, rec.get("reference_output") or ""))
    elif method == "exact_match":
        cfg = rec["scoring"].get("config") or {}
        if cfg.get("mode") == "abstain":
            low = completion.lower()
            abstained = any(p in low for p in _ABSTAIN)
            value = (
                1.0
                if (abstained and not cited_negatives and not any(g in completion for g in gold))
                else 0.0
            )
        else:
            ref = rec.get("reference_output")
            if ref is None:
                return _void("reference_output is empty (template not filled)", completion)
            norm = lambda s: re.sub(r"\s+", " ", str(s)).strip().lower()  # noqa: E731
            accepted = ref if isinstance(ref, list) else [ref]
            value = 1.0 if any(norm(a) in norm(completion) for a in accepted) else 0.0
    else:
        return _void(f"unknown T3 method {method!r}", completion)
    return Score(
        value=max(0.0, min(1.0, value)),
        answer=completion,
        explanation=method,
        metadata={"cited_negatives": cited_negatives, "n_gold": len(gold)},
    )


async def _score_t4(rec: dict[str, Any], state: TaskState) -> Score:
    completion = state.output.completion if state.output else ""
    judge = rec["scoring"].get("judge") or {}
    if os.environ.get("REPERE_RCA_ENABLE_JUDGE") != "1":
        return _void(
            "T4 judge disabled: judge scores are reportable only after inter-rater agreement and judge calibration (DESIGN.md §4.4)",
            completion,
        )
    if not judge.get("human_ratings_ref") or not judge.get("calibration_set_ref"):
        return _void(
            "T4 judge not calibrated: human_ratings_ref and calibration_set_ref are empty",
            completion,
        )
    return _void("T4 judge path not implemented in the skeleton", completion)


# ---------------------------------------------------------------------------
# Scorer + task
# ---------------------------------------------------------------------------


@scorer(metrics=[mean(), std(), stderr()])
def rca_scorer(records_by_id: dict[str, dict[str, Any]], allow_live_network: bool = False):
    async def score(state: TaskState, target: Target) -> Score:
        rec = records_by_id.get(str(state.sample_id))
        if rec is None:
            return _void(f"no record for sample {state.sample_id!r}")
        tier = rec.get("tier")
        if tier == "T2_execution":
            s = await _score_t2(rec, state, allow_live=allow_live_network)
        elif tier == "T1_physics":
            s = await _score_t1(rec, state, allow_live=allow_live_network)
        elif tier == "T3_reference":
            s = await _score_t3(rec, state)
        elif tier == "T4_judgment":
            s = await _score_t4(rec, state)
        else:
            s = _void(f"unknown tier {tier!r}")
        md = dict(s.metadata or {})
        md["tool_use"] = tool_use_stats(state)
        md["tier"] = tier
        md["record_status"] = rec.get("status")
        return Score(value=s.value, answer=s.answer, explanation=s.explanation, metadata=md)

    return score


def _split_ids(ids: str | list[str] | None) -> list[str] | None:
    if ids is None or ids == "":
        return None
    if isinstance(ids, str):
        return [x.strip() for x in ids.split(",") if x.strip()]
    return list(ids)


@task
def rca(
    ids: str | None = None,
    family: str | None = None,
    tier: str | None = None,
    split: str = "validation",
    include_templates: bool = True,
    allow_live_network: bool = False,
) -> Task:
    """The RCA suite (or a filtered subset) as one Inspect task."""
    records = load_records(
        ids=_split_ids(ids),
        family=family,
        tier=tier,
        split=split,
        include_templates=include_templates,
    )
    if not records:
        raise ValueError("no RCA records matched the filter")
    by_id = {r["id"]: r for r in records}
    return Task(
        dataset=samples_from_records(records),
        solver=generate(),
        scorer=rca_scorer(by_id, allow_live_network=allow_live_network),
        name="rca",
        metadata={
            "suite": "rca",
            "record_ids": sorted(by_id),
            "n_templates": sum(1 for r in records if r.get("status") == "template"),
            "split": split,
        },
    )
