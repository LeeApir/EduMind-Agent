"""Acceptance-only context-local timing. No arguments, SQL, credentials or results logged."""

import time
from contextvars import ContextVar
from functools import wraps

CURRENT = ContextVar("acceptance_timeline", default=None)


class Timeline:
    def __init__(self):
        self.started_ns = time.monotonic_ns()
        self.spans = []
        self.sent = {}
        self.phase = "anonymous_session"

    def wrap(self, name, function):
        @wraps(function)
        async def measured(*args, **kwargs):
            timeline = CURRENT.get()
            if timeline is None:
                return await function(*args, **kwargs)
            entry = {"stage": name, "request": timeline.phase, "start_ns": time.monotonic_ns()}
            timeline.spans.append(entry)
            try:
                return await function(*args, **kwargs)
            finally:
                entry["end_ns"] = time.monotonic_ns()
                entry["duration_ms"] = (entry["end_ns"] - entry["start_ns"]) / 1e6

        return measured


def install(monkeypatch, timeline):
    """Instrument real function calls only in the isolated diagnostic test process."""
    from app.agents.profile_agent import ProfileAgent
    from app.api import learning_sessions
    from app.core import auth
    from app.services import first_learning

    for module, name, stage in (
        (learning_sessions, "reserve_operation", "operation_reservation_db"),
        (learning_sessions, "owned_operation", "stream_operation_read_db"),
        (learning_sessions, "update_operation", "stream_operation_update_db"),
        (learning_sessions, "resolve_goal_node", "knowledge_node_resolution"),
        (learning_sessions, "prepare_first_learning", "preparation_total"),
        (learning_sessions, "finalize_learning_unit", "generation_review_publication"),
        (first_learning, "create_transient_profile", "profile_extraction_merge_db"),
        (first_learning, "plan_or_replan_path", "path_locked_snapshot_db"),
        (ProfileAgent, "extract", "profile_provider_extraction"),
    ):
        monkeypatch.setattr(module, name, timeline.wrap(stage, getattr(module, name)))
    # FastAPI has already captured the auth call in its dependency tree.
    from app.main import app

    def dependencies(dependant):
        for dependency in dependant.dependencies:
            if dependency.call is auth.require_authenticated_session:
                monkeypatch.setattr(
                    dependency, "call", timeline.wrap("cookie_csrf_auth_db", dependency.call)
                )
            dependencies(dependency)

    for route in app.routes:
        if hasattr(route, "dependant"):
            dependencies(route.dependant)
