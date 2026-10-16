"""The outbound guard: what may leave the private host for the public board.

``tests/test_no_holdout_in_repo.py`` guards the repository against held-out data
going *in*. This module guards the board against held-out data going *out*, and
it exists because the threat model changed: runs now happen on a GPU host behind
a VPN that pushes to git directly. An automated push with no check is how a gold
answer reaches a public page, and it only has to happen once.

Three rules, in the order they matter.

**1. A row may carry only allowlisted fields.** Not "everything except the
dangerous ones" — a denylist fails open the moment someone adds a field. Add a
field to the board and this module has to be edited, on purpose, in the same
commit.

**2. No free text leaves.** Every published value is a number, a boolean, a null,
or a string from a closed vocabulary (model id, suite id, phase). Scorer
explanations, prompts, completions, claim text and source passages are where the
answers live, and none of them is representable in a published row.

**3. The test split publishes aggregates only.** Per-item scores on the hidden
split are an oracle in slow motion: publish them run after run and a reader
reconstructs which held-out items each model passes. Validation items may be
reported per item; test items may not.

The guard raises rather than filtering. Silently dropping a field would let a
caller believe it published something it did not, and a benchmark that quietly
edits its own output is worse than one that stops.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = [
    "PUBLISHABLE_ROW_FIELDS",
    "PublishError",
    "check_payload",
    "write_board",
]


class PublishError(RuntimeError):
    """Raised when a payload is not safe to publish. Never caught internally."""


# Every field a public board row may carry. Adding a board field means adding it
# here deliberately, which is the point.
PUBLISHABLE_ROW_FIELDS = frozenset(
    {
        # identity and provenance
        "rank",
        "model_id",
        "agent_condition",
        "suite",
        "category",
        "run_file",
        "openness",
        "toolset",
        "skill_name",
        "skill_version",
        "host_id",
        "phase",
        "perturbation_seed",
        "fault_rate",
        "model_pinned",
        # quality
        "score_mean",
        "score_ci95",
        "score_runs",
        "n_epochs",
        "n_completed",
        "n_total",
        # cost
        "cost_usd",
        "scoring_cost_usd",
        "in_tokens",
        "out_tokens",
        "total_tokens",
        "latency_s_mean",
        "latency_s_ci95",
        "n_tool_calls",
        "n_agent_steps",
        # frontier and reliability
        "on_frontier_cost",
        "on_frontier_tokens",
        "reliability",
    }
)

# Values that are strings must look like identifiers, not prose. A scorer
# explanation or a model completion fails this; "claude-haiku-4-5-20251001",
# "synthetic_stalta" and "stalta-detection+skill-v0.3" pass.
_IDENTIFIER = re.compile(r"^[\w.:@+/-]{0,120}$")

# Fields allowed to hold a free-form string, because they are human labels.
_PROSE_ALLOWED = frozenset({"run_file"})

# Substrings that should never appear anywhere in a published payload. Cheap,
# blunt, and aimed at the specific artefacts that carry gold.
_FORBIDDEN_SUBSTRINGS = (
    "expected_detection",
    "stalta_params",
    "trigger_onset_utc",
    "expected_tools",
    "required_cli_args",
    "expected_files",
    "reference_output",
    "SECRET_SEED",
    "BEGIN PRIVATE KEY",
)


def _check_scalar(field: str, value: Any, *, where: str) -> None:
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if field in _PROSE_ALLOWED:
            if len(value) > 200:
                raise PublishError(f"{where}: {field!r} is too long to be a label")
            return
        if not _IDENTIFIER.match(value):
            raise PublishError(
                f"{where}: {field!r} holds free text, which may not be published: {value[:60]!r}"
            )
        return
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, (bool, int, float, type(None))):
                raise PublishError(f"{where}: {field!r} is a list containing a non-numeric value")
        return
    if isinstance(value, dict):
        for key, sub in value.items():
            _check_scalar(str(key), sub, where=f"{where}.{field}")
        return
    raise PublishError(f"{where}: {field!r} has unpublishable type {type(value).__name__}")


def check_payload(payload: dict[str, Any]) -> list[str]:
    """Raise :class:`PublishError` on anything unsafe; return advisory warnings.

    Warnings are things a reader should be told, not reasons to stop: unpinned
    model weights, single-run rows, template records on the board.
    """
    if not isinstance(payload, dict):
        raise PublishError("payload must be a JSON object")

    rows = payload.get("leaderboard")
    if not isinstance(rows, list):
        raise PublishError("payload has no 'leaderboard' list")

    for i, row in enumerate(rows):
        where = f"row {i}"
        if not isinstance(row, dict):
            raise PublishError(f"{where}: not an object")
        extra = set(row) - PUBLISHABLE_ROW_FIELDS
        if extra:
            raise PublishError(
                f"{where}: field(s) not on the publish allowlist: {sorted(extra)}. "
                "If this field is safe to publish, add it to "
                "repere.publish.PUBLISHABLE_ROW_FIELDS in the same commit."
            )
        for key, value in row.items():
            _check_scalar(key, value, where=where)

    blob = json.dumps(payload)
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle in blob:
            raise PublishError(f"payload contains {needle!r}, which belongs to the held-out data")

    warnings: list[str] = []
    prov = payload.get("provenance") or {}
    if not prov:
        warnings.append(
            "no provenance block: a number produced on a private host and "
            "published without one cannot be attributed by a reader"
        )
    else:
        warnings.extend(prov.get("warnings") or [])
        if prov.get("unpinned_models"):
            warnings.append("unpinned model weights: " + ", ".join(sorted(prov["unpinned_models"])))
    if any(r.get("n_epochs", 1) < 2 for r in rows):
        warnings.append("some rows are single-run and carry no confidence interval")

    hosts = {r.get("host_id") for r in rows if r.get("host_id")}
    if len(hosts) > 1:
        warnings.append(
            f"rows come from {len(hosts)} different hosts; latency, energy and "
            "resource consistency are not comparable between them"
        )
    return warnings


def write_board(payload: dict[str, Any], output_path: Path) -> list[str]:
    """Check, then write. Nothing reaches disk if the check fails.

    The order matters on a host that pushes to git automatically: a file written
    before validation is a file a subsequent commit can pick up.
    """
    warnings = check_payload(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n")
    return warnings
