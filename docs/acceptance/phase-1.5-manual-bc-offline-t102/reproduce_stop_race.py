"""Offline synthetic reproduction: job delivered after stop_unconfirmed."""

import threading
import time

from scripts.isolated_diagnostics import p15_manual_supervisor_v1 as m

original = m.SpawnOnlyPopen
entered = threading.Event()
release = threading.Event()
state = {}


def delayed_spawn(*args, **kwargs):
    process = original(*args, **kwargs)
    communicate = process.communicate

    def delayed_communicate(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        state["job_sent_after_stop"] = time.monotonic() > state["stop_return"]
        out = communicate(*args, **kwargs)
        state["child_acted"] = b"fixture" in out[0]
        return out

    process.communicate = delayed_communicate
    return process


m.SpawnOnlyPopen = delayed_spawn
instance = m.ManualSupervisor("generation", "synthetic-one-role", m.child_digest(), m.interpreter_digest())


def send():
    try:
        now = time.monotonic()
        state["result"] = instance.dispatch("fixture", batch_deadline=now + 10, request_deadline=now + 10)
    except BaseException as exc:
        state["error"] = str(exc)


thread = threading.Thread(target=send)
thread.start()
assert entered.wait(5)
with instance._lock:
    state["stop"] = instance.stop(0.05)
    state["stop_return"] = time.monotonic()
    release.set()
thread.join(5)
print("stop=", state["stop"])
print("job_sent_after_stop=", state.get("job_sent_after_stop"))
print("child_acted=", state.get("child_acted"))
print("result_error=", state.get("error"))
print("provider_calls=0")
assert state["stop"] == "stop_unconfirmed"
assert state["job_sent_after_stop"] and state["child_acted"]
assert state["error"] == "STOPPED_RESULT_IGNORED"
