"""T036-only loopback server: actual app/PG/workers, deterministic mock transport."""

import argparse
import asyncio
import ipaddress
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from sqlalchemy.engine import make_url
from test_free_course_planning import candidate
from test_free_course_tutor_scheduler import FakeTutor
from test_free_scene_generation import response

from app.core import provider_factory
from app.core.database import database_lifespan
from app.main import app
from app.services.free_course_scheduler import Reply, Scheduler, SendPolicy
from app.services.free_course_tutor_scheduler import TutorScheduler


def forbidden(*_args, **_kwargs):
    raise RuntimeError("T036_REAL_PROVIDER_FORBIDDEN")


def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        host = (
            args[1][0]
            if event == "socket.connect" and isinstance(args[1], tuple)
            else args[0]
            if event == "socket.getaddrinfo"
            else None
        )
        if host is not None and host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise RuntimeError("T036_EXTERNAL_NETWORK_FORBIDDEN")


class MockTransport:
    policy = SendPolicy(
        package_id="TEST_ONLY_T036", requests=100, fee_micros=0, bounded_output_verified=True
    )

    def __init__(self, output):
        self.output = output
        self.calls = []

    def input_upper_bound(self, request):
        return 1000  # Test fixture only; no actual tokenizer/price or Provider claim.

    async def send(self, request, *, retry_safe):
        assert retry_safe is False
        value = json.loads(request.prompt.messages[1].content)
        if request.stage == "free_course_plan_generation":
            goal = value["original_goal"]
            fail = "局部失败" in goal
            output = candidate(3 if fail else 2, goal)
            for i, item in enumerate(output["plan"]["scenes"]):
                item.update(
                    title=f"明确 Mock 场景 {i + 1}",
                    forms=["text", "code", "exercise", "visualization"],
                )
            await asyncio.sleep(0.2)
        else:
            goal = value["request"]["original_goal"]
            index = next(
                i
                for i, s in enumerate(value["plan"]["scenes"])
                if s["scene_id"] == value["scene_id"]
            )
            fail = "局部失败" in goal and index == 2
            output = {} if fail else response()
            if not fail:
                revision = (value["expected_head"] or 0) >= 3
                output["blocks"][0]["markdown"] = (
                    f"明确 Mock：{'修订后的' if revision else '原始'}场景 {index + 1}。"
                    "数组按下标访问，链表通过 next 连接结点。"
                )
                output["blocks"][1]["source"] = (
                    "n->next = head;\nhead = n;\n/* " + "local_code_reading_" * 15 + " */"
                )
            await asyncio.sleep(0.6)
        self.calls.append({"stage": request.stage, "mock": True, "injected_invalid": output == {}})
        (self.output / "mock-calls.json").write_text(json.dumps(self.calls, indent=2) + "\n")
        return Reply("complete_response", "a" * 64, output, 100, 100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = make_url(os.environ["EDUMIND_DATABASE_URL"])
    assert (
        url.host == "127.0.0.1"
        and url.port == 15437
        and (url.database or "").startswith("edumind_catalog_p15_t036_")
    )
    assert os.environ.get("EDUMIND_PRODUCT_MODE") == "dynamic"
    assert not any(
        k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL", "EDUMIND_REVIEW_CANDIDATE"))
        for k in os.environ
    )
    assert args.output.is_relative_to(Path("/tmp")) and args.output.name.startswith(
        "edumind-p15-t036-"
    )
    provider_factory.build_default_provider_gateway = forbidden
    provider_factory.build_server_provider_gateway = forbidden
    sys.addaudithook(audit)
    transport = MockTransport(args.output)
    tutor = FakeTutor()

    @asynccontextmanager
    async def lifespan(application):
        async with database_lifespan(application) as state:
            sessions = state["database_runtime"].session_factory()
            stop = asyncio.Event()
            tasks = [
                asyncio.create_task(Scheduler(sessions).work(transport, stop)),
                asyncio.create_task(TutorScheduler(sessions).work(tutor, stop)),
            ]
            try:
                yield state
            finally:
                stop.set()
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=15)
                (args.output / "transport-summary.json").write_text(
                    json.dumps(
                        {
                            "mock_generation_calls": len(transport.calls),
                            "mock_tutor_calls": len(tutor.calls),
                            "real_provider_calls": 0,
                            "external_network": "blocked",
                            "production_mode_changed": False,
                        },
                        indent=2,
                    )
                    + "\n"
                )

    app.router.lifespan_context = lifespan
    uvicorn.run(app, host="127.0.0.1", port=8175, log_level="warning")


if __name__ == "__main__":
    main()
