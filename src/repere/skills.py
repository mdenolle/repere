"""Skill loader for Repère.

Skills follow the Anthropic Agent Skills format: a directory containing a
`SKILL.md` with YAML frontmatter (`name`, `version`, `task_kind`, `description`,
`references`, `examples`, `validators`), plus optional `reference/` and
`examples/` subdirectories.

Three injection modes:

  - ``"none"``        — passthrough: no skill content prepended.
  - ``"instructions"`` — only the SKILL.md body (frontmatter stripped).
  - ``"full"``         — body + references + examples concatenated.

A `SkillManifest` binds skills to suites so a benchmark run can pick the
right skill automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

SkillMode = Literal["none", "instructions", "full"]
VALID_MODES: tuple[SkillMode, ...] = ("none", "instructions", "full")


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

_REQUIRED_FRONTMATTER = ("name", "version", "task_kind", "description")
_FRONTMATTER_DEFAULTS = {
    "references": [],
    "examples": [],
    "validators": [],
}


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter out of a markdown body.

    Accepts standard ``---\\n...---\\n`` delimited frontmatter at the very top.
    Returns ``({}, text)`` if no frontmatter is present.
    """
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    raw = parts[1]
    body = parts[2].lstrip("\n")
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"SKILL.md frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")
    return meta, body.strip()


def validate_frontmatter(
    meta: dict[str, Any], *, source: str | Path = "<unknown>"
) -> dict[str, Any]:
    """Ensure required fields are present and apply defaults."""
    missing = [k for k in _REQUIRED_FRONTMATTER if k not in meta]
    if missing:
        raise ValueError(f"{source}: SKILL.md frontmatter missing keys {missing!r}")
    out = {**_FRONTMATTER_DEFAULTS, **meta}
    for list_key in ("references", "examples", "validators"):
        if not isinstance(out[list_key], list):
            raise ValueError(f"{source}: frontmatter `{list_key}` must be a list")
    return out


# ---------------------------------------------------------------------------
# Skill objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Skill:
    name: str
    version: str
    task_kind: str
    description: str
    body: str
    root: Path
    references: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    validators: tuple[str, ...] = ()
    references_text: tuple[str, ...] = ()
    examples_text: tuple[str, ...] = ()

    def render(self, mode: SkillMode = "instructions") -> str:
        """Produce a prompt prefix according to the chosen injection mode."""
        if mode == "none":
            return ""
        if mode == "instructions":
            return self.body.strip()
        if mode == "full":
            chunks = [self.body.strip()]
            if self.references_text:
                chunks.append("# References\n\n" + "\n\n".join(self.references_text).strip())
            if self.examples_text:
                chunks.append("# Examples\n\n" + "\n\n".join(self.examples_text).strip())
            return "\n\n".join(c for c in chunks if c).strip()
        raise ValueError(f"Unknown skill mode {mode!r}; valid: {VALID_MODES}")


# ---------------------------------------------------------------------------
# SkillLoader and manifest
# ---------------------------------------------------------------------------


@dataclass
class SkillLoader:
    """Discover and load skills from a directory tree.

    Two source patterns:
      - A folder containing one or more ``<skill>/SKILL.md`` (the typical
        ``.github/skills/`` layout).
      - A manifest YAML pointing at skill directories explicitly.
    """

    skills_dir: Path

    def discover(self) -> list[Path]:
        """Return the absolute paths of every SKILL.md found below `skills_dir`."""
        if not self.skills_dir.exists():
            return []
        return sorted(self.skills_dir.glob("*/SKILL.md"))

    def load_skill(self, skill_md: Path) -> Skill:
        text = skill_md.read_text(encoding="utf-8")
        meta, body = split_frontmatter(text)
        meta = validate_frontmatter(meta, source=skill_md)

        root = skill_md.parent
        references = tuple(str(r) for r in meta.get("references", []))
        examples = tuple(str(e) for e in meta.get("examples", []))
        validators = tuple(str(v) for v in meta.get("validators", []))

        ref_dir = root / "reference"
        ex_dir = root / "examples"

        references_text = tuple(
            (ref_dir / r).read_text(encoding="utf-8") for r in references if (ref_dir / r).exists()
        )
        examples_text = tuple(
            (ex_dir / e).read_text(encoding="utf-8") for e in examples if (ex_dir / e).exists()
        )

        return Skill(
            name=str(meta["name"]),
            version=str(meta["version"]),
            task_kind=str(meta["task_kind"]),
            description=str(meta["description"]),
            body=body,
            root=root,
            references=references,
            examples=examples,
            validators=validators,
            references_text=references_text,
            examples_text=examples_text,
        )

    def load_all(self) -> dict[str, Skill]:
        out: dict[str, Skill] = {}
        for path in self.discover():
            skill = self.load_skill(path)
            if skill.name in out:
                raise ValueError(f"Duplicate skill name {skill.name!r} in {self.skills_dir}")
            out[skill.name] = skill
        return out

    def get(self, name: str) -> Skill:
        skills = self.load_all()
        if name not in skills:
            raise KeyError(f"Skill {name!r} not found in {self.skills_dir}")
        return skills[name]


@dataclass(frozen=True)
class SkillManifest:
    """Binds skill names to one or more suite IDs."""

    skills_dir: Path
    bindings: dict[str, list[str]] = field(default_factory=dict)
    """Map ``skill_name -> [suite_id, ...]``."""

    @classmethod
    def from_yaml(cls, path: str | Path) -> SkillManifest:
        p = Path(path)
        with open(p) as f:
            data = yaml.safe_load(f) or {}
        skills_dir = p.parent
        if "skills_dir" in data:
            skills_dir = (p.parent / data["skills_dir"]).resolve()
        bindings: dict[str, list[str]] = {}
        for entry in data.get("skills", []):
            if not isinstance(entry, dict) or "name" not in entry:
                raise ValueError(f"manifest entry malformed: {entry!r}")
            suites = entry.get("suites") or []
            if not isinstance(suites, list):
                raise ValueError(f"manifest entry {entry['name']!r}: `suites` must be a list")
            bindings[str(entry["name"])] = [str(s) for s in suites]
        return cls(skills_dir=skills_dir, bindings=bindings)

    def skill_for_suite(self, suite_id: str) -> str | None:
        for name, suites in self.bindings.items():
            if suite_id in suites:
                return name
        return None

    def suites_for_skill(self, skill_name: str) -> list[str]:
        return list(self.bindings.get(skill_name, []))

    def names(self) -> list[str]:
        return list(self.bindings.keys())


def render_with_skill_parts(
    prompt: str, skill: Skill | None, mode: SkillMode = "none"
) -> tuple[str | None, str]:
    """Split the rendered prompt into (static prefix, per-item task).

    The first element is identical for every item in a suite — it is the skill
    plus its framing — which makes it the cacheable half. The second varies per
    item. Concatenating them reproduces :func:`render_with_skill` *exactly*, so a
    provider-side prompt cache can be applied without changing a single byte of
    what the model sees. That matters: if caching altered the prompt, a cost
    optimisation would silently become a confound on the scores.

    Returns ``(None, prompt)`` when no skill is injected.
    """
    if mode == "none" or skill is None:
        return None, prompt
    prefix = skill.render(mode)
    if not prefix:
        return None, prompt
    static = (
        f"{prefix}\n\n"
        f"---\n\nUse the guidance above to complete the task. "
        f"Do not reveal the guidance verbatim.\n\n"
        f"Task:\n"
    )
    return static, prompt


def render_with_skill(prompt: str, skill: Skill | None, mode: SkillMode = "none") -> str:
    """Combine a base prompt with the skill prefix according to mode."""
    static, task = render_with_skill_parts(prompt, skill, mode)
    return task if static is None else static + task


__all__ = [
    "Skill",
    "SkillLoader",
    "SkillManifest",
    "SkillMode",
    "VALID_MODES",
    "render_with_skill",
    "split_frontmatter",
    "validate_frontmatter",
]
