"""Compare the exact prompt update and bind new-profile candidates without database writes."""

import json
from uuid import UUID

import pytest
from test_head_course_fixed import with_direct_echo
from test_stack_course_trial import teaching_fixture

from app.services import course_trial_publication as publication
from app.services import stack_course_profile_pair as pair
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import course_trial_generation as trial
from scripts.head_course_goal_fixture import envelope


def test_pair_wire_changes_only_the_adaptation():
    common = []
    for topic, profile in publication.STACK_PROFILE_V3_LIVE.items():
        previous = publication.STACK_PROFILE_V2_LIVE[topic.removesuffix("-v3") + "-v2"]
        frozen = trial.request_path(previous).read_bytes()
        assert canonical(previous.request()) == frozen
        old = json.loads(frozen)
        new = profile.request()
        assert canonical(new) == trial.request_path(profile).read_bytes()
        assert profile.batch.endswith("-r03") and profile.batch != previous.batch
        assert trial.approval_values(profile)["request_sha256"] == trial.sha(canonical(new))

        before = old["input"][0]["content"]
        after = new["input"][0]["content"]
        assert after != before
        assert after.split("[ADAPTATION]", 1)[0] == before.split("[ADAPTATION]", 1)[0]
        assert after.split("[PROGRAM MATERIAL]", 1)[1] == before.split("[PROGRAM MATERIAL]", 1)[1]
        assert dict(new, input=[old["input"][0], new["input"][1]]) == old
        user = json.loads(new["input"][1]["content"])
        assert user.pop("learner_evidence") == pair.learner_input(profile.learner_case)
        common.append(dict(new, input=[new["input"][0], dict(role="user", content=user)]))
    assert len(common) == 2 and common[0] == common[1]


@pytest.mark.parametrize("topic", publication.STACK_PROFILE_V3_LIVE)
def test_new_slot_binds_exact_candidate_and_refuses_old_approval(topic):
    profile = publication.STACK_PROFILE_V3_LIVE[topic]
    previous = publication.STACK_PROFILE_V2_LIVE[topic.removesuffix("-v3") + "-v2"]
    case = profile.learner_case
    other = next(c for c in pair.CASES if c != case)
    ctx = dict(
        learner_case=case, learner_evidence=pair.evidence(case),
        profile_version=1, profile_id=str(UUID(int=1)),
    )
    request = trial.request_for(ctx, profile, "generate")
    raw = with_direct_echo(request, envelope(teaching_fixture()))
    receipt = dict(
        http_status=200, encoding="identity", raw_sha256=trial.sha(raw),
        raw_bytes=len(raw), complete=True,
    )
    candidate = trial.observe(ctx, raw, receipt, profile=profile)
    assert publication.verify_candidate(ctx, candidate, profile) == request
    with pytest.raises(SnapshotError, match="REQUEST_BINDING"):
        publication.verify_candidate(ctx, candidate, previous)
    with pytest.raises(SnapshotError, match="PROFILE_BINDING"):
        profile.request(dict(ctx, learner_evidence=pair.evidence(other)))
    with pytest.raises(SnapshotError, match="EXACT_AUTHORIZATION_REQUIRED"):
        trial.check_approval(
            json.loads((trial.package_path(previous) /
                        f"{case}.execution-approval.json").read_bytes()),
            profile=profile,
        )
