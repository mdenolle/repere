"""Scorers for the STA/LTA golden suite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
import json
import re

from .sandbox import extract_code, run_snippet


def _parse_iso(s: str) -> datetime | None:
    """Parse ISO-8601 string, tolerating trailing Z and missing timezone."""
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def make_json_extraction_scorer(
    *,
    required_fields: list[str],
    field_tolerances: dict[str, float] | None = None,
) -> Callable[[str, Any], float]:
    """Score JSON output by required-field matches against a gold dict."""
    tolerances = field_tolerances or {}

    def scorer(model_output: str, gold: dict) -> float:
        text = model_output.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return 0.0
        try:
            got = json.loads(m.group(0))
        except json.JSONDecodeError:
            return 0.0
        if not isinstance(got, dict):
            return 0.0

        hits = 0
        for field in required_fields:
            if field not in got or field not in gold:
                continue
            g, v = gold[field], got[field]
            if isinstance(g, str) and _parse_iso(g) is not None:
                tol = tolerances.get(field, 1.0)
                gt, vt = _parse_iso(g), _parse_iso(str(v))
                if gt and vt and abs((gt - vt).total_seconds()) <= tol:
                    hits += 1
            elif isinstance(g, str) and isinstance(v, str):
                if g.strip().lower() == v.strip().lower():
                    hits += 1
            elif g == v:
                hits += 1
        return hits / len(required_fields) if required_fields else 0.0

    return scorer


def make_code_execution_scorer(
    *,
    required_calls: list[str],
    expected_artifact_keys: list[str],
    artifact_predicates: dict[str, Callable[[Any], bool]] | None = None,
    timeout_s: float = 30.0,
) -> Callable[[str, Any], float]:
    """Score code responses by extraction, static checks, execution, and artifacts."""
    predicates = artifact_predicates or {}

    def scorer(model_output: str, gold: Any) -> float:
        score = 0.0
        code = extract_code(model_output)
        if not code:
            return 0.0
        score += 0.25

        if all(call in code for call in required_calls):
            score += 0.25

        result = run_snippet(code, timeout_s=timeout_s)
        if result.ok:
            score += 0.25
            artifacts_ok = True
            for key in expected_artifact_keys:
                if key not in result.artifacts:
                    artifacts_ok = False
                    break
                pred = predicates.get(key)
                if pred and not pred(result.artifacts[key]):
                    artifacts_ok = False
                    break
            if artifacts_ok and expected_artifact_keys:
                score += 0.25
        return score

    return scorer


def make_plot_ssim_scorer(
    *,
    golden_png_path: str,
    ssim_threshold: float = 0.85,
    timeout_s: float = 60.0,
) -> Callable[[str, Any], float]:
    """Run plotting code and compare the produced PNG to a golden via SSIM."""

    def scorer(model_output: str, gold: Any) -> float:
        code = extract_code(model_output)
        if not code:
            return 0.0
        result = run_snippet(code, timeout_s=timeout_s)
        if not result.ok:
            return 0.0
        pngs = [f for f in result.artifact_files if f.lower().endswith(".png")]
        if not pngs:
            return 0.0
        try:
            from skimage.io import imread
            from skimage.metrics import structural_similarity as ssim
            from skimage.transform import resize
        except ImportError as e:
            raise ImportError(
                "Plot scorer requires scikit-image. Install the plot environment."
            ) from e
        try:
            golden = imread(golden_png_path, as_gray=True)
            candidate = imread(pngs[0], as_gray=True)
            if candidate.shape != golden.shape:
                candidate = resize(candidate, golden.shape, anti_aliasing=True)
            value = float(ssim(golden, candidate, data_range=1.0))
            return max(0.0, min(1.0, value))
        except Exception:
            return 0.0

    return scorer


_RE_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?")
_RE_MAG = re.compile(r"\b[Mm]\s*=?\s*([0-9]+(?:\.[0-9]+)?)\b")


def make_report_scorer(
    *,
    expected_detection: bool,
    origin_time_iso: str | None = None,
    origin_time_tolerance_s: float = 60.0,
    magnitude: float | None = None,
    magnitude_tolerance: float = 0.5,
    forbidden_terms: list[str] | None = None,
    required_terms: list[str] | None = None,
) -> Callable[[str, Any], float]:
    """Score a one-paragraph report against catalog truth."""
    forbidden = [t.lower() for t in (forbidden_terms or [])]
    required = [t.lower() for t in (required_terms or [])]

    def scorer(model_output: str, gold: Any) -> float:
        text_lc = model_output.lower()
        penalty = 0.25 * sum(1 for t in forbidden if t in text_lc)

        if expected_detection:
            score = 0.0
            if any(w in text_lc for w in ("detect", "trigger", "earthquake", "event", "arrival")):
                score += 0.4
            if origin_time_iso is not None:
                gold_dt = _parse_iso(origin_time_iso)
                for claimed_time in _RE_TIME.findall(model_output):
                    claimed_dt = _parse_iso(claimed_time)
                    if (
                        claimed_dt
                        and gold_dt
                        and abs((claimed_dt - gold_dt).total_seconds()) <= origin_time_tolerance_s
                    ):
                        score += 0.3
                        break
            if magnitude is not None:
                for found_mag in _RE_MAG.findall(model_output):
                    if abs(float(found_mag) - magnitude) <= magnitude_tolerance:
                        score += 0.3
                        break
            elif required and all(t in text_lc for t in required):
                score += 0.3
            return max(0.0, min(1.0, score - penalty))

        score = 0.0
        if not any(
            w in text_lc
            for w in ("detected an earthquake", "an event was detected", "a tectonic event")
        ):
            score += 0.5
        if any(t in text_lc for t in required) if required else True:
            score += 0.5
        return max(0.0, min(1.0, score - penalty))

    return scorer
