"""Replay the exact r02 source and exercise the narrow revision without outbound calls."""

import asyncio
import os
import time
from copy import deepcopy
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from jsonschema.exceptions import ValidationError
from test_head_course_fixed import fixed_review, with_direct_echo

from app.main import app
from app.services import head_course_citation_revision as revision
from app.services import head_course_evidence_publication as publication
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, canonical
from scripts import head_course_fact_revision as entry
from scripts import head_course_goal_fixture as fixture

OUTPUT = {revision.KEY: revision.AFTER}
pytestmark = pytest.mark.skipif(
    not (revision.entry.EMPTY_R02_VAULT / "STOP").is_file(),
    reason="Requires the local sealed T118 r02 source; real originals are not in Git",
)


def test_exact_source_and_leaf_only():
    parent, review = revision.source_original()
    assert review["verdict"] == "stop"
    child = revision.merge(parent, OUTPUT)
    restored = deepcopy(child["raw_output"])
    restored["paragraphs"][4]["fact_ids"] = revision.BEFORE
    assert restored == parent["raw_output"]
    assert child["payload"] == parent["payload"]
    assert child["parent_digest"] == revision.PARENT
    assert child["candidate_digest"] != revision.PARENT
    assert child["recovery"] is None


@pytest.mark.parametrize(
    "output",
    [
        {},
        {**OUTPUT, "text": "Rewritten"},
        {revision.KEY: [revision.AFTER[1]]},
        {revision.KEY: [revision.AFTER[0]] * 2},
        {revision.KEY: ["other_fact", revision.AFTER[1]]},
        {revision.KEY: list(reversed(revision.AFTER))},
    ],
)
def test_reject_scope_or_fact_changes(output):
    parent, _ = revision.source_original()
    with pytest.raises((ValidationError, SnapshotError)):
        revision.merge(parent, output)


def test_shared_entry_and_private_child(monkeypatch, tmp_path):
    url = os.environ.get("EDUMIND_TEST_DATABASE_URL", "")
    if not url.endswith("/" + revision.direct.EMPTY_R02_DATABASE):
        pytest.skip("Requires the dedicated T118 r02 PostgreSQL test environment")
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_HEAD_GOAL_DEVELOPMENT", "1")
    monkeypatch.setattr(entry, "f", revision)
    monkeypatch.setattr(entry, "PACKAGE", revision.PACKAGE)
    vault = tmp_path / "vault"
    vault.mkdir(mode=0o700)
    monkeypatch.setattr(entry, "VAULT", vault)
    entry.old.raw_io.exclusive(vault / "raw.key", Fernet.generate_key())
    stop_before = (revision.entry.EMPTY_R02_VAULT / "STOP").read_bytes()
    source = revision.entry.read(revision.entry.EMPTY_R02_VAULT / "context.json")
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        owner = UUID(auth["user"]["id"])
        start = int(time.time()) - 1
        approval = dict(
            manifest_sha256=entry.package_digest(),
            batch=revision.BATCH,
            owner=str(owner),
            parent_digest=revision.PARENT,
            original_review_sha256=revision.REVIEW,
            evidence_digest=revision.inputs()["teaching_evidence"]["evidence_digest"],
            protocol_version=revision.VERSION,
            explicit_user_authorization=True,
            max_http_requests=1,
            starts_epoch=start,
            expires_epoch=start + 600,
            **{revision.APPROVAL_KEY: True},
        )
        entry.old.raw_io.exclusive(vault / "approval.json", canonical(approval))
        calls = []

        def respond(request):
            calls.append(request.content)
            exact = revision.body()
            assert request.headers["Host"] == "api.deepseek.com"
            assert request.url.path == "/responses"
            assert request.content == canonical(exact)
            raw = with_direct_echo(exact, fixture.envelope(OUTPUT))
            return httpx.Response(200, stream=httpx.ByteStream(raw))

        mock = httpx.MockTransport(respond)
        with pytest.raises(SnapshotError, match="FACT_AUTHORIZATION_OR_STOP"):
            entry.send(
                vault,
                {**approval, "expires_epoch": start},
                transport=mock,
                key="fixture-only",
            )
        assert not calls
        entry.send(vault, approval, transport=mock, key="fixture-only")
        with pytest.raises(SnapshotError, match="FACT_AUTHORIZATION_OR_STOP"):
            entry.send(vault, approval, transport=mock, key="fixture-only")
        assert len(calls) == 1
        record = entry.read_saved(vault)
        child = record["candidate"]
        assert record["output"] == OUTPUT
        review = fixed_review(child)
        with pytest.raises(SnapshotError, match="REUSE_FULL_REVIEW_REQUIRED"):
            publication.assembled(record, review)
        review["checks"].update(
            empty_first_and_second_links=True, question_conditions_and_unique_answers=True
        )

        async def imported(db, as_owner):
            return await publication.import_course(db, as_owner, record, review)

        with pytest.raises(SnapshotError, match="CITATION_APPROVAL_BINDING"):
            asyncio.run(entry.old.database(lambda db: imported(db, uuid4())))
        result = asyncio.run(entry.old.database(lambda db: imported(db, owner)))
        assert asyncio.run(entry.old.database(lambda db: imported(db, owner))) == result
        assert result["version"] == 2 and result["course_id"] != source["course_id"]
        route = f"/api/free-courses/{result['course_id']}/versions/2/scenes/{result['scene_id']}"
        resp = client.get(route)
        assert resp.status_code == 200, resp.text
        assert "answer_key" not in resp.text and "solution" not in resp.text
        scene = resp.json()
        assert scene["generation_source"]["parent_digest"] == revision.PARENT
        assert scene["generation_source"]["batch"] == revision.BATCH
        assert scene["generation_source"]["evidence_kind"] == "offline_fixture"
        visual = next(b for b in scene["blocks"] if b["kind"] == "visualization")
        assert len(visual["steps"]) == 13
        assert visual["steps"][-1]["head_frame"]["state"]["caller_head"] == "t1"
        assert len(scene["blocks"][-1]["items"]) == 4

    async def old_state(db):
        repo = SnapshotRepository(db, UUID(source["owner"]))
        cid = UUID(source["course_id"])
        op = await repo._operation(cid, UUID(source["operation_id"]))
        return op.state, (await repo.get_course(cid))["head_version"]

    assert asyncio.run(entry.old.database(old_state)) == ("cancel_requested", 1)
    assert (revision.entry.EMPTY_R02_VAULT / "STOP").read_bytes() == stop_before
