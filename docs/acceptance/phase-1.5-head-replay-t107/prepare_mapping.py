"""Offline proposed replay mapping. Does not import, serve, mutate DB, or send requests."""

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from jsonschema import Draft202012Validator  # noqa: E402

from app.services.quiz_scoring import _canonical_answer  # noqa: E402

LIVE = ROOT / "docs/acceptance/phase-1.5-limited-c-live-r01"
spec = importlib.util.spec_from_file_location(
    "frozen_preparation",
    ROOT / "docs/acceptance/phase-1.5-limited-c-preparation-t104/prepare.py",
)
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
CASES = {
    "C01": (
        "C01-generate",
        "e80a6cd201bb12add78fe74b973df432bdef544306b33c8ec63f312c3d4856f1",
    ),
    "C02": (
        "C02-repair",
        "94b98e3411cdffdce46a77387aac92d3333731e5bae340e2e886cad82596dea0",
    ),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()


def ident(value):
    # Proposal identities only. Real owner/course/scene IDs will be assigned by repository.
    return str(uuid5(NAMESPACE_URL, "edumind:t107:proposal:" + value))


def closed(properties):
    return dict(
        type="object",
        additionalProperties=False,
        properties=properties,
        required=list(properties),
    )


def proposal_schemas():
    schemas = deepcopy(
        json.loads(
            (ROOT / "backend/app/contracts/free_course.openapi.json").read_text()
        )["components"]["schemas"]
    )
    token = dict(type="string", minLength=1, maxLength=64)
    pointer = dict(anyOf=[token, dict(type="null")])
    integer = dict(type="integer", minimum=0, maximum=49)
    raw_state = closed(
        dict(
            phase=dict(
                enum=[
                    "initial",
                    "allocate",
                    "allocation_failed",
                    "data",
                    "link",
                    "return",
                    "caller",
                ]
            ),
            attempt=dict(
                anyOf=[dict(type="integer", minimum=0, maximum=1), dict(type="null")]
            ),
            caller_head=pointer,
            local_head=pointer,
            p=pointer,
            returned=pointer,
            nodes=dict(
                type="object",
                maxProperties=3,
                additionalProperties=closed(
                    dict(
                        data=dict(
                            anyOf=[
                                dict(type="integer", minimum=-99, maximum=99),
                                dict(const="indeterminate"),
                            ]
                        ),
                        next=pointer,
                    )
                ),
            ),
            code_line=dict(
                anyOf=[dict(type="integer", minimum=1, maximum=100), dict(type="null")]
            ),
        )
    )
    schemas["HeadReplayFrame"] = closed(
        dict(
            frame_id=token,
            state_index=integer,
            fact_id=token,
            kind=dict(
                enum=[
                    "initial",
                    "allocate",
                    "allocation_failed",
                    "data",
                    "link",
                    "return",
                    "caller",
                    "success_null_check",
                ]
            ),
            title=dict(type="string", minLength=1, maxLength=100),
            note=dict(type="string", minLength=1, maxLength=2000),
            code_anchor=dict(const="head-code"),
            line=dict(
                anyOf=[dict(type="integer", minimum=1, maximum=100), dict(type="null")]
            ),
            locals_scope=dict(enum=["active", "inactive"]),
            state=raw_state,
        )
    )
    # Keep legacy steps unchanged. New explicit type prevents old clients drawing an empty list.
    head_step = closed(
        dict(
            caption=dict(type="string", minLength=1, maxLength=100),
            head_frame={"$ref": "#/$defs/HeadReplayFrame"},
        )
    )
    schemas["HeadReplayVisualization"] = closed(
        dict(
            kind=dict(const="visualization"),
            anchor_id=dict(const="head-state"),
            visualization_type=dict(const="head_insertion_replay_v1"),
            text_alternative=dict(type="string", minLength=1, maxLength=4000),
            steps=dict(type="array", minItems=1, maxItems=13, items=head_step),
        )
    )
    h = dict(type="string", pattern="^[0-9a-f]{64}$")
    schemas["ReplaySource"] = closed(
        dict(
            mapping_version=dict(const="head-replay-map-v1"),
            origin=dict(const="existing_real_candidate_replay"),
            batch=dict(const="PHASE-1.5-T106"),
            slot=dict(enum=["C01", "C02"]),
            candidate_digest=h,
            candidate_file_sha256=h,
            parent_digest=dict(anyOf=[h, dict(type="null")]),
            model=dict(const="deepseek-flash"),
            prompt_version=dict(const=prep.VERSION),
        )
    )
    schemas["Question"]["properties"]["input_type"] = dict(
        enum=["short_text", "json_integer_array", "integer"]
    )
    public = schemas["SceneProjection"]
    public["properties"]["blocks"]["items"]["oneOf"].append(
        {"$ref": "#/$defs/HeadReplayVisualization"}
    )
    public["properties"]["replay_source"] = {"$ref": "#/$defs/ReplaySource"}
    # Standalone review schema only; runtime OpenAPI/normal generation Schema are untouched.
    converted = json.loads(
        json.dumps(schemas).replace("#/components/schemas/", "#/$defs/")
    )
    selected = {}

    def visit(name):
        if name in selected:
            return
        selected[name] = converted[name]

        def refs(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    visit(value["$ref"].removeprefix("#/$defs/"))
                for child in value.values():
                    refs(child)
            elif isinstance(value, list):
                for child in value:
                    refs(child)

        refs(selected[name])

    visit("SceneProjection")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/SceneProjection",
        "$defs": selected,
    }


def map_case(slot):
    name, expected = CASES[slot]
    path = LIVE / (name + ".candidate.json")
    raw_bytes = path.read_bytes()
    frozen = json.loads((LIVE / "delivery-manifest.json").read_text())["files"]
    assert sha(raw_bytes) == frozen[path.name]
    candidate = json.loads(raw_bytes)
    assert candidate["artifact_digest"] == expected and candidate["slot"] == slot
    value = candidate["raw_output"]
    catalog = prep.check_content(slot, value)
    assert prep.artifact(slot, value, candidate["parent_digest"]) == candidate
    source = dict(
        mapping_version="head-replay-map-v1",
        origin="existing_real_candidate_replay",
        batch="PHASE-1.5-T106",
        slot=slot,
        candidate_digest=expected,
        candidate_file_sha256=sha(raw_bytes),
        parent_digest=candidate["parent_digest"],
        model="deepseek-flash",
        prompt_version=prep.VERSION,
    )
    # Each model text leaf is mapped by a JSON pointer; text is never joined or paraphrased.
    blocks, links = [], []

    def prose(pointer, value):
        i = len(blocks)
        blocks.append(dict(kind="text", anchor_id=f"text-{i}", markdown=value))
        links.append(dict(source=pointer, target=f"/blocks/{i}/markdown"))

    prose("/raw_output/prerequisites", value["prerequisites"])
    for i, paragraph in enumerate(value["paragraphs"]):
        prose(f"/raw_output/paragraphs/{i}/text", paragraph["text"])
    blocks.append(
        dict(
            kind="code",
            anchor_id="head-code",
            language="c",
            source=catalog["example"]["code"]["source"],
        )
    )
    steps = []
    vi = len(blocks)
    for i, (frame, note) in enumerate(
        zip(prep.frames(catalog), value["step_notes"], strict=True)
    ):
        state = catalog["example"]["trace"]["steps"][frame["state_index"]]
        head = dict(
            **frame,
            title=note["title"],
            note=note["note"],
            code_anchor="head-code",
            locals_scope="inactive"
            if state["phase"] in ("initial", "caller")
            else "active",
            state=deepcopy(state),
        )
        steps.append(dict(caption=note["title"], head_frame=head))
        for key in ("title", "note"):
            links.append(
                dict(
                    source=f"/raw_output/step_notes/{i}/{key}",
                    target=f"/blocks/{vi}/steps/{i}/head_frame/{key}",
                )
            )
    blocks.append(
        dict(
            kind="visualization",
            anchor_id="head-state",
            visualization_type="head_insertion_replay_v1",
            text_alternative=value["learning_summary"],
            steps=steps,
        )
    )
    for key in ("failure_scope", "lifecycle", "learning_summary"):
        prose("/raw_output/" + key, value[key])
    items = []
    private_items = []
    ei = len(blocks)
    for i, (key, q) in enumerate(value["questions"].items()):
        answer = catalog["example"]["observation"][key]
        if key == "caller_head":
            answer = "none" if answer is None else answer
        elif not isinstance(answer, str):
            answer = json.dumps(answer, separators=(",", ":"))
        item = dict(
            question_id=key,
            question=q["stem"],
            input_type={
                "reachable_prefix": "json_integer_array",
                "allocation_failures": "integer",
            }.get(key, "short_text"),
        )
        items.append(item)
        private_items.append(dict(**item, answer_key=answer, solution=q["explanation"]))
        links.append(
            dict(
                source=f"/raw_output/questions/{key}/stem",
                target=f"/blocks/{ei}/items/{i}/question",
            )
        )
        links.append(
            dict(
                source=f"/raw_output/questions/{key}/explanation",
                private_target=f"/exercise/items/{i}/solution",
            )
        )
    eid = ident(slot + ":exercise")
    blocks.append(
        dict(
            kind="exercise",
            anchor_id="head-questions",
            exercise_id=eid,
            exercise_version_id=ident(slot + ":exercise-version"),
            question="随堂练习",
            items=items,
        )
    )
    public = dict(
        course_id=ident(slot + ":course"),
        course_version=1,
        scene_id=ident(slot + ":scene"),
        scene_version_id=ident(slot + ":scene-version"),
        replay_source=source,
        blocks=blocks,
        actions=[
            dict(type="show_step", anchor_id="head-state", step_index=i)
            for i in range(len(steps))
        ],
    )
    private = dict(
        status="proposal_not_imported",
        replay_source=source,
        original_candidate_utf8=raw_bytes.decode(),
        exercise=dict(exercise_key="head-questions", items=private_items),
        model_field_links=links,
        original_fact_bindings=dict(
            paragraphs=[
                dict(key=p["key"], fact_ids=p["fact_ids"]) for p in value["paragraphs"]
            ],
            questions={k: q["fact_ids"] for k, q in value["questions"].items()},
        ),
    )
    return public, private


def check_exact(slot, public, private):
    expected_public, expected_private = map_case(slot)
    assert public == expected_public and private == expected_private, (
        "REPLAY_MAPPING_MISMATCH"
    )


def pointer(value, path):
    for key in path.strip("/").split("/"):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def outputs():
    schema = proposal_schemas()
    current = json.loads(
        (ROOT / "backend/app/contracts/free_course.openapi.json").read_text()
    )["components"]["schemas"]
    old = json.loads(
        json.dumps({"$ref": "#/$defs/SceneProjection", "$defs": current}).replace(
            "#/components/schemas/", "#/$defs/"
        )
    )
    result = {"proposed-scene.schema.json": encoded(schema)}
    report = dict(
        status="offline_proposal_only",
        provider_calls=0,
        database_writes=0,
        application_browser_checked=False,
        cases=[],
    )
    for slot in CASES:
        public, private = map_case(slot)
        Draft202012Validator(schema).validate(public)
        check_exact(slot, public, private)
        original = json.loads(private["original_candidate_utf8"])
        for link in private["model_field_links"]:
            target = (
                pointer(private, link["private_target"])
                if "private_target" in link
                else pointer(public, link["target"])
            )
            assert target == pointer(original, link["source"])
        # Check every model teaching string appears, not merely the expected mapping count.
        assert (
            len(private["model_field_links"])
            == 4
            + len(original["raw_output"]["paragraphs"])
            + 2 * len(original["raw_output"]["step_notes"])
            + 8
        )
        text = json.dumps(public, ensure_ascii=False)
        assert (
            '"answer_key"' not in text
            and '"solution"' not in text
            and "original_candidate_utf8" not in text
        )
        errors = list(Draft202012Validator(old).iter_errors(public))
        assert errors
        # Concrete old comparator regression: JSON-equivalent array formatting fails today.
        array = json.loads(
            private["exercise"]["items"][
                next(
                    i
                    for i, q in enumerate(private["exercise"]["items"])
                    if q["question_id"] == "reachable_prefix"
                )
            ]["answer_key"]
        )
        compact = json.dumps(array, separators=(",", ":"))
        pretty = json.dumps(array, indent=1)
        assert json.loads(compact) == json.loads(pretty)
        assert _canonical_answer(compact) != _canonical_answer(pretty)
        assert (
            len(
                json.dumps(
                    dict(public=public, private=private), ensure_ascii=False
                ).encode()
            )
            < 65536
        )
        rejected_mutations = []
        vi = next(
            i for i, b in enumerate(public["blocks"]) if b["kind"] == "visualization"
        )
        for kind in ("line", "scope", "unknown_next", "title", "parent", "original"):
            bad, secret = deepcopy(public), deepcopy(private)
            frame = bad["blocks"][vi]["steps"][1]["head_frame"]
            if kind == "line":
                frame["line"] = 99
            elif kind == "scope":
                frame["locals_scope"] = "inactive"
            elif kind == "unknown_next":
                # C01 allocates in frame1; C02 allocates successfully later.
                frame = next(
                    s["head_frame"]
                    for s in bad["blocks"][vi]["steps"]
                    if any(
                        n["next"] == "indeterminate"
                        for n in s["head_frame"]["state"]["nodes"].values()
                    )
                )
                node = next(
                    n
                    for n in frame["state"]["nodes"].values()
                    if n["next"] == "indeterminate"
                )
                node["next"] = None
            elif kind == "title":
                frame["title"] += "modified"
            elif kind == "parent":
                bad["replay_source"]["parent_digest"] = "0" * 64
            else:
                secret["original_candidate_utf8"] += " "
            try:
                check_exact(slot, bad, secret)
            except AssertionError:
                rejected_mutations.append(kind)
            else:
                raise AssertionError("MUTATION_ACCEPTED: " + kind)
        result[slot + ".public.proposed.json"] = encoded(public)
        result[slot + ".private.proposed.json"] = encoded(private)
        report["cases"].append(
            dict(
                slot=slot,
                candidate_digest=original["artifact_digest"],
                frames=len(public["actions"]),
                exact_model_text_links=len(private["model_field_links"]),
                current_schema_accepts=False,
                current_array_comparison_equivalent=False,
                proposed_schema_accepts=True,
                rejected_mutations=rejected_mutations,
                public_bytes=len(encoded(public)),
                private_bytes=len(encoded(private)),
                old_schema_errors=[
                    dict(path=list(e.absolute_path), validator=e.validator)
                    for e in errors
                ],
            )
        )
    result["mapping-check.json"] = encoded(report)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    for name, body in outputs().items():
        path = HERE / name
        if args.check:
            assert path.read_bytes() == body, name
        else:
            path.write_bytes(body)
    print(
        "PASS: exact model mapping, proposed schema, current-contract refusals; no DB/browser/Provider"
    )


if __name__ == "__main__":
    main()
