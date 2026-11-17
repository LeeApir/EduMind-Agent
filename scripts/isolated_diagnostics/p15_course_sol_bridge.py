"""Offline-only first-slot bridge; no credentials, DNS, PG or live transport."""

import copy
import hashlib
import json

import httpx

from isolated_diagnostics import p15_sol_compatibility_proposal as compat

STAGE = "development_scene_review"
ENDPOINT = "https://aiapi.world/v1/responses"
PROMPT = (compat.BASE / "scene-review-prompt.txt").read_text()


def review_request(stage, payload):
    if stage != STAGE:
        raise ValueError("SCENE_ONLY_PROBES_NOT_ADMITTED")
    source = payload["source"]
    # Validate the caller's digest rather than silently recomputing/repairing it.
    rebuilt = compat.original.review_source(**source)
    if payload != rebuilt:
        raise ValueError("EXACT_SOURCE_ENVELOPE_REQUIRED")
    return {
        "model": "gpt-6.1-sol",
        "reasoning": {"effort": "low"},
        "stream": False,
        "store": False,
        "max_output_tokens": 8000,
        "input": [
            {"role": "system", "content": PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "development_scene_review",
                "strict": True,
                "schema": compat.schema(),
            }
        },
    }


class MockCourseReview:
    """Once per exact owner/course/source. Any exception seals this instance."""

    def __init__(self, transport, *, owner, course):
        if not isinstance(transport, httpx.MockTransport):
            raise ValueError("MOCK_TRANSPORT_REQUIRED")
        if not owner or not course:
            raise ValueError("OWNER_COURSE_REQUIRED")
        self.transport = transport
        self.identity = (owner, course)
        self.started = set()
        self.events = []
        self.stopped = False

    async def review(self, *, owner, course, payload, verify_current):
        if self.stopped:
            raise ValueError("STOPPED_NO_RESTART")
        if (owner, course) != self.identity:
            raise ValueError("OWNER_COURSE_CHANGED")
        payload = copy.deepcopy(payload)
        body = review_request(STAGE, payload)
        key = payload["source_sha256"]
        if key in self.started:
            raise ValueError("INTERRUPTED_OR_COMPLETED_REVIEW_NO_RESEND")
        self.started.add(key)
        try:
            if await verify_current(copy.deepcopy(payload)) is not True:
                raise ValueError("SOURCE_NO_LONGER_CURRENT")
            async with httpx.AsyncClient(
                transport=self.transport, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(ENDPOINT, json=body)
            if response.status_code != 200:
                raise ValueError("RESPONSE_STATUS_FAILED")
            if len(response.content) > 2097152:
                raise ValueError("RESPONSE_TOO_LARGE")
            result = compat.validate_envelope(body, response.json(), payload)
            if await verify_current(copy.deepcopy(payload)) is not True:
                raise ValueError("SOURCE_CHANGED_DURING_REVIEW")
            event = {
                "owner": owner,
                "course": course,
                "source_sha256": key,
                "response_sha256": hashlib.sha256(response.content).hexdigest(),
                "opinion": result["opinion"],
                "reported_output_tokens_including_reasoning": result[
                    "reported_output_tokens_including_reasoning"
                ],
                "mock_only": True,
                "review_type": "model_advisory",
                "independent_human_truth": False,
                "production_admission": False,
                "state": (
                    "delegated_assistant_review_required"
                    if result["verdict"] == "pass"
                    else "paused_for_delegated_assistant"
                ),
            }
            self.events.append(copy.deepcopy(event))
            # Model pass never substitutes for the delegated assistant checkpoint.
            self.stopped = True
            return event
        except BaseException:
            self.stopped = True
            raise
