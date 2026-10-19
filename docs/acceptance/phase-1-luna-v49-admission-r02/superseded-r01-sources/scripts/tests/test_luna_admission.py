"""Offline routing, exact-wire execution, durable stop and authority regressions."""
# ruff: noqa: E402

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.luna_admission_gate import (
    BASE,
    PRIVATE,
    Ledger,
    env_metadata,
    prior_human_checks,
    private_write,
    approved,
)
from acceptance_support.luna_review_routing import CONFIG, ExplicitRouter
from acceptance_support.om_diagnostic import valid_review
from acceptance_support.qwen_review_budget import canonical, sha
from app.core.provider_target import ApprovedTarget
from app.agents.hybrid_resource_review import review_output_schema
from jsonschema import Draft202012Validator
from prepare_luna_admission import build, candidates
from prepare_luna_materials import build as material_build
import run_luna_admission as run


def read(name):
    return json.loads((ROOT / BASE / name).read_text())


def test_materials_reproduce_and_human_labels_pending():
    cases, labels = asyncio.run(material_build())
    assert cases == read("cases.json") and labels == read("proposed-labels.json")
    assert (
        len(cases) == 12 and sum(x["phase"] == "holdout" for x in labels["labels"]) == 4
    )
    assert all(
        x["independent_human_status"] == "pending" and x["model_result"] is None
        for x in labels["labels"]
    )
    for case in cases.values():
        assert len(candidates(case)) == 3
        assert (
            case["material"]["teaching_context"]
            == case["input_snapshot"]["teaching_context"]
        )


def test_actual_agent_adapter_wires_reproduce_and_remain_separate():
    capture = asyncio.run(build())
    assert capture == {n: read(n) for n in capture}
    for request in capture["requests.json"].values():
        body = json.loads(bytes.fromhex(request["wire_hex"]))
        assert body["model"] == "gpt-6-luna" and body["reasoning"] == {"effort": "low"}
        assert body["max_output_tokens"] == 8192 and body["temperature"] == 0.0
        assert body["text"]["format"]["type"] == "json_schema"
        assert request["business_schema_sha256"] == request["wire_schema_sha256"]
        assert "qwen" not in request["target"]["host"]
    for role, request in capture["generation-route-capture.json"].items():
        body = json.loads(bytes.fromhex(request["wire_hex"]))
        assert body["model"] == "deepseek-flash" and body["reasoning"] == {
            "effort": "none"
        }
        assert body["max_output_tokens"] == (2048 if role == "plan" else 4096)
    assert (
        capture["budget.json"]["cost_cap"] is None
        and capture["budget.json"]["requests_authorized"] == 0
    )


def test_truth_calculations_not_using_plan_as_evidence():
    cases = read("cases.json")
    assert sum([3, 8, 4]) == 15
    values = []
    states = []
    for v in [6, 9]:
        values.append(v)
        states.append(len(values))
    result = values.pop()
    states.append(len(values))
    assert states == [1, 2, 1] and result == 9
    assert (
        "返回17"
        in cases["screen-fact"]["material"]["candidates"][0]["envelope"]["content"][
            "markdown"
        ]
    )
    assert (
        "return a[5]"
        in cases["screen-safety"]["material"]["candidates"][1]["envelope"]["content"][
            "source"
        ]
    )
    # Do not execute supplied C or assert a numeric result for UB.
    assert (
        "a[top]"
        in cases["holdout-stack-safety"]["material"]["candidates"][1]["envelope"][
            "content"
        ]["source"]
    )


def test_unknown_learner_is_not_fabricated_and_scope_is_explicit():
    cases = read("cases.json")
    assert all(c["input_snapshot"]["learner_evidence"] == {} for c in cases.values())
    tc = cases["holdout-prerequisite"]["material"]["teaching_context"]
    assert (
        tc["target_node_id"] == "linked-list-insertion"
        and tc["teaching_node_id"] == "c-pointer"
    )
    assert (
        tc["segment_scope"] == "prerequisite_segment"
        and tc["teaching_mode"] == "recommended"
    )


def test_no_approval_denies_before_credentials_or_private_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        run,
        "approved",
        lambda root: (_ for _ in ()).throw(ValueError("NOT_AUTHORIZED")),
    )
    monkeypatch.setattr(
        run, "credential", lambda *a: pytest.fail("must not read credential")
    )
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        asyncio.run(run.step(tmp_path))
    assert not (tmp_path / PRIVATE).exists()


def test_ledger_reserved_crash_is_not_replayed(tmp_path):
    clock = [100.0]
    ledger = Ledger(tmp_path / "ledger.sqlite", "a" * 64, lambda: clock[0])
    slots = [str(n) for n in range(12)]
    assert ledger.reserve(slots) == (0, "0")
    ledger = Ledger(tmp_path / "ledger.sqlite", "a" * 64, lambda: clock[0])
    with pytest.raises(ValueError, match="UNCERTAIN"):
        ledger.reserve(slots)
    assert len(ledger.snapshot()[2]) == 1 and ledger.snapshot()[1]


def test_ledger_deadline_survives_reopen_and_different_manifest_denied(tmp_path):
    clock = [1.0]
    path = tmp_path / "ledger.sqlite"
    ledger = Ledger(path, "a" * 64, lambda: clock[0])
    ledger.reserve([str(n) for n in range(12)])
    ledger.finish(0, "b" * 64)
    clock[0] = 1801.0
    ledger = Ledger(path, "a" * 64, lambda: clock[0])
    with pytest.raises(ValueError):
        ledger.reserve([str(n) for n in range(12)])
    with pytest.raises(ValueError, match="REUSE"):
        Ledger(path, "c" * 64)


def test_ledger_twelve_calls_and_no_thirteenth(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite", "a" * 64)
    slots = [str(n) for n in range(12)]
    for n in range(12):
        assert ledger.reserve(slots) == (n, str(n))
        ledger.finish(n, "b" * 64)
    with pytest.raises(ValueError, match="CALL_LIMIT"):
        ledger.reserve(slots)
    ledger.stop("FAIL")
    with pytest.raises(ValueError):
        ledger.reserve(slots)


def test_ledger_symlink_denied(tmp_path):
    target = tmp_path / "target"
    target.touch()
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="UNSAFE"):
        Ledger(link, "a" * 64)


def setup_env(root):
    key = "test-placeholder-no-real-secret"
    p = root / ".env"
    p.write_text(
        "EDUMIND_PROVIDER_BASE_URL=https://www.cbbb.fun/v1\nEDUMIND_PROVIDER_MODEL=gpt-6-luna\nEDUMIND_PROVIDER_API_KEY="
        + key
        + "\nEDUMIND_PROVIDER_REVIEW_REASONING_EFFORT=low\nEDUMIND_PROVIDER_STRUCTURED_TRANSPORT=responses_json_schema\n"
    )
    p.chmod(0o600)
    return {"env_metadata": env_metadata(p)}, key


def test_credential_never_falls_back_or_ignores_env_changes(tmp_path):
    manifest, key = setup_env(tmp_path)
    assert run.credential(tmp_path, manifest) == key
    (tmp_path / ".env").write_text("EDUMIND_PROVIDER_MODEL=deepseek-flash\n")
    with pytest.raises(ValueError, match="ENV_CHANGED"):
        run.credential(tmp_path, manifest)


def test_real_composition_mock_http_exact_wire_and_audit(tmp_path, monkeypatch):
    manifest, key = setup_env(tmp_path)
    case = read("cases.json")["screen-complete"]
    wire = bytes.fromhex(read("requests.json")["screen-complete"]["wire_hex"])
    authorized = []
    target = ApprovedTarget(CONFIG.review_base, "www.cbbb.fun", 443, ("8.8.8.8",))
    monkeypatch.setattr(
        run,
        "ProviderTargetGuard",
        lambda *a: SimpleNamespace(approve_base=lambda: target),
    )
    original = run.ExactTransport

    def reply(request):
        assert request.headers["authorization"] == "Bearer " + key
        body = {
            "model": "gpt-6-luna",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(valid_review("unit")),
                        }
                    ],
                }
            ],
            "usage": {"input_tokens": 123, "output_tokens": 150},
        }
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(body).encode()))

    monkeypatch.setattr(
        run,
        "ExactTransport",
        lambda w, t, a: original(w, t, a, httpx.MockTransport(reply)),
    )
    result = asyncio.run(
        run.attempt(tmp_path, manifest, case, wire, lambda: authorized.append(1))
    )
    assert authorized == [1] and result["sent"] == 1 and result["http_status"] == 200
    assert result["raw_complete"] and result["record"]["request_digest"] == sha(wire)
    assert result["input_tokens"] == 123 and result["output_tokens"] == 150
    assert key not in canonical(result).decode()


@pytest.mark.parametrize("defect", ["model", "usage", "incomplete", "schema"])
def test_complete_response_failures_are_not_accepted(tmp_path, monkeypatch, defect):
    manifest, _ = setup_env(tmp_path)
    case = read("cases.json")["screen-complete"]
    wire = bytes.fromhex(read("requests.json")["screen-complete"]["wire_hex"])
    target = ApprovedTarget(CONFIG.review_base, "www.cbbb.fun", 443, ("8.8.8.8",))
    monkeypatch.setattr(
        run,
        "ProviderTargetGuard",
        lambda *a: SimpleNamespace(approve_base=lambda: target),
    )
    body = {
        "model": "gpt-6-luna",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": json.dumps(valid_review("unit"))}
                ],
            }
        ],
        "usage": {"input_tokens": 123, "output_tokens": 150},
    }
    if defect == "model":
        body["model"] = "different"
    if defect == "usage":
        body["usage"]["output_tokens"] = 8193
    if defect == "incomplete":
        body["status"] = "incomplete"
    if defect == "schema":
        body["output"][0]["content"][0]["text"] = '{"unresolved":[42]}'
    original = run.ExactTransport
    monkeypatch.setattr(
        run,
        "ExactTransport",
        lambda w, t, a: original(
            w,
            t,
            a,
            httpx.MockTransport(
                lambda r: httpx.Response(
                    200, stream=httpx.ByteStream(json.dumps(body).encode())
                )
            ),
        ),
    )
    with pytest.raises(run.LunaAttemptFailure) as e:
        asyncio.run(run.attempt(tmp_path, manifest, case, wire, lambda: None))
    assert e.value.details["http_status"] == 200 and e.value.details["sent"] == 1


def test_exact_transport_rejects_changed_wire_before_authority():
    target = ApprovedTarget(CONFIG.review_base, "www.cbbb.fun", 443, ("8.8.8.8",))
    authorized = []

    async def go():
        t = run.ExactTransport(
            b"expected",
            target,
            lambda: authorized.append(1),
            httpx.MockTransport(lambda r: pytest.fail("no send")),
        )
        r = httpx.Request(
            "POST",
            "https://8.8.8.8/v1/responses",
            content=b"changed",
            headers={"host": "www.cbbb.fun"},
        )
        r.extensions["sni_hostname"] = "www.cbbb.fun"
        with pytest.raises(ValueError, match="WIRE"):
            await t.handle_async_request(r)
        await t.aclose()

    asyncio.run(go())
    assert not authorized


def test_business_schema_retains_duplicate_check_rejection():
    value = valid_review("unit")
    value["coverage"]["checked"].append(value["coverage"]["checked"][0])
    with pytest.raises(Exception):
        Draft202012Validator(review_output_schema("unit", anchor_ids=[])).validate(
            value
        )


def test_router_rejects_retry_before_either_adapter():
    class Trap:
        async def generate_structured(self, r):
            pytest.fail("no adapter")

    router = ExplicitRouter(Trap(), Trap())
    with pytest.raises(ValueError, match="RETRY"):
        asyncio.run(router.generate_structured(None, retry_safe=True))


def write_manifest(root):
    from acceptance_support.luna_admission_gate import BASE
    import time

    manifest, _ = setup_env(root)
    base = root / BASE
    base.mkdir(parents=True)
    (base / "proposed-labels.json").write_text("{}")
    manifest.update(
        files={BASE + "/proposed-labels.json": sha(b"{}")},
        expires_at_epoch=time.time() + 3600,
    )
    (base / "manifest.json").write_bytes(canonical(manifest))
    return manifest, sha(canonical(manifest))


def test_exact_approval_and_label_approval_are_both_required(tmp_path):
    manifest, h = write_manifest(tmp_path)
    base = tmp_path / BASE
    with pytest.raises(ValueError):
        approved(tmp_path)
    a = {
        "manifest_sha256": h,
        "requests": 12,
        "cost_policy": "uncapped_by_explicit_user_instruction",
        "reviewer": "Lee",
        "source_user_message": "synthetic test authorization",
        "decision": "approve_exact_diagnostic",
    }
    (base / "run-approval.json").write_bytes(canonical(a))
    with pytest.raises(ValueError):
        approved(tmp_path)
    labels = {
        "manifest_sha256": h,
        "reviewer": "Lee",
        "source_user_message": "synthetic independent labels",
        "decision": "accept_all_materials_and_labels",
        "labels_sha256": manifest["files"][BASE + "/proposed-labels.json"],
    }
    (base / "labels-human.json").write_bytes(canonical(labels))
    assert approved(tmp_path)[1] == h
    a["requests"] = True
    (base / "run-approval.json").write_bytes(canonical(a))
    with pytest.raises(ValueError, match="AUTHORIZED"):
        approved(tmp_path)


def test_modified_frozen_file_is_rejected(tmp_path):
    from acceptance_support.luna_admission_gate import verify_freeze

    write_manifest(tmp_path)
    (tmp_path / BASE / "proposed-labels.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="FREEZE_CHANGED"):
        verify_freeze(tmp_path)


def test_negative_human_check_halts_irreversibly(tmp_path):
    private = tmp_path / PRIVATE
    private.mkdir(parents=True)
    checks = tmp_path / BASE / "assessments"
    checks.mkdir(parents=True)
    h = "a" * 64
    ledger = Ledger(private / "requests.sqlite", h)
    slots = [str(n) for n in range(12)]
    ledger.reserve(slots)
    receipt = {"slot": "0", "semantic_accepted": False}
    rh = sha(canonical(receipt))
    private_write(private / "0.json", receipt)
    ledger.finish(0, rh)
    signed = {
        "manifest_sha256": h,
        "receipt_sha256": rh,
        "reviewer": "Lee",
        "source_user_message": "synthetic",
        "integrity": True,
        "all_claims": False,
        "all_citations": True,
        "criterion": True,
        "issues": ["unsupported claim"],
    }
    (checks / "0.json").write_bytes(canonical(signed))
    with pytest.raises(ValueError, match="ELIMINATED"):
        prior_human_checks(tmp_path, h, ledger)
    assert ledger.snapshot()[1] == "SEMANTIC_OR_CITATION_FAILURE"
    signed["all_claims"] = True
    signed["issues"] = []
    (checks / "0.json").write_bytes(canonical(signed))
    with pytest.raises(ValueError, match="STOPPED"):
        prior_human_checks(tmp_path, h, ledger)


def test_screen_gate_before_holdout(tmp_path):
    private = tmp_path / PRIVATE
    private.mkdir(parents=True)
    checks = tmp_path / BASE / "assessments"
    checks.mkdir(parents=True)
    h = "a" * 64
    ledger = Ledger(private / "requests.sqlite", h)
    slots = [str(n) for n in range(12)]
    receipts = {}
    for n in range(8):
        _, slot = ledger.reserve(slots)
        r = {"slot": slot}
        rh = sha(canonical(r))
        receipts[slot] = rh
        private_write(private / (slot + ".json"), r)
        ledger.finish(n, rh)
        (checks / (slot + ".json")).write_bytes(
            canonical(
                {
                    "manifest_sha256": h,
                    "receipt_sha256": rh,
                    "reviewer": "Lee",
                    "source_user_message": "synthetic",
                    "integrity": True,
                    "all_claims": True,
                    "all_citations": True,
                    "criterion": True,
                    "issues": [],
                }
            )
        )
    with pytest.raises(ValueError):
        prior_human_checks(tmp_path, h, ledger)
    (tmp_path / BASE / "screen-pass.json").write_bytes(
        canonical(
            {
                "manifest_sha256": h,
                "reviewer": "Lee",
                "source_user_message": "synthetic",
                "decision": "admit_holdout",
                "receipts": receipts,
            }
        )
    )
    prior_human_checks(tmp_path, h, ledger)


@pytest.mark.parametrize("kind", ["exception", "wrong-verdict"])
def test_actual_step_persists_failure_and_does_not_repeat(tmp_path, monkeypatch, kind):
    h = "a" * 64
    monkeypatch.setattr(run, "approved", lambda root: ({}, h))
    p = tmp_path / BASE
    p.mkdir(parents=True)
    for name in ["requests.json", "cases.json", "proposed-labels.json", "budget.json"]:
        (p / name).write_bytes(canonical(read(name)))
    sends = []

    async def perform(root, manifest, case, wire, auth):
        auth()
        sends.append(1)
        if kind == "exception":
            raise TimeoutError()
        return {"record": {"local_routing": {"verdict": "needs_human"}}}

    result = asyncio.run(run.step(tmp_path, perform))
    assert result["state"] == "HALTED" and len(sends) == 1
    with pytest.raises(ValueError):
        asyncio.run(run.step(tmp_path, perform))
    assert len(sends) == 1 and (tmp_path / PRIVATE / "screen-complete.json").is_file()


def test_http400_compressed_safe_failure_metadata(tmp_path, monkeypatch):
    import gzip

    manifest, _ = setup_env(tmp_path)
    case = read("cases.json")["screen-complete"]
    wire = bytes.fromhex(read("requests.json")["screen-complete"]["wire_hex"])
    target = ApprovedTarget(CONFIG.review_base, "www.cbbb.fun", 443, ("8.8.8.8",))
    monkeypatch.setattr(
        run,
        "ProviderTargetGuard",
        lambda *a: SimpleNamespace(approve_base=lambda: target),
    )
    original = run.ExactTransport
    payload = gzip.compress(
        json.dumps(
            {
                "error": {
                    "code": "invalid_json_schema",
                    "message": "uniqueItems unsupported",
                }
            }
        ).encode()
    )
    monkeypatch.setattr(
        run,
        "ExactTransport",
        lambda w, t, a: original(
            w,
            t,
            a,
            httpx.MockTransport(
                lambda r: httpx.Response(
                    400,
                    headers={
                        "content-type": "application/json",
                        "content-encoding": "gzip",
                    },
                    stream=httpx.ByteStream(payload),
                )
            ),
        ),
    )
    with pytest.raises(run.LunaAttemptFailure) as e:
        asyncio.run(run.attempt(tmp_path, manifest, case, wire, lambda: None))
    details = e.value.details
    assert (
        details["http_status"] == 400
        and details["sent"] == 1
        and details["raw_complete"]
    )
    assert details["provider_error"] is not None and details["raw_bytes"] == len(
        payload
    )


def test_exact_target_mismatch_is_denied_before_send():
    target = ApprovedTarget(CONFIG.review_base, "www.cbbb.fun", 443, ("8.8.8.8",))

    async def go():
        t = run.ExactTransport(
            b"wire",
            target,
            lambda: pytest.fail("no authorize"),
            httpx.MockTransport(lambda r: pytest.fail("no send")),
        )
        r = httpx.Request(
            "POST",
            "https://1.1.1.1/v1/responses",
            content=b"wire",
            headers={"host": "www.cbbb.fun"},
        )
        r.extensions["sni_hostname"] = "www.cbbb.fun"
        with pytest.raises(ValueError, match="TARGET_CHANGED"):
            await t.handle_async_request(r)
        await t.aclose()

    asyncio.run(go())


def test_failure_codes_are_specific_without_arbitrary_error_text():
    assert (
        run.safe_failure(ValueError("RESPONSE_MODEL_CHANGED"))
        == "RESPONSE_MODEL_CHANGED"
    )
    assert (
        run.safe_failure(ValueError("provider raw error and hypothetical secret"))
        == "DIAGNOSTIC_FAILURE"
    )
