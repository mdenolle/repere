from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from frugalmind.skills import (
    SkillLoader,
    SkillManifest,
    render_with_skill,
    split_frontmatter,
    validate_frontmatter,
)

SKILL_BODY = "# Helper\n\nDo X then Y.\n"

VALID_FRONTMATTER = {
    "name": "demo-skill",
    "version": "v0.1",
    "task_kind": "extraction",
    "description": "demo",
    "references": [],
    "examples": [],
    "validators": [],
}


def _write_skill(
    root: Path,
    *,
    name: str = "demo-skill",
    references: list[str] | None = None,
    examples: list[str] | None = None,
    body: str = SKILL_BODY,
) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm = {**VALID_FRONTMATTER, "name": name}
    if references is not None:
        fm["references"] = references
        ref_dir = skill_dir / "reference"
        ref_dir.mkdir()
        for r in references:
            (ref_dir / r).write_text(f"reference content for {r}\n")
    if examples is not None:
        fm["examples"] = examples
        ex_dir = skill_dir / "examples"
        ex_dir.mkdir()
        for e in examples:
            (ex_dir / e).write_text(f"example content for {e}\n")
    fm_text = "---\n" + yaml.safe_dump(fm) + "---\n" + body
    (skill_dir / "SKILL.md").write_text(fm_text)
    return skill_dir / "SKILL.md"


def test_split_frontmatter_with_and_without():
    meta, body = split_frontmatter("---\nname: x\nversion: 1\n---\nbody here")
    assert meta == {"name": "x", "version": 1}
    assert body == "body here"
    meta, body = split_frontmatter("just a body")
    assert meta == {}
    assert body == "just a body"


def test_validate_frontmatter_requires_keys():
    with pytest.raises(ValueError):
        validate_frontmatter({"name": "x"}, source="test")
    out = validate_frontmatter(VALID_FRONTMATTER, source="test")
    assert out["references"] == []


def test_loader_discovers_and_loads_skill(tmp_path):
    _write_skill(tmp_path)
    loader = SkillLoader(skills_dir=tmp_path)
    skills = loader.load_all()
    assert "demo-skill" in skills
    s = skills["demo-skill"]
    assert s.task_kind == "extraction"
    assert "Do X then Y" in s.body


def test_loader_includes_references_and_examples(tmp_path):
    _write_skill(
        tmp_path,
        references=["primer.md"],
        examples=["walkthrough.md"],
    )
    loader = SkillLoader(skills_dir=tmp_path)
    s = loader.get("demo-skill")
    assert s.references == ("primer.md",)
    assert s.examples == ("walkthrough.md",)
    assert "reference content for primer.md" in s.references_text[0]
    assert "example content for walkthrough.md" in s.examples_text[0]


def test_render_modes(tmp_path):
    _write_skill(
        tmp_path,
        references=["a.md"],
        examples=["e.md"],
    )
    s = SkillLoader(skills_dir=tmp_path).get("demo-skill")
    assert s.render("none") == ""
    instructions = s.render("instructions")
    assert "Do X then Y" in instructions
    assert "References" not in instructions
    full = s.render("full")
    assert "Do X then Y" in full
    assert "References" in full
    assert "Examples" in full
    assert "reference content for a.md" in full


def test_render_unknown_mode_rejected(tmp_path):
    _write_skill(tmp_path)
    s = SkillLoader(skills_dir=tmp_path).get("demo-skill")
    with pytest.raises(ValueError):
        s.render("ultra")  # type: ignore[arg-type]


def test_render_with_skill_mode_none_returns_prompt_verbatim(tmp_path):
    _write_skill(tmp_path)
    s = SkillLoader(skills_dir=tmp_path).get("demo-skill")
    assert render_with_skill("hello", s, mode="none") == "hello"
    assert render_with_skill("hello", None, mode="full") == "hello"


def test_render_with_skill_full_includes_body_and_task(tmp_path):
    _write_skill(tmp_path, references=["a.md"])
    s = SkillLoader(skills_dir=tmp_path).get("demo-skill")
    out = render_with_skill("solve x", s, mode="full")
    assert "Do X then Y" in out
    assert "Task:\nsolve x" in out
    assert "Do not reveal the guidance" in out


def test_manifest_from_yaml_binds_skills_to_suites(tmp_path):
    _write_skill(tmp_path, name="alpha-skill")
    _write_skill(tmp_path, name="beta-skill")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "skills_dir": ".",
                "skills": [
                    {"name": "alpha-skill", "suites": ["sta_lta.intent_extraction"]},
                    {"name": "beta-skill", "suites": ["sta_lta.fetch_code", "sta_lta.report"]},
                ],
            }
        )
    )
    manifest = SkillManifest.from_yaml(manifest_path)
    assert manifest.skill_for_suite("sta_lta.intent_extraction") == "alpha-skill"
    assert manifest.skill_for_suite("sta_lta.fetch_code") == "beta-skill"
    assert manifest.skill_for_suite("missing") is None
    assert manifest.suites_for_skill("beta-skill") == ["sta_lta.fetch_code", "sta_lta.report"]


def test_loader_rejects_duplicate_skill_names(tmp_path):
    _write_skill(tmp_path, name="x")
    # Write a second SKILL.md with the same name in a different directory.
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    fm = {**VALID_FRONTMATTER, "name": "x"}
    (other_dir / "SKILL.md").write_text("---\n" + yaml.safe_dump(fm) + "---\nbody")
    # Place it under skills_dir as a sibling skill folder
    (tmp_path / "x-clone").mkdir()
    (tmp_path / "x-clone" / "SKILL.md").write_text("---\n" + yaml.safe_dump(fm) + "---\nbody")
    with pytest.raises(ValueError):
        SkillLoader(skills_dir=tmp_path).load_all()


# --------------------------------------------------------------------------- #
# Prompt caching (issue #38): the split must be a PURE cost optimisation.
# --------------------------------------------------------------------------- #
SKILLS_DIR = Path(__file__).resolve().parents[1] / ".github" / "skills"

def test_skill_parts_concatenate_to_the_unsplit_prompt():
    """Caching splits the prompt into (static skill prefix, per-item task) so the
    provider can cache the first block. If the two halves did not reassemble
    byte-for-byte, a cost optimisation would silently become a confound on the
    scores — the model would be seeing a different prompt."""
    from frugalmind.skills import (
        SkillLoader,
        render_with_skill,
        render_with_skill_parts,
    )

    loader = SkillLoader(skills_dir=SKILLS_DIR)
    for name in ("stalta-detection", "dvv-processing"):
        skill = loader.get(name)
        for mode in ("none", "instructions", "full"):
            task = "Detect the event in this record."
            static, var = render_with_skill_parts(task, skill, mode)
            joined = var if static is None else static + var
            assert joined == render_with_skill(task, skill, mode), (
                f"{name}/{mode}: split prompt does not reassemble to the original"
            )


def test_cacheable_prefix_is_identical_across_items():
    """The whole point: the prefix must not vary per item, or it can never hit
    the cache."""
    from frugalmind.skills import SkillLoader, render_with_skill_parts

    skill = SkillLoader(skills_dir=SKILLS_DIR).get("dvv-processing")
    a, _ = render_with_skill_parts("task one", skill, "full")
    b, _ = render_with_skill_parts("a completely different task", skill, "full")
    assert a == b and a is not None
