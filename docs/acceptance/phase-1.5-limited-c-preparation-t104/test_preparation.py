"""Bounded offline checks only. Synthetic prose is not a model success."""

import json
import os
import sys
import time
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prepare as p  # noqa: E402
import execute_once as e  # noqa: E402


def content(slot):
    cat = p.c.make_catalog(p.SPECS[slot])
    return dict(
        paragraphs=[
            dict(
                key="synthetic",
                text="合成离线夹具，不是课程或模型生成。",
                fact_ids=["trace_step_00"],
            )
        ],
        questions={
            k: dict(stem="合成题干 " + k, explanation="合成解析", fact_ids=["obs_" + k])
            for k in p.c.QUESTION_KEYS
        },
        prerequisites="合成前提",
        learning_summary="合成总结",
        lifecycle="合成生命周期",
        failure_scope="合成范围",
        step_notes=[
            dict(frame_id=f["frame_id"], title="合成标题", note="合成说明")
            for f in p.frames(cat)
        ],
    )


def envelope(slot):
    return p.canonical(
        dict(
            status="completed",
            model="deepseek-flash",
            store=False,
            error=None,
            incomplete_details=None,
            usage=dict(input_tokens=10, output_tokens=20, total_tokens=30),
            output=[
                dict(
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[
                        dict(
                            type="output_text",
                            text=json.dumps(content(slot), ensure_ascii=False),
                        )
                    ],
                )
            ],
        )
    )


def vault(tmp_path):
    v = tmp_path / "private"
    v.mkdir(mode=0o700)
    (v / "raw.key").write_bytes(Fernet.generate_key())
    os.chmod(v / "raw.key", 0o600)
    return v


def approval():
    now = time.time()
    return dict(
        version=p.VERSION,
        package_sha256=e.verify_package(),
        explicit_user_authorization=True,
        accept_contract_A_D_and_batch_C2=True,
        starts_epoch=now - 1,
        expires_epoch=now + 1799,
    )


def test_exact_inputs_and_independent_expectations():
    for slot, head, values, failures, count in [
        ("C01", "t1", [2, 1, 9], 0, 13),
        ("C02", "t1", [5], 1, 10),
    ]:
        cat = p.check_content(slot, content(slot))
        obs = cat["example"]["observation"]
        assert (
            obs["caller_head"],
            obs["reachable_prefix"],
            obs["allocation_failures"],
            obs["traversal_status"],
        ) == (head, values, failures, "terminated")
        assert len(p.frames(cat)) == count
        assert (HERE / f"{slot}-request.json").read_bytes() == p.canonical(p.body(slot))
        assert "assistant-revision" not in (HERE / f"{slot}-request.json").read_text()


def test_missing_or_wrong_frame_is_failure():
    value = content("C01")
    value["step_notes"].pop()
    with pytest.raises(AssertionError, match="FRAME_BINDING"):
        p.check_content("C01", value)
    value = content("C01")
    value["step_notes"][0]["frame_id"] = "wrong"
    with pytest.raises(AssertionError, match="FRAME_BINDING"):
        p.check_content("C01", value)


def test_complete_raw_before_invalid_json_parse(tmp_path):
    v = vault(tmp_path)
    raw = b"HTTP body with invalid JSON \xff {trailing"
    with pytest.raises(Exception):
        e.run(
            "C01",
            v,
            approval(),
            httpx.MockTransport(
                lambda req: httpx.Response(200, stream=httpx.ByteStream(raw))
            ),
            key="synthetic-only-key",
        )
    assert (
        e.decrypt(v / "C01-generate.raw.enc", Fernet((v / "raw.key").read_bytes()))
        == raw
    )
    assert (v / "STOP").exists() and (v / "ACTIVE").exists()
    assert not (v / "C01-generate.candidate.json").exists()


@pytest.mark.parametrize("phase", ["absent", "final_answer"])
def test_success_parent_repair_and_no_third_call(tmp_path, phase):
    v = vault(tmp_path)
    sent = []

    def respond(req):
        assert (
            req.url.host == "93.184.216.34"
            and req.headers["Host"] == "api.deepseek.com"
        )
        assert req.extensions["sni_hostname"] == "api.deepseek.com"
        sent.append(json.loads(req.content))
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                phased_envelope("C01", {} if phase == "absent" else {"phase": phase})
            ),
        )

    transport = httpx.MockTransport(respond)
    first = e.run("C01", v, approval(), transport, key="synthetic-only-key")
    (v / "C01-evaluation.json").write_text(
        json.dumps(
            dict(
                verdict="ordinary_wording_repair",
                candidate_digest=first["artifact_digest"],
                independent_evaluator="synthetic-test-only",
                issues=[
                    dict(
                        severity="minor",
                        area="difficulty",
                        quote="合成解析",
                        path=["questions", "caller_head", "explanation"],
                        reason="synthetic only",
                    )
                ],
            ),
            ensure_ascii=False,
        )
    )
    second = e.run("C01", v, approval(), transport, key="synthetic-only-key")
    assert second["parent_digest"] == first["artifact_digest"]
    supplied = json.loads(sent[-1]["input"][1]["content"])
    assert (
        supplied["original"] == first["raw_output"]
        and supplied["previous_candidate_digest"] == first["artifact_digest"]
    )
    with pytest.raises(AssertionError, match="SAMPLE_EXHAUSTED"):
        e.run("C01", v, approval(), transport, key="synthetic-only-key")
    assert len(sent) == 2 and (v / "STOP").exists()


def test_missing_body_blocks_next_stage(tmp_path):
    v = vault(tmp_path)
    first = e.run(
        "C01",
        v,
        approval(),
        httpx.MockTransport(
            lambda req: httpx.Response(200, stream=httpx.ByteStream(envelope("C01")))
        ),
        key="synthetic-only-key",
    )
    (v / "C01-generate.raw.enc").unlink()
    (v / "C01-evaluation.json").write_text(
        json.dumps(
            dict(
                verdict="ordinary_wording_repair",
                candidate_digest=first["artifact_digest"],
                independent_evaluator="synthetic",
                issues=[],
            )
        )
    )
    sent = []
    with pytest.raises(FileNotFoundError):
        e.run(
            "C01",
            v,
            approval(),
            httpx.MockTransport(lambda req: sent.append(req)),
            key="synthetic-only-key",
        )
    assert not sent and (v / "STOP").exists()


def test_c02_waits_for_actual_c01_evaluation(tmp_path):
    v = vault(tmp_path)
    sent = []
    with pytest.raises(FileNotFoundError):
        e.run(
            "C02",
            v,
            approval(),
            httpx.MockTransport(lambda req: sent.append(req)),
            key="synthetic-only-key",
        )
    assert not sent


def test_partial_encrypted_and_never_claim_complete(tmp_path):
    path = tmp_path / "body"
    cipher = Fernet(Fernet.generate_key())
    with pytest.raises(e.IncompleteEvidence):
        e.collect(
            httpx.Response(200, stream=httpx.ByteStream(b"1234567")),
            path,
            cipher,
            maximum=4,
        )
    assert e.decrypt(path, cipher) == b"1234"
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(e.IncompleteEvidence):
        e.decrypt(path, cipher)


def test_stop_and_expiry_refuse_before_transport(tmp_path):
    v = vault(tmp_path)
    auth = approval()
    auth["starts_epoch"] -= 1801
    auth["expires_epoch"] -= 1801
    with pytest.raises(AssertionError):
        e.run(
            "C01",
            v,
            auth,
            httpx.MockTransport(lambda req: pytest.fail("network")),
            key="synthetic-only-key",
        )
    (v / "STOP").touch()
    with pytest.raises(AssertionError, match="BATCH_STOPPED"):
        e.run(
            "C01",
            v,
            approval(),
            httpx.MockTransport(lambda req: pytest.fail("network")),
            key="synthetic-only-key",
        )


def test_same_entry_discloses_pause_then_late_send(tmp_path, monkeypatch):
    v = vault(tmp_path)
    sent = []
    clock = [time.time()]
    auth = approval()
    original = e.exclusive

    def pause_after_registration(path, raw):
        original(path, raw)
        if path.name.endswith(".request.json"):
            clock[0] = auth["expires_epoch"] + 1
            (v / "STOP").touch()  # Represents a stop while sender was paused.

    monkeypatch.setattr(e, "exclusive", pause_after_registration)
    monkeypatch.setattr(e.time, "time", lambda: clock[0])

    def transport(req):
        sent.append(clock[0])
        return httpx.Response(200, stream=httpx.ByteStream(envelope("C01")))

    with pytest.raises(e.IncompleteEvidence, match="LATE_BODY_PRESERVED_STOP"):
        e.run("C01", v, auth, httpx.MockTransport(transport), key="synthetic-only-key")
    assert len(sent) == 1 and sent[0] > auth["expires_epoch"]
    assert (v / "C01-generate.raw.enc").exists() and not (
        v / "C01-generate.candidate.json"
    ).exists()


def test_render_preserves_model_strings_and_escapes_script():
    value = content("C01")
    value["step_notes"][0]["note"] = "合成 </script><script>alert(1)</script>"
    page = p.render("C01", value)
    assert "<script>alert(1)</script>" not in page
    assert "\\u003c/script\\u003e" in page


def phased_envelope(slot, fields):
    value = json.loads(envelope(slot))
    value["output"][0].update(fields)
    # Noncanonical whitespace proves that stored originals are not normalization output.
    return b" \n" + json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n"


@pytest.mark.parametrize(
    "fields", [{}, {"phase": "final_answer"}], ids=["absent", "final_answer"]
)
def test_actual_entry_phase_success_preserves_original_and_replays(tmp_path, fields):
    v = vault(tmp_path)
    raw = phased_envelope("C01", fields)
    cipher = Fernet((v / "raw.key").read_bytes())
    candidate = e.run(
        "C01",
        v,
        approval(),
        httpx.MockTransport(
            lambda req: httpx.Response(200, stream=httpx.ByteStream(raw))
        ),
        key="synthetic-only-key",
    )
    assert e.decrypt(v / "C01-generate.raw.enc", cipher) == raw
    receipt = json.loads((v / "C01-generate.body.json").read_text())
    assert receipt["raw_bytes"] == len(raw)
    assert receipt["raw_sha256"] == e.hashlib.sha256(raw).hexdigest()
    assert e.verify_saved(v, "C01-generate", cipher) == candidate
    observation = json.loads((v / "C01-generate.result.json").read_text())[
        "observation"
    ]
    assert observation["message_phase"] == fields.get("phase", "absent")
    assert observation["phase_adapter_version"] == e.PHASE_ADAPTER_VERSION
    assert not (v / "STOP").exists() and not (v / "ACTIVE").exists()
    if fields:
        # The historical validator must continue rejecting this field outside this batch.
        with pytest.raises(p.wire.PilotError, match="^WIRE_MESSAGE$"):
            p.wire.validate(p.body("C01"), raw, "generation")


@pytest.mark.parametrize(
    "fields,code",
    [
        *[
            ({"phase": phase}, "WIRE_MESSAGE_PHASE")
            for phase in [
                "analysis",
                "commentary",
                "final",
                "final_answer ",
                "",
                None,
                0,
                False,
                [],
                {},
            ]
        ],
        ({"phase": "final_answer", "unexpected_metadata": True}, "WIRE_MESSAGE"),
    ],
)
def test_actual_entry_rejects_other_phases_and_unknown_fields(tmp_path, fields, code):
    v = vault(tmp_path)
    raw = phased_envelope("C01", fields)
    with pytest.raises(p.wire.PilotError, match="^" + code + "$"):
        e.run(
            "C01",
            v,
            approval(),
            httpx.MockTransport(
                lambda req: httpx.Response(200, stream=httpx.ByteStream(raw))
            ),
            key="synthetic-only-key",
        )
    assert (
        e.decrypt(v / "C01-generate.raw.enc", Fernet((v / "raw.key").read_bytes()))
        == raw
    )
    assert (v / "STOP").exists() and (v / "ACTIVE").exists()
    assert not (v / "C01-generate.candidate.json").exists()
    assert not (v / "C01-generate.course.html").exists()
