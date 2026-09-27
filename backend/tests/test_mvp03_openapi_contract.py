"""Validate the proposed MVP 0.3 OpenAPI contract before route implementation."""

import json
from pathlib import Path

SPEC = json.loads((Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml").read_text())


def _walk_refs(value: object) -> None:
    if isinstance(value, list):
        for item in value:
            _walk_refs(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref":
                assert isinstance(item, str) and item.startswith("#/components/")
                target: object = SPEC
                for segment in item[2:].split("/"):
                    assert isinstance(target, dict) and segment in target
                    target = target[segment]
            else:
                _walk_refs(item)


def _parameter_names(operation: dict[str, object]) -> set[str]:
    names = set()
    for parameter in operation.get("parameters", []):
        assert isinstance(parameter, dict)
        if "$ref" in parameter:
            name = parameter["$ref"].split("/")[-1]
            names.add(SPEC["components"]["parameters"][name]["name"])
        else:
            names.add(parameter["name"])
    return names


def test_all_refs_and_path_parameters_resolve() -> None:
    _walk_refs(SPEC)
    assert SPEC["info"]["version"] == "0.3.0"
    assert "设计契约" in SPEC["x-mvp-0.3-contract-status"]
    for path, methods in SPEC["paths"].items():
        for operation in methods.values():
            names = _parameter_names(operation)
            for segment in path.split("{")[1:]:
                assert segment.split("}")[0] in names
            assert "responses" in operation and "operationId" in operation


def test_mvp03_writes_are_owner_scoped_csrf_protected_and_idempotent() -> None:
    for path, methods in SPEC["paths"].items():
        if not any(path.startswith(prefix) for prefix in (
            "/api/animation-jobs/", "/api/learning-units/", "/api/animation-media/"
        )):
            continue
        for method, operation in methods.items():
            assert operation["security"] == [{"sessionCookie": []}]
            if method in {"post", "patch", "put", "delete"}:
                names = _parameter_names(operation)
                assert {"X-CSRF-Token", "Idempotency-Key"} <= names
                assert {"401", "403", "409"} <= set(operation["responses"])
                request = operation.get("requestBody", {})
                assert "user_id" not in json.dumps(request).lower()
    for suffix in ("/mode", "/messages", "/controls", "/debate", "/debate/{resultId}/exit"):
        method = "patch" if suffix == "/mode" else "post"
        operation = SPEC["paths"]["/api/learning-units/{learningUnitId}/classroom" + suffix][method]
        assert "If-Match-Classroom-Revision" in _parameter_names(operation)


def test_job_sse_replay_and_classroom_temporary_boundary() -> None:
    job = SPEC["paths"]["/api/animation-jobs/{jobId}/events"]["get"]
    assert "Last-Event-ID" in _parameter_names(job)
    assert {"409", "410"} <= set(job["responses"])
    assert "last_event_id" in job["description"]
    events = SPEC["x-animation-job-events"]
    expected = {"queued", "running", "progress", "succeeded", "failed", "cancelled", "recovered"}
    assert expected <= set(events)
    stream = SPEC["x-classroom-stream-events"]
    assert stream["token"]["data"]["temporary"] is True
    assert "content_retracted" in stream and "message_ready" in stream
    assert "message_cursor" in SPEC["components"]["schemas"]["ClassroomSnapshot"]["properties"]
    assert "scene_progress" in SPEC["components"]["schemas"]["ClassroomSnapshot"]["properties"]


def test_export_is_read_only_and_mvp03_errors_are_stable() -> None:
    paths = SPEC["paths"]
    assert set(paths["/api/learning-units/{learningUnitId}/notes.md"]) == {"get"}
    for extension in ("mp4", "srt"):
        assert set(paths[f"/api/animation-media/{{mediaId}}/{extension}"]) == {"get"}
    codes = set(SPEC["components"]["schemas"]["Error"]["properties"]["code"]["enum"])
    assert {"EVENT_CURSOR_EXPIRED", "CLASSROOM_VERSION_CONFLICT", "SCENE_VERSION_CONFLICT",
            "MEDIA_NOT_READY", "REVIEW_UNAVAILABLE", "RENDER_UNAVAILABLE"} <= codes
    assert "provider" not in json.dumps(SPEC["components"]["schemas"]["AnimationRequest"]).lower()


def test_model_generation_uses_post_sse_with_recoverable_operation_status() -> None:
    paths = SPEC["paths"]
    base = "/api/learning-units/{learningUnitId}/classroom"
    for suffix in ("/messages", "/scenes/{sceneKey}/reexplanations", "/debate"):
        operation = paths[base + suffix]["post"]
        assert "text/event-stream" in operation["responses"]["200"]["content"]
        assert "operation_id" in operation["description"]
    assert "agent_start" in SPEC["x-classroom-stream-events"]
    status = paths["/api/classroom-operations/{operationId}"]["get"]
    assert status["security"] == [{"sessionCookie": []}]
    assert "临时token不回放" in status["description"]


def test_download_headers_and_range_behavior_are_explicit() -> None:
    paths = SPEC["paths"]
    media = "/api/animation-media/{mediaId}/"
    for extension in ("mp4", "srt"):
        response = paths[media + extension]["get"]["responses"]["200"]
        assert {"Content-Disposition", "X-Content-Type-Options", "Cache-Control"} <= set(
            response["headers"]
        )
    assert "206" in paths[media + "mp4"]["get"]["responses"]
    assert "206" not in paths[media + "srt"]["get"]["responses"]
    notes = paths["/api/learning-units/{learningUnitId}/notes.md"]["get"]["responses"]["200"]
    assert "text/markdown; charset=utf-8" in notes["content"]
    assert "Content-Disposition" in notes["headers"]


def test_explicit_classroom_creation_and_inline_media_playback() -> None:
    paths = SPEC["paths"]
    classroom = paths["/api/learning-units/{learningUnitId}/classroom"]
    assert "post" in classroom and "get" in classroom
    create = classroom["post"]
    assert {"X-CSRF-Token", "Idempotency-Key"} <= _parameter_names(create)
    assert create["responses"]["201"]["content"]["application/json"]
    for extension in ("mp4", "srt"):
        media = paths[f"/api/animation-media/{{mediaId}}/{extension}"]["get"]
        assert "download" in _parameter_names(media)
        disposition = media["responses"]["200"]["headers"]["Content-Disposition"]
        assert "inline" in disposition["description"]
        assert "attachment" in disposition["description"]
