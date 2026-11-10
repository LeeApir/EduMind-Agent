"""One citation amendment for the independently rejected T118 r02 candidate."""

import hashlib
from copy import deepcopy
from uuid import UUID

from cryptography.fernet import Fernet

from app.services import head_course_materials as m
from app.services import head_course_reuse as r
from app.services import head_course_teaching_evidence as evidence
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from scripts import head_course_deepseek_wire as direct
from scripts import head_course_goal as entry

VERSION = "head-empty-citation-revision-v1"
BATCH = "head-empty-citation-revision-r01"
APPROVAL_KEY = "accept_T118_citation_scope_and_batch_C2"
INDEX = 4
KEY = "paragraph_4_fact_ids"
PATH = ["paragraphs", INDEX, "fact_ids"]
BEFORE = ["trace_step_05"]
AFTER = [*BEFORE, evidence.DISCARDED]
PARENT = "49fd497d8d45f928eaacb67bdf9bb37ef6ee77ae160e01d7ed70b3cfb339a21c"
REVIEW = "f648de6c8409bbd9daad95c664b19d2d80e633ca573aa90271714bee75456fe8"
PLAN_REVIEW = "e94e4ad815572b791de3852a5552d9b2122909db516e6f677ac209310d79ee8f"
SOURCE_MANIFEST = "e03652595a62a512f381b102fabd1831345e797334420470f4a646a96da7b47b"
SOURCE_STOP = "3d6f3790b0d12af40f0f97d216d312ae3c62949ba4e8c039099f20baaeb17433"
SOURCE_HTTP = {
    "plan": (
        "28ac73f38a71997b60f17e7317083d52bf29bb5375ea11d4a088c52ec984f091",
        "55c082f5d22b9680c274a7b494d215aaaa078b84f768454e6c1b2dd0fd838eb5",
    ),
    "generate": (
        "04f7508ab028104cfd50ecf9c1fe1a05eec7c770202b233614383bbbd4813e74",
        "31f985fd029768ed54ef7df6cc3802f4b9440e95441a3d2f04b20584281ebcd0",
    ),
}
INSTRUCTION = """[ROLE] Repair one evidence reference list in an otherwise unchanged lesson.
[OUTPUT] Return only the closed JSON object with paragraph_4_fact_ids. This is the complete
replacement list for raw_output.paragraphs[4].fact_ids. Keep trace_step_05 for the claim
about receiving the returned pointer, then add head_evidence_v1.discard_return_comparison
for the claim about ignoring it. Use exactly this order. Do not output prose, other fields,
patch operations, commentary, or Markdown. The program merges only the returned list.
"""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


PACKAGE = entry.ROOT / "docs/acceptance/phase-1.5-head-empty-citation-revision-r01"
VAULT = entry.EMPTY_R02_VAULT.with_name(BATCH)
observe_generation = direct.observe_generation


def source_original():
    """Replay the sealed r02 pair against the original frozen request and review digests."""
    vault = entry.EMPTY_R02_VAULT
    if (
        vault.is_symlink()
        or not vault.is_dir()
        or vault.stat().st_mode & 0o077
        or (vault / "ACTIVE").exists()
        or (vault / "published.json").exists()
        or sorted(p.name for p in vault.glob("*.attempt.json"))
        != ["generate.attempt.json", "plan.attempt.json"]
        or sha((vault / "STOP").read_bytes()) != SOURCE_STOP
        or sha((entry.EMPTY_R02_PACKAGE / "manifest.json").read_bytes()) != SOURCE_MANIFEST
    ):
        raise SnapshotError("CITATION_SOURCE_STOP")
    rawkey = vault / "raw.key"
    if rawkey.is_symlink() or rawkey.stat().st_mode & 0o077:
        raise SnapshotError("CITATION_SOURCE_KEY")
    cipher = Fernet(rawkey.read_bytes())
    approval = (vault / "approval.bound.json").read_bytes()
    context = entry.read(vault / "context.json")
    grant = entry.read(vault / "approval.bound.json")
    if (
        grant["context_sha256"] != sha((vault / "context.json").read_bytes())
        or grant["package_sha256"] != SOURCE_MANIFEST
        or grant["batch"] != direct.EMPTY_R02_BATCH
        or grant["explicit_user_authorization"] is not True
        or grant["execution_window"] != context["execution_window"]
    ):
        raise SnapshotError("CITATION_SOURCE_APPROVAL")
    saved = {}
    for stage, (request_sha, raw_sha) in SOURCE_HTTP.items():
        req = entry.read(vault / f"{stage}.request.json")
        raw = entry.raw_io.decrypt(vault / f"{stage}.raw.enc", cipher)
        attempt = entry.read(vault / f"{stage}.attempt.json")
        if (
            sha(canonical(req)) != request_sha
            or sha(raw) != raw_sha
            or entry.read(vault / f"{stage}.body.json")
            != dict(http_status=200, raw_bytes=len(raw), raw_sha256=raw_sha, body_complete=True)
            or attempt["stage"] != stage
            or attempt["package_sha256"] != SOURCE_MANIFEST
            or attempt["approval_sha256"] != sha(approval)
            or attempt["request_sha256"] != request_sha
            or attempt["evidence_kind"] != "actual_provider_response"
        ):
            raise SnapshotError("CITATION_SOURCE_HTTP")
        saved[stage] = (req, raw)
    planning_inputs = context["planning_inputs"]
    plan_req, plan_raw = saved["plan"]
    if plan_req != entry.planning_body(planning_inputs):
        raise SnapshotError("CITATION_SOURCE_PLAN")
    result, _ = observe_generation(plan_req, plan_raw)
    mapping = entry.plan_wire.mapping_record(dict(result.value), planning_inputs)
    if mapping != entry.read(vault / "plan.mapping.json"):
        raise SnapshotError("CITATION_SOURCE_PLAN")
    payload = m.content_payload(planning_inputs, mapping["value"]["plan"])
    if (
        entry.read(vault / "plan.binding.json")["payload"] != payload
        or sha((vault / "plan-review.json").read_bytes()) != PLAN_REVIEW
    ):
        raise SnapshotError("CITATION_SOURCE_PLAN")
    r.validate_plan_review(entry.read(vault / "plan-review.json"), payload)
    record = r.record(payload, *saved["generate"], direct, evidence_kind="actual_provider_response")
    if (
        record != entry.read(vault / "generate.record.json")
        or sha((vault / "final-review.json").read_bytes()) != REVIEW
        or record["candidate"]["candidate_digest"] != PARENT
    ):
        raise SnapshotError("CITATION_SOURCE_CANDIDATE")
    review = entry.read(vault / "final-review.json")
    r.review_binding(review, record["candidate"], "stop")
    return record["candidate"], review


def inputs():
    parent, review = source_original()
    return dict(
        parent_candidate=parent,
        original_review=review,
        teaching_evidence=parent["payload"]["teaching_evidence"],
        allowed_paths={KEY: PATH},
    )


def schema():
    return m.closed(
        {
            KEY: dict(
                type="array",
                minItems=2,
                maxItems=2,
                uniqueItems=True,
                items=dict(type="string", enum=AFTER),
            )
        }
    )


def body():
    data = inputs()
    parent, review = data["parent_candidate"], data["original_review"]
    paragraph = parent["raw_output"]["paragraphs"][INDEX]
    bundle = data["teaching_evidence"]
    (finding,) = review["blocking_findings"]
    if (
        finding["id"] != "C01"
        or finding["path"] != "raw_output.paragraphs[4].fact_ids"
        or finding["quote"] not in paragraph["text"]
        or paragraph["fact_ids"] != BEFORE
        or finding["required_fact_id"] != evidence.DISCARDED
        or bundle["facts"][evidence.DISCARDED]["evidence_kind"] != "computed_counterfactual"
    ):
        raise SnapshotError("CITATION_SCOPE")
    scoped = dict(
        version=VERSION,
        parent_digest=PARENT,
        original_review_sha256=REVIEW,
        plan_digest=digest("head-plan", plan=parent["payload"]["plan"]),
        materials_digest=parent["payload"]["materials"]["materials_digest"],
        evidence_digest=bundle["evidence_digest"],
        allowed_path=["raw_output", *PATH],
        original_paragraph=paragraph,
        finding=finding,
        required_fact_ids=AFTER,
        facts={
            BEFORE[0]: parent["payload"]["materials"]["catalog"]["facts"][BEFORE[0]],
            evidence.DISCARDED: bundle["facts"][evidence.DISCARDED],
        },
    )
    return dict(
        model="deepseek-flash",
        stream=False,
        store=False,
        reasoning=dict(effort="none"),
        temperature=0.2,
        max_output_tokens=4000,
        input=[
            dict(role="system", content=INSTRUCTION),
            dict(role="user", content=canonical(scoped).decode()),
        ],
        text=dict(
            format=dict(
                type="json_schema",
                name="edumind_head_empty_citation_revision",
                strict=True,
                schema=schema(),
            )
        ),
    )


def merge(parent, replacements):
    r.validate_candidate(parent)
    if parent["candidate_digest"] != PARENT:
        raise SnapshotError("CITATION_PARENT")
    m.Draft202012Validator(schema()).validate(replacements)
    if (
        replacements[KEY] != AFTER
        or parent["raw_output"]["paragraphs"][INDEX]["fact_ids"] != BEFORE
    ):
        raise SnapshotError("CITATION_EXACT_LIST")
    raw = deepcopy(parent["raw_output"])
    raw["paragraphs"][INDEX]["fact_ids"] = deepcopy(replacements[KEY])
    child = r.candidate(parent["payload"], raw, parent=PARENT)
    restored = deepcopy(child["raw_output"])
    restored["paragraphs"][INDEX]["fact_ids"] = BEFORE
    if canonical(restored) != canonical(parent["raw_output"]) or canonical(
        child["payload"]
    ) != canonical(parent["payload"]):
        raise SnapshotError("CITATION_IMMUTABILITY")
    return child


def source(candidate, model, review=None, fixture=False):
    p = candidate["payload"]
    value = dict(
        origin=m.ORIGIN,
        batch=BATCH,
        candidate_digest=candidate["candidate_digest"],
        parent_digest=PARENT,
        model=model,
        prompt_version=VERSION,
        plan_digest=digest("head-plan", plan=p["plan"]),
        materials_digest=p["materials"]["materials_digest"],
        evidence_kind="offline_fixture" if fixture else "evidence_bound_local_revision",
        teaching_evidence_version=evidence.VERSION,
        teaching_evidence_digest=p["teaching_evidence"]["evidence_digest"],
    )
    if review is not None:
        value["teaching_review"] = dict(
            verdict=review["verdict"], independent_evaluator=review["independent_evaluator"]
        )
    return value


def assemble(candidate):
    parent = inputs()["parent_candidate"]
    replacements = {KEY: candidate["raw_output"]["paragraphs"][INDEX]["fact_ids"]}
    if canonical(candidate) != canonical(merge(parent, replacements)):
        raise SnapshotError("CITATION_CANDIDATE")
    return m.assemble(
        candidate["payload"], candidate["raw_output"], source(candidate, "deepseek-flash")
    )


def validate_approval(approval, owner=None):
    try:
        target = UUID(approval["owner"])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise SnapshotError("CITATION_APPROVAL_OWNER") from None
    if (
        approval.get(APPROVAL_KEY) is not True
        or approval.get("batch") != BATCH
        or approval.get("original_review_sha256") != REVIEW
        or str(target) != approval["owner"]
        or (owner is not None and target != owner)
    ):
        raise SnapshotError("CITATION_APPROVAL_BINDING")
