"""Single-paragraph revision of the sealed T121 queue first draft."""

from copy import deepcopy

from cryptography.fernet import Fernet
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.services import queue_course_materials as queue
from app.services.free_course_snapshots import SnapshotError, canonical
from app.services.stack_course_materials import TEXT, closed, fixed_request

GOAL = queue.GOAL
ORIGIN = queue.ORIGIN
outline = queue.outline
materials = queue.materials
assemble = queue.assemble
validate_content = queue.validate_content
VERSION = "queue-fifo-q01-revision-v1"
BATCH = "queue-fifo-q01-revision-r01"
PARENT = "39742e3ccc803c1afe313c7d90dc69fb778ea349227db248a09decd295c1cb97"
SOURCE_RECORD_SHA256 = "47b0f5c27324356de46fa28172e5ef5bc9ff2d9c5b1f5f2c9d3fc519873999e2"
INDEX = 2
KEY = "paragraph_2_text"
PATH = ["raw_output", "paragraphs", INDEX, "text"]
SCHEMA = closed({KEY: TEXT})
VALIDATOR = Draft202012Validator(SCHEMA)
INSTRUCTION = """[ROLE] Revise only the supplied dequeue paragraph of the Chinese FIFO lesson.
[OUTPUT] Return one complete replacement paragraph under paragraph_2_text. No other fields,
commentary, code fences, HTML, links, tools, or exercise answers. The program preserves every
other field, including the original paragraph's fact_ids.
[Q01] Distinguish the removed element and the surviving element by their original positions
or identities. Their integer values can be equal. After dequeuing a sole element the queue
is empty, with no new front. Only if there were at least two elements before a successful
dequeue does the original second element become the new front.
[PRESERVE] Keep the original paragraph's teaching role: empty check, writing the old front
through *out, shifting survivors, decreasing count and the linear cost of shifting count-1
elements. Use the supplied C code and facts. Do not copy adjacent paragraphs, introduce
unrelated examples, or change the lesson or its demonstration scope.
[LANGUAGE] Use one clear beginner-friendly paragraph in Simplified Chinese."""


def sealed_parent():
    from app.services.course_trial_publication import QUEUE
    from scripts import course_trial_generation as trial

    history = trial.package_path(QUEUE) / "live-result.json"
    if trial.sha(history.read_bytes()) != SOURCE_RECORD_SHA256:
        raise SnapshotError("QUEUE_REVISION_SOURCE_RECORD")
    record = trial.read(history)
    vault = trial.vault_path(QUEUE)
    key = vault / "raw.key"
    if (
        vault.is_symlink()
        or vault.stat().st_mode & 0o077
        or key.is_symlink()
        or key.stat().st_mode & 0o077
        or (vault / "published.json").exists()
    ):
        raise SnapshotError("QUEUE_REVISION_SOURCE_VAULT")
    for name, expected in record["sealed_file_sha256"].items():
        path = vault / name
        if path.is_symlink() or trial.sha(path.read_bytes()) != expected:
            raise SnapshotError("QUEUE_REVISION_SOURCE_BINDING")
    parent = trial.observe(
        trial.read(vault / "context.json"),
        trial.raw_io.decrypt(vault / "generate.raw.enc", Fernet(key.read_bytes())),
        trial.read(vault / "generate.body.json"),
        profile=QUEUE,
    )
    review = trial.read(vault / "review.json")
    if (
        parent != trial.read(vault / "generate.candidate.json")
        or parent["candidate_digest"] != PARENT
        or review != record["first_draft"]["teaching_review"]
        or review["candidate_digest"] != PARENT
        or review["verdict"] != "fail"
        or [(finding["id"], finding["path"]) for finding in review["blocking_findings"]]
        != [("Q01", "raw_output.paragraphs[2].text")]
    ):
        raise SnapshotError("QUEUE_REVISION_PARENT")
    return parent, review["blocking_findings"][0], record["sealed_file_sha256"]["review.json"]


def request():
    parent, finding, review_sha256 = sealed_parent()
    paragraphs = parent["raw_output"]["paragraphs"]
    mat = materials()
    paragraph = paragraphs[INDEX]
    return fixed_request(
        INSTRUCTION,
        GOAL,
        outline(),
        dict(
            protocol=VERSION,
            parent_digest=PARENT,
            parent_request_sha256=parent["receipt"]["request_sha256"],
            parent_response_sha256=parent["receipt"]["raw_sha256"],
            parent_review_sha256=review_sha256,
            plan_digest=parent["plan_digest"],
            materials_digest=parent["materials_digest"],
            allowed_path=PATH,
            original_paragraph=paragraph,
            neighboring_text=[paragraphs[i]["text"] for i in (INDEX - 1, INDEX + 1)],
            finding=finding,
            source=mat["main"]["source"],
            facts={key: mat["facts"][key] for key in paragraph["fact_ids"]},
        ),
        "edumind_queue_q01_revision",
        SCHEMA,
    )


def replacements(raw):
    return {KEY: raw["paragraphs"][INDEX]["text"]}


def merge(output):
    parent, _, _ = sealed_parent()
    if not VALIDATOR.is_valid(output):
        raise SnapshotError("QUEUE_REVISION_SCHEMA")
    raw = deepcopy(parent["raw_output"])
    text = output[KEY]
    if (
        not text.strip()
        or text.splitlines() != [text]
        or any(text.strip() == paragraph["text"].strip() for paragraph in raw["paragraphs"])
    ):
        raise SnapshotError("QUEUE_REVISION_TEXT")
    raw["paragraphs"][INDEX]["text"] = text
    validate_content(raw, materials())
    return raw


def validate_immutable(raw):
    # Rebuild from the exact parent using only the permitted leaf.
    if canonical(raw) != canonical(merge(replacements(raw))):
        raise SnapshotError("QUEUE_REVISION_OUTSIDE_SCOPE")
