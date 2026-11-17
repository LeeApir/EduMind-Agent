"""Ten-field revision of the sealed, schema-rejected T122 response."""

import re
from copy import deepcopy
from hashlib import sha256

from cryptography.fernet import Fernet
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.services import binary_search_course_materials as binary
from app.services.free_course_snapshots import SnapshotError, canonical
from app.services.stack_course_materials import TEXT, closed, fixed_request

GOAL, ORIGIN = binary.GOAL, binary.ORIGIN
outline, materials, assemble = binary.outline, binary.materials, binary.assemble
validate_content = binary.validate_content
VERSION = "binary-search-revision-v1"
BATCH = "binary-search-revision-r01"
SOURCE_RECORD = "dfe09909f844d1123c0ce7e805d17e905fc36322f31edec47e341dbfb4a651b3"
SOURCE_RESPONSE = "a083646c1a9109f04384dbaac2564699ec77092010fd7e8d3aee697eb7ea2409"
FRAME_INDICES = {"f2": 2, "f4": 4}
STEMS = {
    "increase_left": (
        "根据下方代码，查找 19 时第一次更新区间后的闭区间端点是什么？"
        "请用两元素 JSON 整数数组 [left,right] 作答。"
    ),
    "decrease_right": (
        "根据下方代码，查找 9 时第一次更新区间后的闭区间端点是什么？"
        "请用两元素 JSON 整数数组 [left,right] 作答。"
    ),
    "found_index": "根据下方代码，查找 19 时 binary_search 的函数返回值是什么？请用整数作答。",
    "missing_result": "根据下方代码，查找 9 时 binary_search 的函数返回值是什么？请用整数作答。",
}
SCHEMA = closed(
    {
        "questions": closed({key: closed({"stem": TEXT, "explanation": TEXT}) for key in STEMS}),
        "frame_notes": closed(dict.fromkeys(FRAME_INDICES, TEXT)),
    }
)
VALIDATOR = Draft202012Validator(SCHEMA)
MARKUP = re.compile(r"<\s*/?\s*[a-zA-Z][\w-]*(?:\s+[^<>]*)?/?>|<!--|\[[^\]]*\]\(|https?://")
INSTRUCTION = """[OUTPUT] Return exactly the closed Schema object, with questions keyed by the four
given keys and frame_notes keyed by f2 and f4. No extra or duplicate keys, nulls, arrays in
place of strings, full course, patches, commentary, tools, or Markdown/HTML wrapper.
Each leaf is one nonempty line of Simplified Chinese plain text, at most 1200 characters.
No HTML, links, Markdown formatting, fences, or code snippets. Ordinary punctuation,
identifiers, comparison symbols, and interval/JSON-array notation as inline text are allowed.
[STEMS] Copy each required_stem verbatim. Stems must not contain {, }, semicolons, #include,
backticks or tildes used as fences. Refer to the appended C code. Do not repeat the array,
give hints, or reveal answers. Preserve data, target, observation time, question meaning,
input format, and program answer.
[EXPLANATIONS] Use the exact program code and answers. For the two update questions explain
the first midpoint, comparison direction and resulting inclusive bounds. For the hit,
explain the path to the matching zero-based index. For the miss explain that left > right
makes the interval empty and the function returns -1. Answers belong in explanations only.
[FRAMES] f2 is the right update on line 13 in the same iteration that just compared
values[2] = 8 > 5. Keep left = 0, right = 1 and the just-used mid = 2, now excluded.
f4 is the left update on line 11 in the same iteration that just compared
values[0] = 2 < 5. Keep left = 1, right = 1 and the just-used mid = 0, now excluded.
Do not call either comparison a previous iteration, compute a new mid, or move the highlight.
[SCOPE] Only the ten supplied leaves are writable. Preserve other teaching and program material."""


def sealed_source():
    from app.services.course_trial_publication import BINARY_SEARCH
    from scripts import course_trial_generation as trial
    from scripts import head_course_deepseek_wire as direct

    package = trial.package_path(BINARY_SEARCH)
    record_path = package / "live-result.json"
    if trial.sha(record_path.read_bytes()) != SOURCE_RECORD:
        raise SnapshotError("BINARY_SEARCH_REVISION_SOURCE_RECORD")
    record = trial.read(record_path)
    vault = trial.vault_path(BINARY_SEARCH)
    key = vault / "raw.key"
    if (
        vault.is_symlink()
        or vault.stat().st_mode & 0o077
        or key.is_symlink()
        or key.stat().st_mode & 0o077
        or (vault / "generate.candidate.json").exists()
        or (vault / "published.json").exists()
    ):
        raise SnapshotError("BINARY_SEARCH_REVISION_SOURCE_VAULT")
    for name, expected in record["sealed_file_sha256"].items():
        path = vault / name
        if path.is_symlink() or trial.sha(path.read_bytes()) != expected:
            raise SnapshotError("BINARY_SEARCH_REVISION_SOURCE_BINDING")
    request_bytes = (vault / "generate.request.json").read_bytes()
    response = trial.raw_io.decrypt(vault / "generate.raw.enc", Fernet(key.read_bytes()))
    if (
        request_bytes != (package / "request.json").read_bytes()
        or request_bytes != canonical(binary.request())
        or trial.sha(response) != SOURCE_RESPONSE
    ):
        raise SnapshotError("BINARY_SEARCH_REVISION_SOURCE_BINDING")
    try:
        direct.observe_generation(trial.raw_io.wire.strict_json(request_bytes), response)
    except ValueError as error:
        if str(error) != "ROLE_SCHEMA":
            raise
    else:
        raise SnapshotError("BINARY_SEARCH_REVISION_SOURCE_VERDICT")
    envelope = trial.raw_io.wire.strict_json(response)
    raw = trial.raw_io.wire.strict_json(envelope["output"][0]["content"][0]["text"])
    errors = list(binary.VALIDATOR.iter_errors(raw))
    if (
        len(errors) != len(STEMS)
        or {tuple(e.absolute_path) for e in errors} != {("questions", k) for k in STEMS}
        or any(e.validator != "required" or set(e.instance) != {"stem"} for e in errors)
    ):
        raise SnapshotError("BINARY_SEARCH_REVISION_SOURCE_SCHEMA")
    return raw, trial.read(vault / "context.json"), trial.sha(request_bytes)


def request():
    raw, _, original_request = sealed_source()
    mat = materials()
    return fixed_request(
        INSTRUCTION,
        GOAL,
        outline(),
        dict(
            protocol=VERSION,
            source_response_sha256=SOURCE_RESPONSE,
            source_request_sha256=original_request,
            materials_digest=mat["materials_digest"],
            original_output_sha256=sha256(canonical(raw)).hexdigest(),
            required_stems=STEMS,
            original_questions=raw["questions"],
            original_frame_notes={key: raw["step_notes"][i] for key, i in FRAME_INDICES.items()},
            main=mat["main"],
            facts=mat["facts"],
            transfer=mat["transfer"],
        ),
        "edumind_binary_search_revision",
        SCHEMA,
    )


def merge(output):
    if not VALIDATOR.is_valid(output):
        raise SnapshotError("BINARY_SEARCH_REVISION_SCHEMA")
    raw, _, _ = sealed_source()
    if any(output["questions"][key]["stem"] != stem for key, stem in STEMS.items()):
        raise SnapshotError("BINARY_SEARCH_REVISION_QUESTION_BINDING")
    texts = list(output["frame_notes"].values()) + [
        item["explanation"] for item in output["questions"].values()
    ]
    if any(
        not text.strip()
        or text.splitlines() != [text]
        or MARKUP.search(text)
        or "`" in text
        or "~~~" in text
        for text in texts
    ):
        raise SnapshotError("BINARY_SEARCH_REVISION_TEXT")
    if any("上一轮" in note or "前一轮" in note for note in output["frame_notes"].values()):
        raise SnapshotError("BINARY_SEARCH_REVISION_FRAME_ITERATION")
    raw = deepcopy(raw)
    for key, replacement in output["questions"].items():
        raw["questions"][key].update(replacement)
    for key, index in FRAME_INDICES.items():
        raw["step_notes"][index]["note"] = output["frame_notes"][key]
    validate_content(raw, materials())
    return raw


def validate_immutable(raw):
    patch = {
        "questions": raw["questions"],
        "frame_notes": {
            key: raw["step_notes"][index]["note"] for key, index in FRAME_INDICES.items()
        },
    }
    if canonical(merge(patch)) != canonical(raw):
        raise SnapshotError("BINARY_SEARCH_REVISION_OUTSIDE_SCOPE")
