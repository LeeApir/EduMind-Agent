"""No paid Provider: deterministic chunks/clocks, raw loopback HTTP, semantic audit."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/acceptance_support"))

from audit_first_screen_v2 import audit
from first_screen_v2 import ParagraphClock, SSEClock, assessed_metrics, qualify, raw_learning_post


def decisions(clock, verdicts):
    return {
        str(c["id"]): {"sha256": c["sha256"], "verdict": v, "reason": "offline public fixture"}
        for c, v in zip(clock.candidates, verdicts, strict=True)
    }


def test_saved_public_sample_one_is_partial_evidence_not_lossless_replay():
    import hashlib

    source = Path(__file__).resolve().parent / "fixtures/acceptance/mvp-0.2-t035-raw.json"
    sample = json.loads(source.read_text())["samples"][0]
    assert len(sample["candidates"]) == 10
    assert "chunks" not in sample and "raw_stream" not in sample
    for candidate in sample["candidates"]:
        text = candidate["public_text"]
        assert hashlib.sha256(text.encode()).hexdigest() == candidate["sha256"]
        # Reuse only the saved candidate text; never invent original boundaries or times.
        rebuilt = "".join(text[i : i + 1] for i in range(len(text)))
        assert rebuilt == text
    assert "**2." in sample["candidates"][2]["public_text"]
    assert "```" in sample["candidates"][8]["public_text"]
    decisions_file = source.with_name("mvp-0.2-t035-decisions.json")
    original_decisions = json.loads(decisions_file.read_text())["1"]
    assert qualify(sample["candidates"], original_decisions)["milestone_confirmed"] is False


def test_multiple_candidates_cross_chunk_intro_and_end_are_independent():
    clock = ParagraphClock()
    clock.feed("接下来观察代码。\n", 10)
    assert clock.candidates == []
    clock.feed("\n# 标题\n\n```c\nint *p;\n```\n\n指针保", 20)
    clock.feed("存地址。\n ", 30)
    assert len(clock.candidates) == 1
    clock.feed("\n第三段", 40)
    assert len(clock.candidates) == 2
    assert clock.candidates[1]["first_token_ns"] == 20
    assert clock.candidates[1]["completed_ns"] == 40
    clock.feed("有完整说明。", 50)
    clock.finish(60)
    assert len(clock.candidates) == 3
    assert clock.candidates[-1]["completed_ns"] == 60
    result = qualify(clock.candidates, decisions(clock, ["intro", "teaching", "teaching"]))
    assert result["first_teaching_candidate"]["id"] == 2
    assert qualify(clock.candidates, {})["milestone_confirmed"] is False
    bad = decisions(clock, ["unconfirmed", "teaching", "teaching"])
    assert qualify(clock.candidates, bad)["milestone_confirmed"] is False
    evidence = {
        "started_ns": 0,
        "validated_ns": 5,
        "milestones_ns": {"sse_status": 7},
        "candidates": clock.candidates,
        "status": "published",
        "errors": [],
    }
    metrics = assessed_metrics(evidence, decisions(clock, ["intro", "teaching", "teaching"]))
    assert metrics["client_ms"]["teaching_token"] == 20 / 1e6
    assert metrics["client_ms"]["teaching_paragraph"] == 40 / 1e6
    assert metrics["validated_ms"]["teaching_token"] == 15 / 1e6
    assert metrics["outcome_success"] is True


def test_intro_only_interruption_and_incomplete_sentences_are_not_teaching():
    clock = ParagraphClock()
    clock.feed("接下来讲解。\n\n半段未完成", 10)
    # Interruption does not call finish, cannot invent a completion time.
    assert len(clock.candidates) == 1
    assert qualify(clock.candidates, decisions(clock, ["intro"]))["milestone_confirmed"] is False
    clock.finish(20)
    assert not clock.candidates[-1]["sentence_terminated"]
    assert (
        qualify(clock.candidates, decisions(clock, ["intro", "teaching"]))["milestone_confirmed"]
        is False
    )


def test_fence_without_blank_line_does_not_invent_boundary_or_lose_prose():
    clock = ParagraphClock()
    clock.feed("指针保存地址。\n```c\nint *p;\n```", 10)
    assert clock.candidates == []
    clock.finish(20)
    assert clock.candidates[0]["text"] == "指针保存地址。"
    assert clock.candidates[0]["first_token_ns"] == 10
    assert clock.candidates[0]["completed_ns"] == 20


def test_markdown_delimiters_alone_are_not_teaching_body_tokens():
    clock = ParagraphClock()
    clock.feed("**", 10)
    clock.feed("指针保存地址。**\n\n", 20)
    assert clock.candidates[0]["first_token_ns"] == 20


def test_full_plan_audit_retains_unconfirmed_samples_and_failures():
    clock = ParagraphClock()
    clock.feed("导语说明。\n\n指针保存地址。\n\n", 100000000)
    raw = {
        "samples_planned": 20,
        "samples": [
            {
                "number": n,
                "started_ns": 0,
                "validated_ns": 100,
                "milestones_ns": {"http_first_byte": 1000, "sse_status": 1000},
                "candidates": clock.candidates,
                "status": "published",
                "errors": [],
            }
            for n in range(1, 21)
        ],
    }
    decision = decisions(clock, ["intro", "teaching"])
    reviewed = {str(n): decision for n in range(1, 21)}
    assert audit(raw, reviewed)["stage_gate_passed"] is True
    del reviewed["2"]
    result = audit(raw, reviewed)
    assert result["stage_gate_passed"] is False
    assert result["metrics"]["client_ms"]["teaching_paragraph"]["missing"] == 1
    raw["samples"][3]["errors"] = ["INTERRUPTED"]
    assert audit(raw, reviewed)["request_failures"] == 1


def test_utf8_split_sse_keeps_first_token_and_publication_separate():
    clock = SSEClock(0)
    for event, payload, now in (
        ("agent_start", {"stage": "preparing"}, 10),
        ("token", {"temporary": True, "delta": "指针保存地址。"}, 20),
        ("stage_changed", {"stage": "reviewing"}, 30),
        ("scene_ready", {}, 40),
        ("done", {"status": "published"}, 50),
    ):
        frame = f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
        for byte in frame:
            clock.feed(bytes([byte]), now)
    assert clock.milestones_ns == {"sse_status": 10, "any_nonempty_token": 20, "published": 40}
    assert clock.paragraphs.candidates[0]["completed_ns"] == 30
    assert "text" not in clock.evidence()["candidates"][0]
    assert "public_text" not in clock.evidence()["candidates"][0]


def test_raw_http_first_byte_precedes_headers_status_and_content_without_paid_calls():
    async def run():
        async def serve(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"H")
            await writer.drain()
            await asyncio.sleep(0.02)
            writer.write(b"TTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
            await writer.drain()
            await asyncio.sleep(0.02)
            frame = b"event: agent_start\ndata: {}\n\n"
            writer.write(f"{len(frame):x}\r\n".encode() + frame + b"\r\n0\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        async with server:
            result = await raw_learning_post(
                port=server.sockets[0].getsockname()[1],
                cookie="offline",
                csrf="offline",
                key="offline",
                goal="public",
            )
        times = result.milestones_ns
        assert times["http_first_byte"] < times["http_headers_complete"] < times["sse_status"]
        assert "any_nonempty_token" not in times
        assert result.status == "incomplete"

    asyncio.run(run())


def test_wire_timeout_retained_without_finishing_pending_paragraph():
    async def run():
        released = asyncio.Event()

        async def serve(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            try:
                await released.wait()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        async with server:
            result = await raw_learning_post(
                port=server.sockets[0].getsockname()[1],
                cookie="offline",
                csrf="offline",
                key="offline",
                goal="public",
                timeout=0.02,
            )
            released.set()
            await asyncio.sleep(0.01)
        assert result.errors == ["TOTAL_TIMEOUT"]
        assert result.paragraphs.candidates == []
        assert not result.paragraphs.ended

    asyncio.run(run())


def test_whitespace_boundary_arrival_is_not_token_or_invented_completion():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/acceptance_support"))
    from first_screen_v2 import ParagraphClock

    clock = ParagraphClock()
    clock.feed(" ", 1)
    clock.feed("指针保存地址。", 10)
    clock.feed("\n", 20)
    assert clock.candidates == []
    clock.feed("\n", 30)
    assert clock.candidates[0]["first_token_ns"] == 10
    assert clock.candidates[0]["completed_ns"] == 30
    for fragment in ("`", "`", "`c", "\n", "    int *p;", "\n", "`", "``", "\n", "\n"):
        clock.feed(fragment, 40)
    clock.feed("下一段完整正文。", 50)
    clock.finish(60)
    assert [c["text"] for c in clock.candidates] == ["指针保存地址。", "下一段完整正文。"]
    assert clock.candidates[1]["completed_ns"] == 60
