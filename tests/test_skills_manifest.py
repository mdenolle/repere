"""Tests that validate the real `.github/skills/` directory and manifest.

These run against the in-repo files; if a skill is added or its frontmatter
changes, these tests are the first to fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repere.skills import SkillLoader, SkillManifest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".github" / "skills"
MANIFEST_PATH = SKILLS_DIR / "manifest.yaml"


def test_skills_dir_loads_all_skills():
    skills = SkillLoader(skills_dir=SKILLS_DIR).load_all()
    expected = {
        "stalta-detection",
        "obspy-fdsn-fetch",
        "seismic-plotting",
        "seismic-report",
        "seismo-data-agent",
    }
    assert expected.issubset(set(skills))


def test_stalta_detection_skill_has_full_frontmatter_and_files():
    skill = SkillLoader(skills_dir=SKILLS_DIR).get("stalta-detection")
    assert skill.version == "v0.3"
    assert skill.task_kind == "code_generation"
    assert skill.references == ("pnsn-catalog.md", "obspy-recipes.md", "stalta-tuning.md")
    assert skill.examples == ("nisqually-detection.md", "quiet-window.md")
    assert skill.validators  # non-empty
    assert all(t for t in skill.references_text)
    assert all(t for t in skill.examples_text)


@pytest.mark.parametrize(
    "skill_name, expected_task_kind",
    [
        ("obspy-fdsn-fetch", "code_generation"),
        ("seismic-plotting", "plotting"),
        ("seismic-report", "report_drafting"),
    ],
)
def test_narrow_skills_have_required_frontmatter(skill_name, expected_task_kind):
    skill = SkillLoader(skills_dir=SKILLS_DIR).get(skill_name)
    assert skill.task_kind == expected_task_kind
    assert skill.version
    assert skill.description
    assert skill.body  # non-empty body


def test_manifest_binds_skills_to_correct_suites():
    manifest = SkillManifest.from_yaml(MANIFEST_PATH)
    assert manifest.skill_for_suite("sta_lta.fetch_code") == "stalta-detection"
    assert "sta_lta.intent_extraction" in manifest.suites_for_skill("stalta-detection")
    assert manifest.suites_for_skill("obspy-fdsn-fetch") == ["sta_lta.fetch_code"]
    assert manifest.suites_for_skill("seismic-plotting") == ["sta_lta.plot"]
    assert manifest.suites_for_skill("seismic-report") == ["sta_lta.report"]
