"""Private reviewed media cache: reuse, corruption, versions and concurrency."""

import hashlib
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from app.animation_templates.deletion_plan import srt_for_deletion
from app.animation_templates.insertion_plan import srt_for_insertion
from app.services.animation_cache import (
    AnimationCache,
    UnsupportedAnimationError,
    runtime_identity,
)
from app.services.animation_renderer import RenderedCandidate
from app.services.animation_templates import TemplateValidationError

INSERT = {"values": [1, 3, 5], "index": 1, "value": 2}


def fake_renderer(calls: list[str]):
    def render(
        template_id: str, parameters: dict[str, object], *, work_root: Path
    ) -> RenderedCandidate:
        calls.append(template_id)
        time.sleep(0.02)
        attempt = Path(tempfile.mkdtemp(prefix="fake-", dir=work_root))
        mp4 = attempt / "scene.mp4"
        srt = attempt / "scene.srt"
        mp4.write_bytes(
            b"\x00\x00\x00\x18ftypisom" + json.dumps(parameters, sort_keys=True).encode()
        )
        subtitle = srt_for_insertion() if template_id.endswith("insertion") else srt_for_deletion()
        srt.write_text(subtitle, encoding="utf-8")
        return RenderedCandidate(
            attempt, mp4, srt, 36.0 if template_id.endswith("insertion") else 42.0,
            hashlib.sha256(mp4.read_bytes()).hexdigest(),
            hashlib.sha256(srt.read_bytes()).hexdigest(),
        )
    return render


def test_prepared_public_asset_is_hit_without_owner_data(tmp_path: Path) -> None:
    calls: list[str] = []
    cache = AnimationCache(tmp_path, renderer=fake_renderer(calls))
    first = cache.resolve("linked-list-insertion", INSERT)
    second = cache.resolve("linked-list-insertion", dict(reversed(list(INSERT.items()))))
    assert not first.cache_hit and second.cache_hit
    assert first.cache_key == second.cache_key and calls == ["linked-list-insertion"]
    assert first.mp4_path == second.mp4_path and first.srt_path == second.srt_path
    metadata = (tmp_path / "entries" / f"{first.cache_key}.json").read_text()
    assert '"source_status": "approved"' in metadata
    assert "owner" not in metadata and "cookie" not in metadata.lower()


def test_corrupt_media_or_review_metadata_is_never_a_hit(tmp_path: Path) -> None:
    calls: list[str] = []
    cache = AnimationCache(tmp_path, renderer=fake_renderer(calls))
    first = cache.resolve("linked-list-insertion", INSERT)
    first.mp4_path.chmod(0o644)
    first.mp4_path.write_bytes(b"corrupt")
    repaired = cache.resolve("linked-list-insertion", INSERT)
    assert not repaired.cache_hit and len(calls) == 2
    assert repaired.mp4_path.read_bytes() != b"corrupt"
    assert list((tmp_path / "quarantine").iterdir())
    entry = tmp_path / "entries" / f"{first.cache_key}.json"
    record = json.loads(entry.read_text(encoding="utf-8"))
    record["source_status"] = "pending"
    entry.write_text(json.dumps(record), encoding="utf-8")
    assert not cache.resolve("linked-list-insertion", INSERT).cache_hit
    assert len(calls) == 3


def test_runtime_version_changes_cache_key_and_rebuilds(tmp_path: Path) -> None:
    calls: list[str] = []
    original = runtime_identity("linked-list-insertion")
    version = [original]
    cache = AnimationCache(
        tmp_path, renderer=fake_renderer(calls), runtime_factory=lambda _: version[0]
    )
    first = cache.resolve("linked-list-insertion", INSERT)
    version[0] = replace(original, renderer_config_sha256="e" * 64)
    second = cache.resolve("linked-list-insertion", INSERT)
    assert first.cache_key != second.cache_key and not second.cache_hit
    assert len(calls) == 2


def test_same_key_concurrent_requests_render_once(tmp_path: Path) -> None:
    calls: list[str] = []
    cache = AnimationCache(tmp_path, renderer=fake_renderer(calls))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: cache.resolve("linked-list-deletion",
                                                        {"values": [1, 3, 5], "index": 1}),
                                range(8)))
    assert len(calls) == 1
    assert len({result.cache_key for result in results}) == 1
    assert sum(not result.cache_hit for result in results) == 1


def test_unknown_or_private_parameters_never_render(tmp_path: Path) -> None:
    calls: list[str] = []
    cache = AnimationCache(tmp_path, renderer=fake_renderer(calls))
    with pytest.raises(UnsupportedAnimationError, match="没有可用"):
        cache.resolve("linked-list-sort", {"values": [1], "index": 0})
    with pytest.raises(TemplateValidationError):
        cache.resolve("linked-list-insertion", {**INSERT, "owner_id": "private"})
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_cache_root_symlink_cannot_redirect_candidate_files(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    redirected = tmp_path / "cache"
    redirected.symlink_to(outside, target_is_directory=True)
    cache = AnimationCache(redirected, renderer=fake_renderer([]))
    with pytest.raises(ValueError, match="invalid cache directory"):
        cache.resolve("linked-list-insertion", INSERT)
    assert list(outside.iterdir()) == []
