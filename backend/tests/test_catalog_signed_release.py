"""Actual Lee signature, real isolated PostgreSQL/REST, no Provider or synthetic media."""

import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.main import app
from app.models.catalog import CatalogRelease
from app.models.learning import GeneratedResource
from app.services.animation_cache import AnimationCache
from app.services.catalog_package import CatalogError, content_digest, load_package, read_json
from app.services.catalog_publication import publish_catalog, revoke_catalog

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_catalog_release import trusted_release, verify  # noqa: E402

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
OUTPUT = os.getenv("EDUMIND_CATALOG_SIGNED_RESULT")
pytestmark = pytest.mark.skipif(
    not URL or not OUTPUT, reason="explicit signed-release runner required"
)


def test_actual_signed_version_core_journey_and_withdrawal(monkeypatch):
    directory = ROOT / "data/course_catalog/linear-v1"
    digest, approval_path = trusted_release(
        directory, ROOT / "data/course_catalog/release-allowlist.json"
    )
    assert verify(directory, digest, approval_path)["publishable"]
    package, approval = load_package(directory), read_json(approval_path)
    result = {
        "manifest_digest": digest,
        "reviewer": approval["reviewer"],
        "approval": approval,
        "provider_requests": 0,
        "external_attempts": [],
        "transport": (
            "FastAPI HTTPS TestClient + real isolated PostgreSQL; not a new browser benchmark"
        ),
        "database": URL.rsplit("/", 1)[-1],
        "checks": [],
        "nodes": [],
        "media": [],
        "production_published": False,
        "passed": False,
    }
    assert result["database"].startswith("edumind_catalog_signed_")
    output = Path(OUTPUT)

    def save():
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    def forbidden(*_args, **_kwargs):
        pytest.fail("No Provider construction permitted")

    original_connect = socket.socket.connect

    def guarded_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
            result["external_attempts"].append(str(address[0]))
            save()
            pytest.fail("External network prohibited")
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr("app.core.provider_factory.build_default_provider_gateway", forbidden)
    monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    monkeypatch.delenv("EDUMIND_PROVIDER_API_KEY", raising=False)
    # Existing T045 real-render cache only; a miss must fail, never silently render fake media.
    cache_root = Path(
        os.environ.get(
            "EDUMIND_SIGNED_CACHE_ROOT", "/private/tmp/edumind-catalog-quality-20261003-v2"
        )
    )
    cache = AnimationCache(cache_root, renderer=forbidden)
    monkeypatch.setattr("app.api.animation_jobs.AnimationCache", lambda: cache)
    monkeypatch.setattr("app.api.animation_media.AnimationCache", lambda: cache)

    async def database(action, release_id=None):
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                if action == "publish":
                    with pytest.raises(CatalogError):
                        await publish_catalog(
                            db, package, approval=approval, trusted_digest="0" * 64
                        )
                    release = await publish_catalog(
                        db, package, approval=approval, trusted_digest=digest
                    )
                    same = await publish_catalog(
                        db, package, approval=approval, trusted_digest=digest
                    )
                    assert same.id == release.id and release.approval == approval
                    await db.commit()
                    return str(release.id)
                if action == "provenance":
                    resources = list(
                        (
                            await db.scalars(
                                select(GeneratedResource).where(
                                    GeneratedResource.catalog_release_id == UUID(release_id)
                                )
                            )
                        ).all()
                    )
                    assert len(resources) == 30
                    for resource in resources:
                        assert resource.origin_type == "curated"
                        expected = package.nodes[resource.knowledge_point_id][
                            resource.resource_type
                        ]
                        assert resource.content == expected
                        assert resource.catalog_content_digest == content_digest(expected)
                    return
                await revoke_catalog(db, UUID(release_id))
                await db.commit()
                release = await db.get(CatalogRelease, UUID(release_id))
                assert release.status == "revoked" and release.revoked_at is not None
                with pytest.raises(CatalogError, match="CATALOG_VERSION_CONFLICT"):
                    await publish_catalog(db, package, approval=approval, trusted_digest=digest)
        finally:
            await engine.dispose()

    try:
        release_id = asyncio.run(database("publish"))
        result["release_id"] = release_id
        result["checks"].append(
            "exact signed publication, unauthorized digest refusal, idempotent registration"
        )
        save()
        with TestClient(app, base_url="https://testserver") as client:
            assert client.get("/api/catalog").status_code == 401
            guest = client.post("/api/auth/guest").json()
            headers = {"X-CSRF-Token": guest["csrf_token"]}

            def post(path, body=None, **extra):
                return client.post(
                    path, json=body, headers={**headers, "Idempotency-Key": uuid4().hex, **extra}
                )

            listing = client.get("/api/catalog").json()["releases"]
            assert len(listing) == 1 and listing[0]["id"] == release_id
            units, quizzes = {}, {}
            for node, content in package.nodes.items():
                enrollment = post(
                    "/api/catalog/sessions", {"release_id": release_id, "node_id": node}
                )
                assert enrollment.status_code == 201, enrollment.text
                unit = enrollment.json()["learning_unit_id"]
                units[node] = unit
                unit_path = f"/api/learning-units/{unit}"
                body = client.get(unit_path).json()
                assert body["catalog_release_id"] == release_id and body["origin_type"] == "curated"
                resources = body["scenes"][0]["resources"]
                assert len(resources) == 3
                for resource in resources:
                    if resource["type"] != "exercise":
                        assert resource["content"] == content[resource["type"]]
                quiz = next(r for r in resources if r["type"] == "exercise")
                quizzes[node] = quiz["id"]
                assert all(set(q) == {"id", "question"} for q in quiz["content"]["items"])
                answers = [
                    {"question_id": q["id"], "answer": q["answer"]}
                    for q in content["exercise"]["items"]
                ]
                submission = {"resource_id": quiz["id"], "resource_version": 1, "answers": answers}
                first = post("/api/quiz-submissions", submission)
                assert first.status_code == 200, first.text
                first = first.json()
                assert (
                    first["correct_count"] == 3
                    and first["catalog_assessment"]["reason"] == "first_complete"
                )
                repeat = post("/api/quiz-submissions", submission).json()
                assert (
                    repeat["catalog_assessment"]["reason"] == "repeat"
                    and repeat["mastery_changes"] == []
                )
                notes = client.get(unit_path + "/notes.md")
                assert notes.status_code == 200
                assert "Lee" in notes.text and approval["reviewed_at"] in notes.text
                assert "TEST" not in notes.text
                result["nodes"].append(
                    {
                        "node_id": node,
                        "unit_id": unit,
                        "resource_count": 3,
                        "correct_count": 3,
                        "repeat_mastery_changes": [],
                    }
                )
                save()
            asyncio.run(database("provenance", release_id))
            result["checks"].append(
                "10 nodes/30 exact signed resources/30 correct answers; "
                "repeat cannot inflate mastery; signed notes"
            )
            demo = f"/api/catalog/learning-units/{units['array']}/demo"
            classroom = f"/api/learning-units/{units['array']}/classroom"
            assert post(classroom).status_code == 201
            assert client.get(demo).json()["script"] == package.demo
            assert (
                post(
                    demo,
                    {"action": "begin", "return_resource_type": "exercise"},
                    **{"If-Match-Classroom-Revision": "1"},
                ).status_code
                == 200
            )
            assert client.get(demo).json()["classroom"]["detour"]["kind"] == "catalog_demo"
            exit_response = post(demo, {"action": "exit"}, **{"If-Match-Classroom-Revision": "2"})
            assert (
                exit_response.status_code == 200
                and exit_response.json()["return_resource_type"] == "exercise"
            )
            result["checks"].append("approved preset begin/reload/exit returns to exercises")
            for template in ("linked-list-insertion", "linked-list-deletion"):
                parameters = {"values": [1, 3, 5], "index": 1}
                if template.endswith("insertion"):
                    parameters["value"] = 4
                animation = post(
                    f"/api/learning-units/{units[template]}/animations",
                    {
                        "template_id": template,
                        "template_version": "1.0.0",
                        "scene_version": 1,
                        "parameters": parameters,
                    },
                )
                assert animation.status_code == 200, animation.text
                media_id = animation.json()["media_id"]
                assert media_id
                for suffix in ("mp4", "srt"):
                    response = client.get(f"/api/animation-media/{media_id}/{suffix}?download=true")
                    assert response.status_code == 200 and len(response.content) > 20
                    result["media"].append(
                        {
                            "template": template,
                            "media_id": media_id,
                            "format": suffix,
                            "bytes": len(response.content),
                        }
                    )
            with TestClient(app, base_url="https://testserver") as other:
                other.post("/api/auth/guest")
                assert other.get(f"/api/learning-units/{units['array']}").status_code == 404
                assert other.get(demo).status_code == 404
                assert other.get(f"/api/animation-media/{media_id}/mp4").status_code == 404
            assert (
                client.post(
                    "/api/catalog/sessions", json={"release_id": release_id, "node_id": "array"}
                ).status_code
                == 403
            )
            result["checks"].append(
                "two real cached animations and MP4/SRT; foreign owner 404 and missing CSRF 403"
            )
            asyncio.run(database("revoke", release_id))
            for unit in units.values():
                assert client.get(f"/api/learning-units/{unit}").status_code == 404
                assert client.get(f"/api/learning-units/{unit}/notes.md").status_code == 404
            assert client.get(demo).status_code == 404
            for media in result["media"]:
                assert (
                    client.get(
                        f"/api/animation-media/{media['media_id']}/{media['format']}"
                    ).status_code
                    == 404
                )
            assert (
                post(
                    "/api/quiz-submissions",
                    {
                        "resource_id": quizzes["array"],
                        "resource_version": 1,
                        "answers": [
                            {"question_id": q["id"], "answer": q["answer"]}
                            for q in package.nodes["array"]["exercise"]["items"]
                        ],
                    },
                ).status_code
                == 404
            )
            assert (
                post(
                    "/api/catalog/sessions", {"release_id": release_id, "node_id": "array"}
                ).status_code
                == 409
            )
            assert client.get("/api/catalog").json()["releases"] == []
            result["checks"].append(
                "withdrawal denies all resources/notes/demo/media/new scoring/"
                "enrollment and reapproval"
            )
        result["passed"] = True
    finally:
        save()
