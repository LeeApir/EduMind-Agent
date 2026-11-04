"""Only four-text request, merge refusal and unified reassembly; no Provider/DB."""

import json
from copy import deepcopy

import pytest

from app.services import head_course_fact_revision as f
from scripts import head_course_goal as entry


def replacement():
    # Explicit offline transport fixture, never a real correction or teaching success.
    return {k: "离线测试替换 " + k for k in f.PATHS}


def test_request_parent_and_schema():
    req = f.body()
    data = json.loads(req["input"][1]["content"])
    assert req["text"]["format"]["schema"] == f.SCHEMA
    assert set(f.SCHEMA["properties"]) == set(f.PATHS) and not f.SCHEMA["additionalProperties"]
    assert data["parent_candidate"]["candidate_digest"] == f.PARENT
    assert data["same_version_materials"] == data["parent_candidate"]["payload"]["materials"]
    assert [i["id"] for i in data["review"]["findings"]] == ["F01", "F02"]


def test_merge_changes_only_four_fields_and_reassembles_both_views():
    parent = f.inputs()["parent_candidate"]
    saved = deepcopy(parent)
    rep = replacement()
    candidate = f.merge(parent, rep)
    restored = deepcopy(candidate["raw_output"])
    for path in f.PATHS.values():
        a = restored
        b = parent["raw_output"]
        for p in path[:-1]:
            a = a[p]
            b = b[p]
        a[path[-1]] = b[path[-1]]
    assert restored == parent["raw_output"] and parent == saved
    assert candidate["payload"] == parent["payload"] and candidate["parent_digest"] == f.PARENT
    assembled = f.assemble(candidate)
    assert (
        next(b for b in assembled["blocks"] if b["anchor_id"] == "text-12")["markdown"]
        == rep["learning_summary"]
    )
    assert (
        next(b for b in assembled["blocks"] if b["kind"] == "visualization")["text_alternative"]
        == rep["learning_summary"]
    )
    assert candidate["raw_output"]["questions"] == parent["raw_output"]["questions"]
    assert candidate["raw_output"]["step_notes"] == parent["raw_output"]["step_notes"]
    candidate["raw_output"]["paragraphs"][0]["text"] = "outside"
    with pytest.raises(Exception, match="OUTSIDE_ALLOWLIST"):
        f.assemble(candidate)


@pytest.mark.parametrize("kind", ["extra", "missing", "type", "empty", "parent", "fact_ids"])
def test_refuses(kind):
    parent = deepcopy(f.inputs()["parent_candidate"])
    rep = replacement()
    if kind == "extra":
        rep["questions"] = {}
    if kind == "missing":
        del rep["paragraph_1_text"]
    if kind == "type":
        rep["paragraph_1_text"] = []
    if kind == "empty":
        rep["paragraph_1_text"] = ""
    if kind == "parent":
        parent["candidate_digest"] = "0" * 64
    if kind == "fact_ids":
        parent["raw_output"]["paragraphs"][1]["fact_ids"] = ["other"]
    with pytest.raises(Exception):
        f.merge(parent, rep)


def test_strict_actual_adapter_refuses_duplicate_replacement_key():
    from scripts.head_course_goal_fixture import envelope

    req = f.body()
    value = replacement()
    raw = json.loads(envelope(value))
    txt = raw["output"][0]["content"][0]["text"]
    raw["output"][0]["content"][0]["text"] = txt[:-1] + ',"learning_summary":"duplicate"}'
    with pytest.raises(Exception, match="DUPLICATE_JSON_KEY"):
        entry.raw_io.observe_generation(req, json.dumps(raw).encode())


@pytest.mark.parametrize("bad", [False, True])
def test_single_actual_entry_with_mock_transport(tmp_path, monkeypatch, bad):
    import time

    import httpx
    from cryptography.fernet import Fernet

    from scripts import head_course_fact_revision as entry2
    from scripts.head_course_goal_fixture import envelope

    vault = tmp_path / "new-vault"
    vault.mkdir(mode=0o700)
    key = Fernet.generate_key()
    (vault / "raw.key").write_bytes(key)
    (vault / "raw.key").chmod(0o600)
    monkeypatch.setattr(entry2, "VAULT", vault)
    monkeypatch.setattr(entry2, "package_digest", lambda: "a" * 64)
    approval = dict(
        manifest_sha256="a" * 64,
        parent_digest=f.PARENT,
        explicit_user_authorization=True,
        accept_fact_revision_and_batch_C2=True,
        max_http_requests=1,
        starts_epoch=int(time.time()) - 1,
        expires_epoch=int(time.time()) + 599,
    )
    calls = []
    saved = envelope(replacement())
    if bad:
        saved = json.loads(saved)
        saved["output"][0]["phase"] = "analysis"
        saved = json.dumps(saved).encode()

    def receive(request):
        calls.append(1)
        assert json.loads(request.content) == f.body()
        return httpx.Response(200, stream=httpx.ByteStream(saved))

    if bad:
        with pytest.raises(Exception):
            entry2.send(vault, approval, transport=httpx.MockTransport(receive), key="fixture-key")
        assert (vault / "revision.failure.json").exists() and not (
            vault / "revision.candidate.json"
        ).exists()
    else:
        entry2.send(vault, approval, transport=httpx.MockTransport(receive), key="fixture-key")
        candidate = json.loads((vault / "revision.candidate.json").read_text())
        assert candidate == f.merge(f.inputs()["parent_candidate"], replacement())
    assert entry.raw_io.decrypt(vault / "revision.raw.enc", Fernet(key)) == saved
    assert (vault / "STOP").exists()
    with pytest.raises(Exception):
        entry2.send(vault, approval, transport=httpx.MockTransport(receive), key="fixture-key")
    assert len(calls) == 1
