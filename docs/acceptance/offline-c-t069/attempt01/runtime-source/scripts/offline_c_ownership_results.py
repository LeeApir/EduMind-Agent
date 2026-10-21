"""Check actual emitted fixed-driver states, never infer UB final values."""
import base64
import json
import re


def observe(source, case, value, commands, bundle):
    fields = ["numeric_sequence", "format_exact", "attempts", "allocated", "released", "live", "per_insert_states", "free_call_sequence", "caller_head_reset"]
    observation = dict.fromkeys(fields)
    observation.update(asan="not_run", ubsan="not_run", lsan="not_run")
    if len(commands) != 2:
        stderr = base64.b64decode(commands[0]["stderr"]["base64"]).decode("utf-8", "replace") if commands else ""
        return observation, source == "om-original" and case.startswith("program-") and value["reason"] == "compile_failed" and "Node" in stderr
    run = commands[1]
    stderr = base64.b64decode(run["stderr"]["base64"]).decode("utf-8", "replace")
    stdout = base64.b64decode(run["stdout"]["base64"])
    events = [json.loads(line[6:]) for line in stderr.splitlines() if line.startswith("EVENT ")]
    states = [e for e in events if e["event"] == "insert_state"]
    frees = [e["slot"] for e in events if e["event"] == "free"]
    allocations = [e["slot"] for e in events if e["event"] == "allocate"]
    summaries = [e for e in events if e["event"] == "summary"]
    attempts = [e for e in events if e["event"] == "attempt"]
    observation.update(per_insert_states=states, free_call_sequence=frees,
                       asan="instrumented execution; inspect actual diagnostic/exit",
                       ubsan="instrumented execution; inspect actual diagnostic/exit")
    if case.startswith("negative-"):
        expected = value["status"] == "fail" and not run["timeout"] and not run["output_limit"]
        expected = expected and ("unknown or repeated release" in stderr if case == "negative-double-free" else "snapshot" in stderr and "Assertion" in stderr)
        if expected:
            value["reason"] = "assertion_failed"
        return observation, expected
    fail = int(case.rsplit("-", 1)[1])
    if source == "om-original" and fail:
        # The actual injected failure reaches original NULL access. No complete summary exists.
        expected = value["status"] == "fail" and "null pointer" in stderr.lower() and not summaries
        expected = expected and bool(attempts) and attempts[-1]["step"] == fail and attempts[-1]["injected"] and attempts[-1]["prior_live"] == fail-1
        observation["ubsan"] = "reported reachable NULL member access" if "null pointer" in stderr.lower() else "no matching diagnostic"
        return observation, bool(expected)
    expected_values = [n for n in range(3, 0, -1) if n != fail]
    numeric = [int(n) for n in re.findall(rb"-?\d+", stdout)]
    exact = (" ".join(map(str, expected_values))+" \n").encode() if source == "edumind-r02-original" else b"3 -> 2 -> 1 -> NULL\n"
    observation.update(numeric_sequence=numeric, format_exact={"independent": stdout == exact})
    valid = value["status"] == "pass" and numeric == expected_values and stdout == exact and len(summaries) == 1
    valid = valid and [e["step"] for e in states] == [1, 2, 3]
    for state in states:
        values = [n for n in range(state["step"], 0, -1) if n != fail]
        valid = valid and state["values"] == values and state["count"] == len(values)
        basis = "caller_head_after_assignment" if case.startswith("contract-") else None
        valid = valid and (state["basis"] == basis if basis else state["basis"].startswith("allocation_root_"))
    if summaries:
        summary = summaries[0]
        observation.update({k: summary[k] for k in ["attempts", "allocated", "released", "live"]})
        observation["caller_head_reset"] = {"value": summary["caller_reset"], "by": summary["reset_by"]}
        count = len(expected_values)
        valid = valid and summary["attempts"] == 3 and summary["allocated"] == summary["released"] == count and summary["live"] == 0
        valid = valid and allocations == list(range(count)) and frees == list(range(count-1, -1, -1))
        if case.startswith("contract-"):
            valid = valid and summary["caller_reset"] is True
    return observation, bool(valid)
