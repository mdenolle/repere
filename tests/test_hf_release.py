"""Public Hugging Face releases: what gets built, and what must never get out.

The release folder is what a DOI will lock, so these tests pin the contract
rather than the wording:

  1. Only split=validation, visibility=public rows are written, and a held-out
     split visible to the suite stops the build.
  2. Every file in the folder matches manifest.json, and croissant.json points
     at the same sha256 values.
  3. croissant.json declares Croissant 1.1 (+ GeoCroissant when the release has
     a place), and tasks.jsonld has one Croissant Tasks TaskProblem per suite
     with the spec classes the upstream SHACL shapes require.
  4. The upload check refuses a folder with a held-out row in it.

When mlcroissant is installed the generated croissant.json is also validated
and every record is read back with it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_mod = _load_script("build_hf_release")
publish_mod = _load_script("publish_hf_release")


RELEASES = build_mod.load_releases()


@pytest.fixture(scope="module")
def stalta_folder(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("rel") / "synthetic_stalta"
    build_mod.build("synthetic_stalta", out, base_url="")
    return out


@pytest.fixture(scope="module")
def codameter_folder(tmp_path_factory) -> Path:
    pytest.importorskip("codameter", reason="dv/v release needs codameter")
    out = tmp_path_factory.mktemp("rel") / "codameter"
    build_mod.build("codameter", out, base_url="")
    return out


def _rows(folder: Path) -> list[dict]:
    rows = []
    for p in sorted((folder / "data").glob("*.jsonl")):
        rows += [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
    return rows


# --- the releases file --------------------------------------------------------


def test_every_release_entry_carries_license_rai_and_readiness():
    for name, rel in RELEASES.items():
        if rel.get("status") != "release":
            continue
        assert rel["hf_repo"].startswith("gaia-hazlab/"), name
        assert rel.get("license") and rel.get("license_url"), name
        assert rel.get("rai", {}).get("dataLimitations"), name
        assert rel.get("readiness"), name
        for cid, entry in rel["readiness"].items():
            assert entry.get("level") in (0, 1, 2, None), (name, cid)
            if entry.get("level") is not None:
                assert entry.get("evidence"), (name, cid)


def test_placeholder_release_is_not_buildable(tmp_path):
    assert RELEASES["ooi_rca"]["status"] == "placeholder"
    with pytest.raises(build_mod.ReleaseError, match="placeholder"):
        build_mod.build("ooi_rca", tmp_path / "x")


def test_no_release_targets_the_hidden_repository():
    hidden = _load_script("pull_eval_data").HF_REPO
    assert all(rel.get("hf_repo") != hidden for rel in RELEASES.values())


# --- what is written ------------------------------------------------------------


@pytest.mark.parametrize("folder_fixture", ["stalta_folder", "codameter_folder"])
def test_only_public_validation_rows_are_released(folder_fixture, request):
    folder = request.getfixturevalue(folder_fixture)
    rows = _rows(folder)
    assert rows
    assert {(r["split"], r["visibility"]) for r in rows} == {("validation", "public")}


def test_stalta_release_has_the_eleven_public_cases_and_three_negatives(stalta_folder):
    rows = _rows(stalta_folder)
    assert len(rows) == 11
    assert sum(1 for r in rows if r["gold"] == []) == 3


@pytest.mark.parametrize("folder_fixture", ["stalta_folder", "codameter_folder"])
def test_manifest_and_croissant_hashes_match_the_files(folder_fixture, request):
    folder = request.getfixturevalue(folder_fixture)
    manifest = json.loads((folder / "manifest.json").read_text())
    md = json.loads((folder / "croissant.json").read_text())
    by_path = {d["@id"]: d["sha256"] for d in md["distribution"]}
    for f in manifest["files"]:
        digest = hashlib.sha256((folder / f["path"]).read_bytes()).hexdigest()
        assert digest == f["sha256"] == by_path[f["path"]]
    assert publish_mod.check_folder(folder) == []


def test_build_refuses_a_suite_that_sees_a_hidden_split(tmp_path, monkeypatch):
    class Row:
        id, split, visibility = "x/y/z", "validation", "private"

    class Suite:
        def export_rows(self):
            return [Row()]

    with pytest.raises(build_mod.ReleaseError, match="not marked public"):
        build_mod.public_rows(Suite())


def test_build_refuses_when_private_dir_is_not_the_empty_one(tmp_path):
    from repere_suites.synthetic_stalta import items

    suite = items.SyntheticSTALTASuite()
    if Path(items.PRIVATE_DIR).resolve() == tmp_path.resolve():  # pragma: no cover
        pytest.skip("unexpected PRIVATE_DIR")
    with pytest.raises(build_mod.ReleaseError, match="PRIVATE_DIR"):
        build_mod.assert_no_hidden_source(suite, str(tmp_path))


# --- Croissant ------------------------------------------------------------------


def test_stalta_croissant_is_geocroissant(stalta_folder):
    md = json.loads((stalta_folder / "croissant.json").read_text())
    assert md["conformsTo"] == [
        "http://mlcommons.org/croissant/1.1",
        "http://mlcommons.org/croissant/geo/1.0",
    ]
    assert md["geocr:coordinateReferenceSystem"] == "EPSG:4326"
    geo = md["spatialCoverage"]["geo"]
    assert (geo["latitude"], geo["longitude"]) == (34.22362, -118.05832)
    assert md["temporalCoverage"].startswith("2019-07-06T03:19")
    assert "rai:dataLimitations" in md and "rai:dataCollection" in md
    ids = {rs["@id"] for rs in md["recordSet"]}
    assert ids == {"splits", "ridgecrest_detection"}


def test_codameter_croissant_is_plain_croissant(codameter_folder):
    md = json.loads((codameter_folder / "croissant.json").read_text())
    assert md["conformsTo"] == "http://mlcommons.org/croissant/1.1"
    assert "spatialCoverage" not in md
    assert any(b.get("codeRepository", "").endswith("codameter") for b in md["isBasedOn"])


@pytest.mark.parametrize("folder_fixture", ["stalta_folder", "codameter_folder"])
def test_tasks_jsonld_has_one_task_problem_per_suite(folder_fixture, request):
    folder = request.getfixturevalue(folder_fixture)
    graph = json.loads((folder / "tasks.jsonld").read_text())["@graph"]
    rs = {r["@id"] for r in json.loads((folder / "croissant.json").read_text())["recordSet"]}
    assert {g["@id"].split("#task-")[1] for g in graph} == rs - {"splits"}
    for g in graph:
        assert g["@type"] == "croissant:TaskProblem"
        assert g["croissant:output"]["@type"] == "croissant:OutputSpec"
        assert g["croissant:implementation"]["@type"] == "croissant:ImplementationSpec"
        assert g["croissant:execution"]["@type"] == "croissant:ExecutionSpec"
        assert g["croissant:evaluation"]["@type"] == "croissant:EvaluationSpec"


@pytest.mark.parametrize("folder_fixture", ["stalta_folder", "codameter_folder"])
def test_mlcroissant_reads_every_record(folder_fixture, request, monkeypatch):
    mlc = pytest.importorskip("mlcroissant")
    folder = request.getfixturevalue(folder_fixture)
    monkeypatch.chdir(folder)
    ds = mlc.Dataset(jsonld="croissant.json")
    counts = {rs.id: len(list(ds.records(record_set=rs.id))) for rs in ds.metadata.record_sets}
    manifest = json.loads((folder / "manifest.json").read_text())
    for f in manifest["files"]:
        if "rows" in f:
            assert counts[Path(f["path"]).stem] == f["rows"]


# --- the upload check -------------------------------------------------------------


def test_upload_check_refuses_a_held_out_row(stalta_folder, tmp_path):
    import shutil

    folder = tmp_path / "copy"
    shutil.copytree(stalta_folder, folder)
    data = folder / "data" / "ridgecrest_detection.jsonl"
    rows = data.read_text().splitlines()
    leaked = json.loads(rows[0]) | {"split": "test", "visibility": "private"}
    data.write_text("\n".join([json.dumps(leaked)] + rows[1:]) + "\n")
    problems = publish_mod.check_folder(folder)
    assert any("sha256 mismatch" in p for p in problems)
    assert any("test/private" in p for p in problems)


def test_card_front_matter_maps_each_suite_to_a_validation_file(stalta_folder):
    text = (stalta_folder / "README.md").read_text()
    front = yaml.safe_load(text.split("---")[1])
    assert front["license"] == "other" and front["license_link"] == "LICENSE.md"
    assert (stalta_folder / "LICENSE.md").exists()
    cfg = front["configs"][0]
    assert cfg["data_files"][0] == {"split": "validation", "path": "data/ridgecrest_detection.jsonl"}
