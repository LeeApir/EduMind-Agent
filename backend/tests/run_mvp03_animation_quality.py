"""Run the frozen T032 100-slot template matrix with actual Manim rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.animation_templates.deletion_plan import plan_deletion  # noqa: E402
from app.animation_templates.insertion_plan import plan_insertion  # noqa: E402
from app.services.animation_cache import AnimationCache  # noqa: E402
from app.services.animation_templates import load_template  # noqa: E402


def ordered_nodes(head: str | None, links: tuple[tuple[str, str | None], ...]) -> list[str]:
    edges = dict(links)
    visited: list[str] = []
    current = head
    while current is not None:
        assert current in edges and current not in visited
        visited.append(current)
        current = edges[current]
    return visited


def correct_links(template_id: str, parameters: dict[str, object]) -> None:
    values = parameters["values"]
    index = parameters["index"]
    assert isinstance(values, list) and isinstance(index, int)
    if template_id == "linked-list-insertion":
        value = parameters["value"]
        assert isinstance(value, int)
        frames = plan_insertion(values, index, value)
        assert frames[2].stage == "save_successor"
        assert frames[3].stage == "link_predecessor"
        final = frames[-1]
        traversed = ordered_nodes(final.head, final.links)
        actual = [value if node == "new" else values[int(node[1:])] for node in traversed]
        assert actual == values[:index] + [value] + values[index:]
    else:
        frames = plan_deletion(values, index)
        assert [frame.stage for frame in frames[2:5]] == [
            "save_successor", "relink", "release",
        ]
        final = frames[-1]
        traversed = ordered_nodes(final.head, final.links)
        assert f"n{index}" not in traversed
        actual = [values[int(node[1:])] for node in traversed]
        assert actual == values[:index] + values[index + 1:]


def save(path: Path, report: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def run(plan_path: Path, output: Path, cache_root: Path) -> None:
    if output.exists():
        raise RuntimeError("Refusing to overwrite an existing report")
    plan = json.loads(plan_path.read_text())
    slots = plan["quality_slots"]
    assert len(slots) == 100 and len({slot["id"] for slot in slots}) == 100
    assert [slot["template_id"] for slot in slots].count("linked-list-insertion") == 50
    assert [slot["template_id"] for slot in slots].count("linked-list-deletion") == 50
    cache = AnimationCache(cache_root)
    report: dict[str, object] = {
        "plan": str(plan_path.resolve().relative_to(ROOT)),
        "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "baseline_commit": plan["baseline_commit"],
        "host": {"platform": platform.platform(), "machine": platform.machine()},
        "cache_root": str(cache_root), "concurrency": 1,
        "slots": [],
    }
    save(output, report)
    results: list[dict[str, object]] = report["slots"]  # type: ignore[assignment]
    for position, slot in enumerate(slots, 1):
        started = time.monotonic()
        result = {"id": slot["id"], "template_id": slot["template_id"],
                  "case": slot["case"], "parameters": slot["parameters"]}
        try:
            spec = load_template(slot["template_id"], require_executable=True)
            assert spec.review["source_status"] == "approved"
            correct_links(slot["template_id"], slot["parameters"])
            media = cache.resolve(slot["template_id"], slot["parameters"])
            assert cache.validate(media, slot["parameters"])
            assert media.mp4_path.stat().st_size > 0 and media.srt_path.stat().st_size > 0
            result.update({
                "ok": True, "cache_hit": media.cache_hit,
                "duration_seconds": media.duration_seconds,
                "mp4_sha256": media.mp4_sha256, "srt_sha256": media.srt_sha256,
            })
        except Exception as error:
            result.update({"ok": False, "error_type": type(error).__name__,
                           "error": str(error)[:160]})
        result["elapsed_seconds"] = round(time.monotonic() - started, 4)
        results.append(result)
        save(output, report)
        print(f"quality {position}/100 {slot['id']} ok={result['ok']}", flush=True)
    success = sum(item["ok"] is True for item in results)
    report["summary"] = {
        "planned": 100, "passed": success, "failed": 100 - success,
        "availability": success / 100,
        "fresh_rendered": sum(item.get("cache_hit") is False for item in results),
    }
    save(output, report)
    print(json.dumps(report["summary"]), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    args = parser.parse_args()
    run(args.plan, args.output, args.cache_root)
