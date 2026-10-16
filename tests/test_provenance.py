"""Tests for `repere.provenance`.

Two contracts:

  1. **Collection never raises.** A provenance block that fails the run is a
     provenance block people switch off. Missing GPU tools, no Ollama server, no
     git: all record `None` and carry on.
  2. **A local model is pinned only by its digest.** `qwen2.5:7b` is a moving
     pointer. This is the check `rca.cost` skips for local providers, and the
     one that matters once runs move to a private GPU host.
"""

from __future__ import annotations

from repere.provenance import (
    HOST_BOUND_FIELDS,
    HostProfile,
    ModelPin,
    RunProvenance,
    capture_host,
    capture_ollama_models,
    capture_run_provenance,
    dataset_hashes,
)


def test_capture_never_raises_on_a_machine_without_gpus_or_ollama():
    host = capture_host()
    assert host.host_id and len(host.host_id) == 12
    assert host.platform and host.python_version
    # No assertion on gpu_count/ollama_version: both are legitimately None here.


def test_host_id_is_stable_and_hides_the_hostname():
    import platform

    a, b = capture_host(), capture_host()
    assert a.host_id == b.host_id
    assert platform.node() not in a.host_id


def test_capture_ollama_models_returns_empty_without_a_server():
    # No server in CI; the function must degrade rather than fail.
    assert isinstance(capture_ollama_models([]), list)


def test_a_local_model_without_a_digest_is_not_pinned():
    assert ModelPin("qwen2.5:7b", "ollama").pinned is False
    assert ModelPin("qwen2.5:7b", "ollama", digest="sha256:abc").pinned is True


def test_an_api_model_is_pinned_by_its_dated_id():
    assert ModelPin("claude-haiku-4-5-20251001", "anthropic").pinned is True


def test_latency_and_resource_consistency_are_host_bound():
    """The fields a reader must not compare across machines."""
    assert "latency_s_mean" in HOST_BOUND_FIELDS
    assert "latency_s_ci95" in HOST_BOUND_FIELDS
    # Resource consistency averages a CV over cost, latency and tokens; latency
    # is in there, so the whole metric inherits the binding.
    assert "consistency_resource" in HOST_BOUND_FIELDS
    # Scores and tokens are invariant and must not be listed.
    assert "score_mean" not in HOST_BOUND_FIELDS
    assert "total_tokens" not in HOST_BOUND_FIELDS


def test_warnings_name_every_reason_a_run_is_not_attributable():
    prov = RunProvenance(
        harness_commit=None,
        harness_dirty=True,
        harness_version=None,
        host=HostProfile(host_id="x" * 12, platform="linux", python_version="3.12"),
        models=[ModelPin("qwen2.5:7b", "ollama")],
    )
    text = " ".join(prov.warnings())
    assert "commit unknown" in text
    assert "dirty" in text
    assert "qwen2.5:7b" in text
    assert "dataset hashes" in text


def test_a_fully_pinned_run_has_no_warnings():
    prov = RunProvenance(
        harness_commit="abc1234",
        harness_dirty=False,
        harness_version="0.5.2",
        host=HostProfile(host_id="y" * 12, platform="linux", python_version="3.12"),
        models=[ModelPin("qwen2.5:7b", "ollama", digest="sha256:deadbeef")],
        dataset_sha256={"sta_lta/v0.1/intent.jsonl": "0" * 64},
    )
    assert prov.warnings() == []


def test_payload_exposes_the_host_bound_field_list_to_the_renderer():
    prov = RunProvenance(
        harness_commit="abc",
        harness_dirty=False,
        harness_version="0.5.2",
        host=HostProfile(host_id="z" * 12, platform="linux", python_version="3.12"),
        models=[ModelPin("qwen2.5:7b", "ollama")],
    )
    payload = prov.to_payload()
    assert "latency_s_mean" in payload["host_bound_fields"]
    assert payload["unpinned_models"] == ["qwen2.5:7b"]


def test_dataset_hashes_reads_exported_manifests(tmp_path):
    d = tmp_path / "sta_lta" / "v0.1"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(
        '{"files": [{"path": "sta_lta/v0.1/intent.jsonl", "sha256": "abc123"}]}'
    )
    assert dataset_hashes(tmp_path) == {"sta_lta/v0.1/intent.jsonl": "abc123"}


def test_dataset_hashes_is_empty_when_nothing_is_exported(tmp_path):
    assert dataset_hashes(tmp_path / "nope") == {}


def test_capture_run_provenance_produces_a_serialisable_block():
    import json

    prov = capture_run_provenance(seed=0, temperature=0.0, n_epochs=5)
    payload = prov.to_payload()
    json.dumps(payload)  # must not raise
    assert payload["n_epochs"] == 5
    assert "host" in payload and payload["host"]["host_id"]
