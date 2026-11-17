"""Print stack boundary materials or exact provider-neutral requests, without network access."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.services.free_course_snapshots import canonical
from app.services.stack_multiscene import planning_request, scene_request
from app.services.stack_multiscene_materials import materials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("materials", "plan", "scene"))
    parser.add_argument("snapshot", type=Path, nargs="?")
    args = parser.parse_args()
    if (args.kind == "materials") != (args.snapshot is None):
        parser.error("plan and scene require the corresponding JSON input snapshot")
    if args.snapshot is None:
        result = materials()
    else:
        builder = planning_request if args.kind == "plan" else scene_request
        result = json.loads(json.dumps(asdict(builder(json.loads(args.snapshot.read_bytes())))))
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
