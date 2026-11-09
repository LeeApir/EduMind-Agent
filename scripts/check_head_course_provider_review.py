"""Read-only T113 comparison. Emits field inventories and measurements, never raw text."""

from pathlib import Path

from app.services.free_course_snapshots import SnapshotError, canonical
from app.services.head_course_archived_import import mapping
from scripts import head_course_fixed_aiapi as aiapi
from scripts import head_course_fixed_aiapi_draft as draft
from scripts.head_course_fixed_continuation import cipher

ACCEPTANCE = Path(__file__).resolve().parents[1] / "docs/acceptance"
read, sha, wire = aiapi.read, aiapi.sha, aiapi.wire


def sealed(archive, vault, stage):
    manifest = read(archive / "originals-manifest.json")
    assert not vault.is_symlink() and not vault.stat().st_mode & 0o077
    assert manifest["vault"] == str(vault) and manifest["key_excluded"] is True
    assert {"STOP", "failure.json"} <= manifest["files"].keys()
    for name, expected in manifest["files"].items():
        path = vault / name
        assert not path.is_symlink() and sha(path.read_bytes()) == expected, name
    for name in ("STOP", "failure.json", f"{stage}.attempt.json", f"{stage}.body.json"):
        assert (archive / name).read_bytes() == (vault / name).read_bytes(), name
    request = (vault / f"{stage}.request.json").read_bytes()
    attempt = read(vault / f"{stage}.attempt.json")
    approval_file = archive / "approval.json"
    approval = read(approval_file)
    approved = approval["request_sha256"]
    assert (
        sha(request)
        == attempt["request_sha256"]
        == (approved[stage] if isinstance(approved, dict) else approved)
    )
    assert attempt["approval_sha256"] == sha(approval_file.read_bytes())
    assert (
        attempt["stage"] == stage
        and attempt["evidence_kind"] == "actual_provider_attempt"
    )
    assert attempt["model"] == approval["model"] == aiapi.MODEL
    assert attempt["endpoint"] == approval["endpoint"] == aiapi.ENDPOINT
    raw = aiapi.raw_io.decrypt(vault / f"{stage}.raw.enc", cipher(vault))
    assert read(vault / f"{stage}.body.json") == {
        "http_status": 200,
        "raw_bytes": len(raw),
        "raw_sha256": sha(raw),
        "body_complete": True,
    }
    return request, raw


def schema_changes(sent, reported, path=""):
    for key in sorted(sent.keys() | reported.keys()):
        pointer = f"{path}/{key}"
        if key not in reported:
            yield [pointer, "request_only"]
        elif key not in sent:
            yield [pointer, "response_only"]
        elif type(sent[key]) is dict and type(reported[key]) is dict:
            yield from schema_changes(sent[key], reported[key], pointer)
        elif type(sent[key]) is not type(reported[key]) or sent[key] != reported[key]:
            yield [pointer, "different_value"]


def observation(request_bytes, raw):
    request, response = map(wire.strict_json, (request_bytes, raw))
    (message,) = response["output"]
    (part,) = message["content"]
    system = request["input"][0]["content"]
    echo = response.get("instructions")
    echo_kind = (
        "absent"
        if "instructions" not in response
        else "null"
        if echo is None
        else "exact"
        if echo == system
        else "known_suffix"
        if echo == system + wire.SUFFIX
        else "other"
    )
    fields = (
        "model",
        "store",
        "stream",
        "temperature",
        "max_output_tokens",
        "reasoning",
        "status",
        "error",
        "incomplete_details",
        "background",
        "previous_response_id",
        "tool_choice",
        "parallel_tool_calls",
        "tools",
        "tool_usage",
        "max_tool_calls",
        "top_p",
        "top_logprobs",
        "frequency_penalty",
        "presence_penalty",
        "service_tier",
        "truncation",
        "prompt_cache_retention",
        "moderation",
        "access_programs",
        "image",
    )
    usage = response["usage"]
    return {
        "request_sha256": sha(request_bytes),
        "response_sha256": sha(raw),
        "response_bytes": len(raw),
        "request_keys": sorted(request),
        "response_keys": sorted(response),
        "message_keys": sorted(message),
        "text_part_keys": sorted(part),
        "message_phase": message.get("phase"),
        "instructions": echo_kind,
        "schema_echo_differences": list(
            schema_changes(request["text"], response["text"])
        ),
        "duplicate_output_text": (
            "absent"
            if "output_text" not in response
            else "exact"
            if response["output_text"] == part["text"]
            else "different"
        ),
        "requested_fields": {
            field: request[field] for field in fields if field in request
        },
        "reported_fields": {
            field: response[field] for field in fields if field in response
        },
        "usage_keys": sorted(usage),
        "usage": {
            key: usage[key]
            for key in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "input_tokens_details",
                "output_tokens_details",
            )
        },
    }


def main():
    plan_request, plan_raw = sealed(aiapi.ARCHIVE, aiapi.VAULT, "plan")
    draft_request, draft_raw = sealed(draft.ARCHIVE, draft.VAULT, "draft")
    assert draft_request == (aiapi.ARCHIVE / "draft1.request.json").read_bytes()
    assert read(aiapi.ARCHIVE / "failure.json")["code"] == "ReadTimeout"
    assert not (aiapi.VAULT / "draft1.headers.json").exists()
    assert not (aiapi.VAULT / "draft2.attempt.json").exists()
    aiapi.message(wire.strict_json(plan_request), plan_raw)
    try:
        aiapi.message(wire.strict_json(draft_request), draft_raw)
    except SnapshotError as error:
        assert (
            str(error)
            == read(draft.ARCHIVE / "failure.json")["code"]
            == "AIAPI_ENVELOPE"
        )
    else:
        raise AssertionError(
            "r05 unexpectedly accepted by the historical generation adapter"
        )
    record, _ = mapping()
    assert (
        record["review"]["verdict"] == "pass"
        and record["review"]["admission_eligible"] is False
    )

    samples = {}
    for folder, stage in (
        ("head-fixed-live-r01", "plan"),
        ("head-fixed-repeat-r03", "repeat"),
    ):
        archive = ACCEPTANCE / f"phase-1.5-{folder}"
        request = (archive / f"{stage}.request.json").read_bytes()
        raw = (archive / f"{stage}.raw.json").read_bytes()
        receipt = read(archive / f"{stage}.body.json")
        assert (receipt["raw_bytes"], receipt["raw_sha256"]) == (len(raw), sha(raw))
        aiapi.raw_io.observe_generation(wire.strict_json(request), raw)
        samples[folder] = observation(request, raw)
    s2 = read(ACCEPTANCE / "phase-1.5-aiapi-s2-once/results.json")
    request_cap = read(ACCEPTANCE / "phase-1.5-aiapi-minimal-r01/S2.json")[
        "max_output_tokens"
    ]
    (terminal,) = (
        event["response"]
        for event in s2["events"]
        if event["type"] == "response.completed"
    )
    assert terminal["usage"]["output_tokens"] > request_cap

    return {
        "provider_calls": 0,
        "aiapi_r04_plan": observation(plan_request, plan_raw),
        "aiapi_r05_draft": observation(draft_request, draft_raw),
        "aiapi_earlier_stream_s2": {
            "requested_output_cap": request_cap,
            "reported_output_tokens": terminal["usage"]["output_tokens"],
            "reported_reasoning_tokens": terminal["usage"]["output_tokens_details"][
                "reasoning_tokens"
            ],
            "missing_final_fields": s2["missing_final_fields"],
        },
        "deepseek_comparison": samples,
    }


if __name__ == "__main__":
    print(canonical(main()).decode())
