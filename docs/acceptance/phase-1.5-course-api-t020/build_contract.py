"""Build/check the additive approved T001/T002/T003 runtime DTO contract."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    merged = dict(
        openapi="3.1.0",
        info=dict(title="EduMind Free Course API (T020)", version="phase-1.5-t020"),
        paths={},
        components=dict(schemas={}, parameters={}, securitySchemes={}),
    )
    sources = []
    for stem in ["free-course", "generation", "quality"]:
        relative = f"docs/api/phase-1.5-{stem}.openapi.json"
        path = ROOT / relative
        value = json.loads(path.read_text())
        sources.append(
            dict(path=relative, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        )
        for route, methods in value["paths"].items():
            merged["paths"].setdefault(route, {}).update(methods)
        for section in ["schemas", "parameters", "securitySchemes"]:
            merged["components"][section].update(value["components"].get(section, {}))
    # ADR0028 source stays frozen; publish only the T047 implemented index projection.
    relative = "docs/api/phase-1.5-record-read.proposed.openapi.json"
    read_source = ROOT / relative
    supplement = json.loads(read_source.read_text())
    sources.append(dict(path=relative, sha256=hashlib.sha256(read_source.read_bytes()).hexdigest()))
    route = "/api/free-courses/{course_id}/records"
    merged["paths"][route] = supplement["paths"][route]
    merged["paths"][route]["get"]["x-status"] = "implemented"
    for name in ["RecordRef", "RecordPage"]:
        merged["components"]["schemas"][name] = supplement["components"]["schemas"][name]
    merged["components"]["securitySchemes"].update(supplement["components"]["securitySchemes"])
    merged["components"]["schemas"]["SceneProjection"]["properties"]["blocks"]["items"][
        "oneOf"
    ].append({"$ref": "#/components/schemas/DisabledExerciseBlock"})
    merged["x-contract-sources"] = sources
    merged["x-integration"] = (
        "T001 base + T002 generation + approved T003 quality/tutor DTOs; tutor routes integrated in T045; ADR0028 owner record index integrated in T047"
    )
    for route, method in [
        ("/api/free-courses/{course_id}/operations/{operation_id}", "get"),
        ("/api/free-courses/{course_id}/operations/{operation_id}/cancel", "post"),
    ]:
        merged["paths"][route][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"] = {
            "oneOf": [
                {"$ref": "#/components/schemas/Operation"},
                {"$ref": "#/components/schemas/TutorOperation"},
            ]
        }
    merged["paths"]["/api/free-courses/{course_id}/operations/{operation_id}/events"][
        "get"
    ]["x-event-schemas"] = ["Event", "TutorEvent"]
    raw = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode()
    for relative in [
        "backend/app/contracts/free_course.openapi.json",
        "docs/api/phase-1.5-free-course.runtime.openapi.json",
    ]:
        path = ROOT / relative
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit("Cumulative contract differs: " + relative)
        else:
            path.write_bytes(raw)
    print("Cumulative T020 contract matches approved source projections")


if __name__ == "__main__":
    main()
