"""Bounded pipeline with real local compile/review; Provider calls are Fake/Mock only."""

import asyncio
import copy
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from test_provider_connections_api import setup_api  # noqa: F401 -- real PG fixture

from app.agents.animation_dsl_generation import AnimationDSLGenerator, GenerationCall
from app.agents.animation_dsl_review import (
    AnimationDSLReviewAgent,
    DSLReference,
    ModelSource,
    ReviewCall,
    canonical,
    digest,
)
from app.services.animation_cache import CachedAnimation
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    StructuredResult,
    TaskProfile,
)
from app.services.video_dsl_generation import VideoDSLPlanner, VideoIntent

ROOT = Path(__file__).resolve().parents[2]
RAW = (ROOT / "docs/agents/animation-dsl-v1/valid-all-actions.json").read_text()
GEN = ModelSource("openai-compatible", "generation-model", "adapter-v1", "cap-v1", "a" * 64)
REV = replace(GEN, model_id="review-model", target_sha256="b" * 64)
PASS = {"review_version": "animation-dsl-review-v1", "verdict": "pass", "issues": []}
REVISE = {
    **PASS,
    "verdict": "revise",
    "issues": [
        {
            "area": "complexity",
            "severity": "major",
            "action_index": 10,
            "message": "Give a truthful complexity justification.",
        }
    ],
}


def reference(kp="arrays"):
    target = {"scene_version": 1}
    return DSLReference(
        canonical(
            {
                "context_version": "animation-dsl-reference-v1",
                "target": target,
                "graph_version": "synthetic-v1",
                "node": {
                    "id": kp,
                    "description": "Public teaching facts.",
                    "learning_objectives": ["Explain operations and integer values."],
                },
                "prerequisites": [],
                "known_profile": {},
            }
        ),
        digest(target),
        "e" * 64,
        kp,
    )


def candidate(kp="arrays", caption=None):
    value = json.loads(RAW)
    value["knowledge_point_id"] = kp
    if caption:
        value["actions"][0]["caption"] = caption
    return canonical(value).encode()


class FakeGeneration:
    def __init__(self, raws=None, error=None, sources=None):
        self.raws = raws or [candidate()]
        self.error, self.sources = error, sources or [GEN]
        self.calls = []

    async def generate_candidate(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        index = len(self.calls) - 1
        return GenerationCall(
            self.raws[min(index, len(self.raws) - 1)],
            self.sources[min(index, len(self.sources) - 1)],
        )


class FakeReview:
    def __init__(self, values=None, error=None):
        self.values, self.error, self.calls = values or [PASS], error, []

    async def review_structured(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        value = self.values[min(len(self.calls) - 1, len(self.values) - 1)]
        return ReviewCall(StructuredResult(copy.deepcopy(value), REV.model_id), REV)


def planner(monkeypatch, gen=None, rev=None, cache=None):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    gen, rev = gen or FakeGeneration(), rev or FakeReview()
    return (
        VideoDSLPlanner(AnimationDSLGenerator(gen, AnimationDSLReviewAgent(rev)), cache=cache),
        gen,
        rev,
    )


def run(plan, intent=None, *, dynamic=True, ref=None):
    intent = intent or VideoIntent("arrays", "compare", '{"values":[1,2]}')
    return asyncio.run(
        plan.plan(
            intent, reference=ref or reference(intent.knowledge_point_id), dynamic_allowed=dynamic
        )
    )


def test_complete_generation_independent_review_and_no_media_success(monkeypatch):
    plan, gen, rev = planner(monkeypatch)
    result = run(plan)
    assert result.source == "generated_dsl" and result.outcome.approved and result.media is None
    assert result.candidates == 1 and len(gen.calls) == len(rev.calls) == 1
    assert gen.calls[0].prompt.task_profile is TaskProfile.QUALITY
    assert rev.calls[0].prompt.task_profile is TaskProfile.REVIEW
    sent = json.loads(gen.calls[0].prompt.messages[1].content)
    reviewed = json.loads(rev.calls[0].prompt.messages[1].content)
    assert reviewed["intent"] == sent["intent"]
    assert reviewed["intent"]["parameters"] == {"values": [1, 2]}
    assert "frames" in reviewed and "compiled_source" not in reviewed
    assert result.outcome.generation_source.source.model_id != result.outcome.review_source.model_id
    assert len(result.outcome.generation_source.prompt_sha256) == 64


@pytest.mark.parametrize(
    "operation,kp,params",
    [
        ("insert", "linked-list-insertion", {"values": [1], "index": 1, "value": 2}),
        ("delete", "linked-list-deletion", {"values": [1], "index": 0}),
    ],
)
def test_applicable_template_without_model_calls(monkeypatch, operation, kp, params):
    plan, gen, rev = planner(monkeypatch)
    result = run(plan, VideoIntent(kp, operation, canonical(params)))
    assert result.source == "parameterized_template" and result.template_id == kp
    assert json.loads(result.parameters_json) == params and not gen.calls and not rev.calls


def test_cache_first_and_corrupt_cache_falls_back_to_template(monkeypatch, tmp_path):
    hit = CachedAnimation(
        "a" * 64,
        "linked-list-insertion",
        "1.0.0",
        tmp_path / "a.mp4",
        tmp_path / "a.srt",
        "b" * 64,
        "c" * 64,
        36,
        True,
    )

    class Cache:
        valid = True

        def lookup(self, *args):
            return hit

        def validate(self, *args):
            return self.valid

    cache = Cache()
    plan, gen, rev = planner(monkeypatch, cache=cache)
    intent = VideoIntent("linked-list-insertion", "insert", '{"values":[],"index":0,"value":7}')
    result = run(plan, intent)
    assert result.source == "reviewed_cache" and result.media is hit
    cache.valid = False
    assert run(plan, intent).source == "parameterized_template"
    assert not gen.calls and not rev.calls


@pytest.mark.parametrize(
    "error",
    [
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.INVALID_OUTPUT,
        ProviderErrorCode.CAPABILITY_UNAVAILABLE,
    ],
)
def test_generation_failure_single_attempt_no_other_goal_template(monkeypatch, error):
    plan, gen, rev = planner(monkeypatch, gen=FakeGeneration(error=ProviderError(error)))
    result = run(plan)
    assert result.source == "unavailable" and len(gen.calls) == 1 and not rev.calls
    assert result.template_id is None and result.outcome is None


def test_failed_detailed_presentation_retains_exact_goal_and_marks_degradation(monkeypatch):
    intent = VideoIntent(
        "linked-list-insertion", "insert", '{"values":[1,2],"index":1,"value":7}', "detailed_trace"
    )
    plan, gen, rev = planner(
        monkeypatch, gen=FakeGeneration(error=ProviderError(ProviderErrorCode.TIMEOUT))
    )
    result = run(plan, intent)
    assert result.source == "template_fallback" and result.template_id == intent.knowledge_point_id
    assert json.loads(result.parameters_json) == json.loads(intent.parameters_json)
    assert (
        result.omitted_presentation == "detailed_trace"
        and result.error_code == "DSL_GENERATION_UNAVAILABLE"
    )
    assert result.media is None and result.outcome is None and len(gen.calls) == 1 and not rev.calls


@pytest.mark.parametrize("verdict", ["reject", "revise"])
def test_reject_terminates_and_revise_allows_only_two_corrections(monkeypatch, verdict):
    value = {**REVISE, "verdict": verdict}
    plan, gen, rev = planner(monkeypatch, rev=FakeReview([value]))
    result = run(plan)
    expected = 1 if verdict == "reject" else 3
    assert result.source == "unavailable" and result.error_code == "DSL_REVIEW_REJECTED"
    assert len(gen.calls) == len(rev.calls) == expected and result.candidates == expected
    if verdict == "revise":
        for request in gen.calls[1:]:
            payload = json.loads(request.prompt.messages[1].content)
            assert payload["correction"]["issues"] == REVISE["issues"]
            assert payload["correction"]["candidate"] == json.loads(candidate())


def test_correction_fresh_pass_binds_new_candidate_and_input(monkeypatch):
    plan, gen, rev = planner(
        monkeypatch,
        gen=FakeGeneration([candidate(), candidate(caption="创建第一个整数节点。")]),
        rev=FakeReview([REVISE, PASS]),
    )
    result = run(plan)
    assert result.source == "generated_dsl" and result.candidates == 2
    assert len(rev.calls) == 2
    assert (
        json.loads(rev.calls[1].prompt.messages[1].content)["dsl"]["actions"][0]["caption"]
        == "创建第一个整数节点。"
    )
    assert (
        result.outcome.compiled.validated.candidate["actions"][0]["caption"]
        == "创建第一个整数节点。"
    )


@pytest.mark.parametrize(
    "value",
    [
        {**PASS, "verdict": "unknown"},
        {**REVISE, "issues": [{**REVISE["issues"][0], "message": "sk-secretvalue123"}]},
    ],
)
def test_unavailable_or_unsafe_review_never_corrected(monkeypatch, value):
    plan, gen, rev = planner(monkeypatch, rev=FakeReview([value]))
    result = run(plan)
    assert result.error_code == "DSL_REVIEW_UNAVAILABLE" and len(gen.calls) == len(rev.calls) == 1


@pytest.mark.parametrize(
    "raw", [b"{}", b'{"schema_version":1,"schema_version":2}', b"```python\nexec(1)\n```", b"\xff"]
)
def test_invalid_local_candidate_never_sent_to_review(monkeypatch, raw):
    plan, gen, rev = planner(monkeypatch, gen=FakeGeneration([raw]))
    result = run(plan)
    assert result.source == "unavailable" and result.error_code == "DSL_SCHEMA_INVALID"
    assert len(gen.calls) == 1 and not rev.calls


def test_same_provider_model_target_required_through_correction(monkeypatch):
    plan, gen, rev = planner(
        monkeypatch,
        gen=FakeGeneration(sources=[GEN, replace(GEN, target_sha256="f" * 64)]),
        rev=FakeReview([REVISE]),
    )
    result = run(plan)
    assert result.error_code == "DSL_TARGET_CHANGED" and len(gen.calls) == 2 and len(rev.calls) == 1


@pytest.mark.parametrize(
    "params",
    [
        '{"values":[true]}',
        '{"values":[1.0]}',
        '{"values":[1000]}',
        '{"values":[1],"code":"exec(1)"}',
        '{"values":"private"}',
        '{"values":[],"values":[1,2]}',
        '{"values":[1]}',
    ],
)
def test_bad_intent_fails_before_any_call(monkeypatch, params):
    plan, gen, rev = planner(monkeypatch)
    result = run(plan, VideoIntent("arrays", "compare", params))
    assert result.error_code == "DSL_INTENT_INVALID" and not gen.calls and not rev.calls


def test_target_mismatch_no_call(monkeypatch):
    plan, gen, rev = planner(monkeypatch)
    assert run(plan, ref=reference("linked-list-insertion")).error_code == "DSL_INTENT_INVALID"
    assert not gen.calls and not rev.calls


@pytest.mark.parametrize("catalog,dynamic", [(True, True), (False, False)])
def test_default_generation_permission_and_catalog_fail_closed(monkeypatch, catalog, dynamic):
    plan, gen, rev = planner(monkeypatch)
    if catalog:
        monkeypatch.delenv("EDUMIND_PRODUCT_MODE")
    assert run(plan, dynamic=dynamic).source == "unavailable" and not gen.calls and not rev.calls


def test_no_template_for_outside_template_parameter_range(monkeypatch):
    intent = VideoIntent("linked-list-insertion", "insert", '{"values":[100],"index":1,"value":7}')
    plan, gen, rev = planner(
        monkeypatch, gen=FakeGeneration(error=ProviderError(ProviderErrorCode.TIMEOUT))
    )
    assert run(plan, intent).source == "unavailable" and len(gen.calls) == 1


def test_real_async_timeout_bounds_generation(monkeypatch):
    class Waiting(FakeGeneration):
        async def generate_candidate(self, request):
            self.calls.append(request)
            await asyncio.sleep(60)

    gen = Waiting()
    plan, gen, rev = planner(monkeypatch, gen=gen)
    timeout = asyncio.timeout
    monkeypatch.setattr(asyncio, "timeout", lambda seconds: timeout(min(seconds, 0.03)))
    result = run(plan)
    assert (
        result.error_code == "DSL_GENERATION_UNAVAILABLE" and len(gen.calls) == 1 and not rev.calls
    )


def test_cancellation_propagates_without_degradation(monkeypatch):
    class Waiting(FakeGeneration):
        async def generate_candidate(self, request):
            self.calls.append(request)
            await asyncio.sleep(60)

    gen = Waiting()
    plan, gen, rev = planner(monkeypatch, gen=gen)

    async def exercise():
        task = asyncio.create_task(
            plan.plan(
                VideoIntent("arrays", "compare", '{"values":[1,2]}'),
                reference=reference(),
                dynamic_allowed=True,
            )
        )
        while not gen.calls:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert len(gen.calls) == 1 and not rev.calls


@pytest.mark.skipif(
    not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="isolated PostgreSQL required"
)
@pytest.mark.parametrize(
    "structured,deny,changed",
    [
        (True, None, False),
        (False, None, False),
        (True, "generation", False),
        (True, "review", False),
        (True, None, True),
    ],
)
def test_pg_selected_pipeline_mock_transport_and_candidate_qualification(
    setup_api,  # noqa: F811 -- shared real PG fixture
    monkeypatch,
    structured,
    deny,
    changed,
):
    from uuid import UUID, uuid4

    import httpx
    from test_model_preferences import internal
    from test_provider_connection_test_api import ORIGINAL_SEND, create, output
    from test_provider_connections_api import guest

    from app.core.credential_crypto import CredentialFailure
    from app.models.learning import LearningScene, LearningUnit
    from app.services.animation_dsl_candidates import (
        admit_current_policy,
        build_dsl_reference,
        qualified_candidate,
        save_dsl_review,
    )
    from app.services.animation_dsl_generation_gateway import SelectedDSLGenerationGateway
    from app.services.animation_dsl_review_gateway import SelectedDSLReviewGateway
    from app.services.knowledge_graph import KnowledgeGraphRepository
    from app.services.provider_connection_dispatch import (
        ConnectionConsent,
        ConnectionRoute,
        DispatchRequest,
        ModelCapabilities,
    )

    client, users, _ = setup_api
    token, headers = guest(client, users)
    cid = create(client, headers)
    for profile, model, categories in [
        ("quality", "generation-model", ["learning_goal", "content_for_review"]),
        ("review", "review-model", ["content_for_review"]),
    ]:
        response = client.put(
            "/api/model-preferences/" + profile,
            headers=headers,
            json={
                "expected_version": 0,
                "route": {
                    "connection_id": cid,
                    "config_version": 1,
                    "model_id": model,
                    "data_categories": categories,
                },
                "fallbacks": [],
                "consent_accepted": True,
            },
        )
        assert response.status_code == 200, response.text
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    sent = []
    attempts = []

    async def authorize(request):
        attempts.append(request.route.model_id)
        if (deny == "generation" and request.route.model_id == "generation-model") or (
            deny == "review" and request.route.model_id == "review-model"
        ):
            raise CredentialFailure("BUDGET_NOT_AUTHORIZED")

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        value = output(
            candidate("array").decode() if body["model"] == "generation-model" else json.dumps(PASS)
        )
        value["model"] = body["model"]
        return httpx.Response(200, json=value)

    monkeypatch.setattr(httpx.AsyncClient, "send", ORIGINAL_SEND)
    graph = KnowledgeGraphRepository.from_file(ROOT / "data/knowledge_graph.yaml")

    async def exercise(store, identity):
        async with store.factory() as db, db.begin():
            await admit_current_policy(db)
            unit = LearningUnit(
                user_id=identity.user_id, knowledge_point_id="array", status="ready"
            )
            db.add(unit)
            await db.flush()
            scene = LearningScene(
                learning_unit_id=unit.id,
                scene_key="animation",
                scene_order=1,
                scene_type="video",
                version=1,
                generation_status="complete",
                review_status="passed",
            )
            db.add(scene)
            await db.flush()
            ref = await build_dsl_reference(
                db, graph, owner=identity.user_id, unit_id=unit.id, scene_id=scene.id, version=1
            )
            unit_id, scene_id = unit.id, scene.id

        def dispatch(model, categories, structured):
            route = ConnectionRoute(UUID(cid), 1, model, frozenset(categories))
            return DispatchRequest(
                identity,
                route,
                ConnectionConsent(route, True),
                ModelCapabilities(
                    UUID(cid), 1, model, "explicit-mock-v1", structured_output=structured
                ),
                uuid4(),
            )

        quality = dispatch(
            "other-model" if changed else "generation-model",
            ["learning_goal", "content_for_review"],
            structured,
        )
        review = dispatch("review-model", ["content_for_review"], True)
        transport = httpx.MockTransport(handler)
        generator = AnimationDSLGenerator(
            SelectedDSLGenerationGateway(store, quality, authorize, transport=transport),
            AnimationDSLReviewAgent(
                SelectedDSLReviewGateway(store, review, authorize, transport=transport)
            ),
        )
        result = await VideoDSLPlanner(generator).plan(
            VideoIntent("array", "compare", '{"values":[1,2]}'), reference=ref, dynamic_allowed=True
        )
        if result.outcome is not None:
            async with store.factory() as db, db.begin():
                record, saved = await save_dsl_review(
                    db,
                    graph,
                    owner=identity.user_id,
                    unit_id=unit_id,
                    scene_id=scene_id,
                    version=1,
                    outcome=result.outcome,
                )
                checked = await qualified_candidate(
                    db, graph, owner=identity.user_id, candidate_id=saved.id
                )
                candidate_id = checked.id
                assert checked.dsl_sha256 == result.outcome.compiled.validated.dsl_sha256
                assert (
                    record.evidence["generation"]["prompt_sha256"]
                    == result.outcome.generation_source.prompt_sha256
                )
            from app.services.animation_dsl_candidate_cache import ReviewedDSLCandidateCache
            from app.services.animation_dsl_candidates import revoke_candidate

            cache = ReviewedDSLCandidateCache(store.factory, graph, owner=identity.user_id)
            current_intent = VideoIntent("array", "compare", '{"values":[1,2]}')
            cached = await cache.lookup(current_intent, ref)
            assert cached is not None and cached.binding_sha256 == result.outcome.binding_sha256
            cache_plan = await VideoDSLPlanner(generator, reviewed_cache=cache).plan(
                current_intent, reference=ref, dynamic_allowed=True
            )
            assert cache_plan.source == "reviewed_dsl_cache" and cache_plan.candidates == 0
            assert cache_plan.media is None and len(sent) == 2
            assert (
                await cache.lookup(VideoIntent("array", "compare", '{"values":[2,1]}'), ref) is None
            )
            other_cache = ReviewedDSLCandidateCache(store.factory, graph, owner=uuid4())
            assert await other_cache.lookup(current_intent, ref) is None
            async with store.factory() as db, db.begin():
                await revoke_candidate(db, graph, owner=identity.user_id, candidate_id=candidate_id)
            assert await cache.lookup(current_intent, ref) is None
        return result

    result = internal(users, token, exercise)
    if deny or changed:
        assert result.source == "unavailable" and result.outcome is None
        assert len(sent) == (1 if deny == "review" else 0)
        if changed:
            assert not attempts
    else:
        assert (
            result.source == "generated_dsl"
            and len(sent) == 2
            and attempts == ["generation-model", "review-model"]
        )
        assert ("response_format" in sent[0]) is structured
        assert result.outcome.generation_source.source.adapter_version.startswith("sha256:")
        assert "provider.test" not in canonical(sent[1]["messages"])
        assert "intent" in json.loads(sent[1]["messages"][1]["content"])


@pytest.mark.parametrize("failure", ["validation", "review", "compile"])
def test_every_failure_uses_only_same_goal_reviewed_template(monkeypatch, failure):
    from app.agents import animation_dsl_review
    from app.services.animation_dsl_compiler import DSLCompileError

    intent = VideoIntent(
        "linked-list-insertion", "insert", '{"values":[1],"index":1,"value":7}', "detailed_trace"
    )
    gen = FakeGeneration(
        [b"{}" if failure == "validation" else candidate(intent.knowledge_point_id)]
    )
    rev = FakeReview([{**REVISE, "verdict": "reject"}])
    if failure == "compile":

        def reject(*args, **kwargs):
            raise DSLCompileError("DSL_COMPILE_REJECTED")

        monkeypatch.setattr(animation_dsl_review, "compile_animation_dsl", reject)
    plan, gen, rev = planner(monkeypatch, gen=gen, rev=rev)
    result = run(plan, intent)
    assert result.source == "template_fallback" and result.template_id == intent.knowledge_point_id
    assert json.loads(result.parameters_json) == json.loads(intent.parameters_json)
    assert (
        result.error_code
        == {
            "validation": "DSL_SCHEMA_INVALID",
            "review": "DSL_REVIEW_REJECTED",
            "compile": "DSL_COMPILE_REJECTED",
        }[failure]
    )
    assert len(gen.calls) == 1 and len(rev.calls) == (1 if failure == "review" else 0)


def test_intent_change_gets_distinct_review_binding_even_with_same_generation_source():
    from app.agents.animation_dsl_review import GenerationSource

    generation = GenerationSource(GEN, "a" * 64, "b" * 64)

    async def exercise():
        reviewer = AnimationDSLReviewAgent(FakeReview())
        a = await reviewer.review(
            candidate(),
            reference=reference(),
            generation_source=generation,
            animation_intent=VideoIntent("arrays", "compare", '{"values":[1,2]}').payload(),
        )
        b = await reviewer.review(
            candidate(),
            reference=reference(),
            generation_source=generation,
            animation_intent=VideoIntent("arrays", "compare", '{"values":[2,1]}').payload(),
        )
        assert a.approved and b.approved and a.binding_sha256 != b.binding_sha256

    asyncio.run(exercise())
