"""Verify the v2 request bytes and candidate bindings without creating an operation."""

import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from test_head_course_fixed import with_direct_echo
from test_stack_course_trial import teaching_fixture

from app.services import course_trial_publication as publication
from app.services import stack_course_profile_pair as pair
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import course_trial_generation as trial
from scripts.head_course_goal_fixture import envelope

PACKAGE = Path("docs/acceptance/phase-1.5-stack-profile-pair-t132")


def test_v2_wire_only_changes_the_shared_prompt_and_keeps_exact_evidence():
    common = []
    for case in pair.CASES:
        old = pair.request(case)
        new = pair.request(case, prompt_version=pair.PROMPT_V2)
        assert canonical(old) == (trial.ROOT / PACKAGE / case / "request.json").read_bytes()
        assert canonical(new) == (
            trial.ROOT / PACKAGE / "prompt-v2" / f"{case}.request.json"
        ).read_bytes()
        schema = new["text"]["format"]["schema"]
        assert (schema["properties"]["paragraphs"]["minItems"],
                schema["properties"]["paragraphs"]["maxItems"]) == (4, 7)
        system = new["input"][0]
        assert system != old["input"][0]
        assert "4–7 substantive entries in paragraphs" in system["content"]
        assert "Both lessons may share necessary explanations" in system["content"]
        assert "Use order, push, and f1/f2/f4" in system["content"]
        assert "Use order, pop, and f3" in system["content"]
        assert "Use push, pop, and boundary" in system["content"]
        assert dict(new, input=[old["input"][0], new["input"][1]]) == old

        user = json.loads(new["input"][1]["content"])
        assert user.pop("learner_evidence") == pair.learner_input(case)
        common.append(canonical(dict(new, input=[system, dict(role="user", content=user)])))
    assert common[0] == common[1]


@pytest.mark.parametrize("case", pair.CASES)
def test_v2_candidate_rejects_old_request_and_cross_slot_binding(case):
    old = publication.STACK_PROFILE_CASES[case]
    profile = replace(old, learner_prompt_version=pair.PROMPT_V2)
    assert profile.offline_only
    other = next(value for value in pair.CASES if value != case)
    ctx = dict(
        learner_case=case, profile_id=str(UUID(int=1)), profile_version=1,
        learner_evidence=pair.evidence(case),
    )
    request = trial.request_for(ctx, profile, "generate")
    raw = with_direct_echo(request, envelope(teaching_fixture()))
    receipt = dict(
        http_status=200, encoding="identity", raw_sha256=trial.sha(raw),
        raw_bytes=len(raw), complete=True,
    )
    candidate = trial.observe(ctx, raw, receipt, profile=profile)
    assert candidate["context"]["learner_evidence"] == pair.evidence(case)
    assert candidate["receipt"]["request_sha256"] == trial.sha(canonical(request))
    assert publication.verify_candidate(ctx, candidate, profile) == request
    with pytest.raises(SnapshotError, match="REQUEST_BINDING"):
        publication.verify_candidate(ctx, candidate, old)

    for wrong in (
        pair.request(case),
        pair.request(other, prompt_version=pair.PROMPT_V2),
    ):
        receipt = dict(candidate["receipt"], request_sha256=trial.sha(canonical(wrong)))
        with pytest.raises(SnapshotError, match="REQUEST_BINDING"):
            publication.candidate(ctx, candidate["raw_output"], receipt, profile=profile)
    ctx["learner_evidence"] = pair.evidence(other)
    with pytest.raises(SnapshotError, match="PROFILE_BINDING"):
        publication.verify_candidate(ctx, candidate, profile)
