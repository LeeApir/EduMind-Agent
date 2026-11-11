"""Build a bounded first-draft revision from an exact offline approval record."""

from copy import deepcopy
from hashlib import sha256

from app.services import head_course_reuse as reuse
from app.services.free_course_snapshots import canonical
from app.services.head_course_materials import closed

VERSION = "shared-trial-limited-revision-v1"
SUMMARY_FIELDS = {
    "head": frozenset({"learning_summary", "failure_scope"}),
    "stack": frozenset({"summary"}),
    "queue": frozenset({"summary"}),
    "binary-search": frozenset({"summary"}),
}
RECORD_KEYS = {
    "version", "topic", "batch", "parent_digest", "review_sha256", "allowed_paths",
    "max_http_requests", "offline_fixture", "approved", "request_sha256",
}


def checksum(value):
    return sha256(canonical(value)).hexdigest()


def contract(profile, parent, review, record):
    raw = parent["raw_output"]
    ctx = parent["context"]
    if (
        not profile.offline_only
        or ctx.get("evidence_kind") != "offline_fixture"
        or ctx.get("topic") != profile.topic
        or ctx.get("batch") != profile.batch
        or parent.get("parent_digest") is not None
        or set(record) != RECORD_KEYS
        or record["version"] != VERSION
        or record["topic"] != profile.topic
        or record["batch"] != profile.batch
        or record["parent_digest"] != parent["candidate_digest"]
        or record["offline_fixture"] is not True
    ):
        raise profile.error("REVISION_PARENT_BINDING")
    if (
        type(record["max_http_requests"]) is not int
        or record["max_http_requests"] not in (0, 1)
        or type(record["approved"]) is not bool
    ):
        raise profile.error("REVISION_BUDGET")
    if (
        record["review_sha256"] != checksum(review)
        or review.get("candidate_digest") != parent["candidate_digest"]
        or review.get("verdict") != "needs_revision"
        or not isinstance(review.get("independent_evaluator"), str)
        or not review["independent_evaluator"].strip()
        or review.get("full_lesson_reviewed") is not True
    ):
        raise profile.error("REVISION_REVIEW_BINDING")
    if profile.model_planned:
        lesson = reuse.candidate(ctx["head_payload"], raw)
        reuse.review_binding(
            dict(review, candidate_digest=lesson["candidate_digest"]), lesson, "needs_revision"
        )

    findings = review.get("findings")
    if (
        not isinstance(findings, list)
        or not 1 <= len(findings) <= 8
        or any(not isinstance(item, dict) for item in findings)
        or review.get("blocking_findings") != findings
        or record["allowed_paths"] != [item.get("path") for item in findings]
    ):
        raise profile.error("REVISION_SCOPE")

    properties = profile.materials.SCHEMA["properties"]
    targets, fields = {}, {}
    for finding in findings:
        path = finding["path"]
        if (
            finding.get("area") not in ("citation", "teaching_expression")
            or finding.get("severity") != "minor"
            or finding.get("repairable") is not True
            or any(
                not isinstance(finding.get(key), str) or not finding[key].strip()
                for key in ("quote", "issue", "teaching_responsibility")
            )
            or not isinstance(path, list)
        ):
            raise profile.error("REVISION_SCOPE")
        if len(path) == 1 and isinstance(path[0], str) and path[0] in SUMMARY_FIELDS[profile.topic]:
            key = path[0]
            old, schema = raw[key], properties[key]
        elif (
            len(path) == 3
            and path[0] == "paragraphs"
            and type(path[1]) is int
            and 0 <= path[1] < len(raw["paragraphs"])
            and path[2] in ("text", "fact_ids")
        ):
            index, leaf = path[1:]
            key = f"paragraph_{index}_{leaf}"
            old = raw["paragraphs"][index][leaf]
            schema = properties["paragraphs"]["items"]["properties"][leaf]
        else:
            raise profile.error("REVISION_SCOPE")
        if key in targets or finding["quote"] not in old:
            raise profile.error("REVISION_QUOTE_OR_DUPLICATE")
        targets[key], fields[key] = path, deepcopy(schema)
    return dict(targets=targets, schema=closed(fields))


def request(profile, parent, review, record):
    selection = contract(profile, parent, review, record)
    body = profile.request(parent["context"])
    body.update(
        max_output_tokens=4000,
        input=[
            dict(
                role="system",
                content=(
                    "[ROLE] Revise only the selected fields of this Chinese lesson.\n"
                    "[OUTPUT] Return the required replacements under the exact Schema keys. "
                    "Follow the finding and teaching responsibility for each selected field.\n"
                    "[LIMITS] Keep all other text, questions, explanations, frames and "
                    "program materials unchanged. Use only supplied facts and cite exact IDs. "
                    "Keep necessary explanations. Do not copy adjacent paragraphs, add tools, "
                    "or reveal answers. Independent full-lesson review follows merging."
                ),
            ),
            dict(
                role="user",
                content=canonical(
                    dict(
                        version=VERSION,
                        parent_digest=parent["candidate_digest"],
                        original=parent["raw_output"],
                        review=review,
                        targets=selection["targets"],
                        same_version_input=body["input"][1]["content"],
                    )
                ).decode(),
            ),
        ],
        text=dict(
            format=dict(
                type="json_schema", name="edumind_shared_trial_revision",
                strict=True, schema=selection["schema"],
            )
        ),
    )
    return body


def approved_request(profile, parent, review, record):
    body = request(profile, parent, review, record)
    if (
        record["approved"] is not True
        or record["max_http_requests"] != 1
        or record["request_sha256"] != checksum(body)
    ):
        raise profile.error("REVISION_AUTHORIZATION_REQUIRED")
    return body


def merge(profile, parent, review, record, replacements):
    selection = contract(profile, parent, review, record)
    original = parent["raw_output"]
    merged = reuse.merge_replacements(original, selection, replacements)
    if merged == original or any(
        isinstance(value, str) and not value.strip() for value in replacements.values()
    ):
        raise profile.error("REVISION_EMPTY_CHANGE")
    paragraphs = merged["paragraphs"]
    for path in selection["targets"].values():
        if len(path) == 3 and path[2] == "text":
            index = path[1]
            text = paragraphs[index]["text"].strip()
            if any(
                text in (original["paragraphs"][j]["text"].strip(), paragraphs[j]["text"].strip())
                for j in (index - 1, index + 1)
                if 0 <= j < len(paragraphs)
            ):
                raise profile.error("REVISION_COPIED_NEIGHBOUR")
    return merged
