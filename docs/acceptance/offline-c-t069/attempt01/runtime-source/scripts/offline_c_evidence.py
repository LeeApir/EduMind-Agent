"""Offline evidence integrity and fixed contract checks; no Docker/model/DB calls."""

from __future__ import annotations

import json

from offline_c_fixtures import (
    ROOT,
    FIXTURES,
    AdmissionError,
    check_manifest,
    safe_file,
    sha,
)

EXECUTION_FILES = [
    "scripts/offline_c_runner.py",
    "scripts/offline_c_runtime/controller.py",
    "scripts/offline_c_ownership.py",
    "scripts/offline_c_ownership_results.py",
    "scripts/offline_c_docker.py",
    "scripts/offline_c_evidence.py",
    "scripts/run_offline_c_checks.py",
    "scripts/check_offline_c_report.py",
]
CASE_KEYS = {
    "version",
    "run_id",
    "case_id",
    "source_id",
    "bindings",
    "toolchain",
    "isolation",
    "kind",
    "fault_at",
    "commands",
    "status",
    "reason",
    "observations",
    "expected_observation_matched",
    "scope_limitations",
}
REPORT_KEYS = {
    "version",
    "run_id",
    "suite",
    "provider_calls",
    "cases",
    "preflight",
    "stopped",
    "execution_counts_are_confirmed_minimum",
    "compilations",
    "sample_processes",
    "execution_sources",
    "execution_baseline_commit",
    "evidence_index",
    "report_binding",
}


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def source_snapshot():
    return {name: sha(safe_file(ROOT, name).read_bytes()) for name in EXECUTION_FILES}


def seal_report(report, directory):
    report.setdefault("execution_sources", source_snapshot())
    if report["execution_sources"] != source_snapshot():
        report["stopped"] = {
            "type": "binding_mismatch",
            "message": "executor source changed during run",
        }
    case_dir = directory / "cases"
    case_dir.mkdir(exist_ok=True)
    report["evidence_index"] = []
    for index, case in enumerate(report["cases"]):
        relative = f"cases/{index:03}.json"
        data = json.dumps(case, ensure_ascii=False, indent=2).encode() + b"\n"
        (directory / relative).write_bytes(data)
        report["evidence_index"].append(
            {
                "path": relative,
                "sha256": sha(data),
                "source_id": case["source_id"],
                "case_id": case["case_id"],
            }
        )
    report.pop("report_binding", None)
    report["report_binding"] = sha(canonical(report))
    data = json.dumps(report, ensure_ascii=False, indent=2).encode() + b"\n"
    (directory / "report.json").write_bytes(data)
    (directory / "report.seal.json").write_text(
        json.dumps(
            {
                "version": "fixed-c-report-seal-v1",
                "report_sha256": sha(data),
                "binding": report["report_binding"],
            },
            indent=2,
        )
        + "\n"
    )


def expected_schedule(suite):
    base = [
        (s, c)
        for s in ["edumind-r02-original", "om-original"]
        for c in ["strict", "ordinary", "normal", "sanitized-normal"]
    ]
    owned = [
        (s, f"{mode}-{n}")
        for s in ["edumind-r02-original", "om-original"]
        for mode in ["program", "contract"]
        for n in range(4)
    ]
    owned += [
        ("edumind-r02-original", "negative-" + n)
        for n in ["drop-link", "double-free", "ignored-return"]
    ]
    if suite not in {"compile-output", "ownership", "all"}:
        raise AdmissionError("unregistered suite")
    return (
        base
        if suite == "compile-output"
        else owned
        if suite == "ownership"
        else base + owned
    )


def expected_commands(source, case):
    owned = case.startswith(("program-", "contract-"))
    negative = case.startswith("negative-")
    src = (
        "edumind/candidate.c"
        if source == "edumind-r02-original"
        else "om/original-program.c"
    )
    if (
        owned
        and (source == "edumind-r02-original" or case.startswith("contract-"))
        or negative
    ):
        src = (
            "edumind" if source == "edumind-r02-original" else "om"
        ) + "/ownership-driver.c"
    flags = ["-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Wnewline-eof"]
    if case == "strict":
        flags += ["-Werror"]
    if case == "sanitized-normal" or owned or negative:
        flags += [
            "-O0",
            "-g",
            "-fno-omit-frame-pointer",
            "-fsanitize=address,undefined",
            "-fno-sanitize-recover=all",
        ]
    if negative:
        flags += [f'-DSOURCE_C="{case}.c"']
    compiler = ["/usr/bin/clang-19", *flags, "/bundle/" + src, "-o", "/work/program"]
    program = ["/work/program"]
    if owned:
        program += [
            "program" if case.startswith("program-") else "contract",
            case.rsplit("-", 1)[1],
        ]
    if negative:
        program += ["program", "0"]
    return compiler, program


def raw_verdict(case):
    commands = case["commands"]
    if not commands:
        raise AdmissionError("no stage evidence; execution incomplete")
    first = commands[0]
    if first["timeout"]:
        return "fail", "timeout"
    if first["output_limit"]:
        return "fail", "output_limit"
    if first["exit_code"] != 0:
        return (
            ("fail", "compile_error")
            if case["case_id"] in {"strict", "ordinary"}
            else ("not_run", "compile_failed")
        )
    if case["case_id"] in {"strict", "ordinary"}:
        if len(commands) != 1:
            raise AdmissionError("compile-only case ran extra stage")
        return "pass", "success"
    if len(commands) != 2:
        raise AdmissionError("missing program stage")
    run = commands[1]
    if run["timeout"]:
        return "fail", "timeout"
    if run["output_limit"]:
        return "fail", "output_limit"
    return ("pass", "success") if run["exit_code"] == 0 else ("fail", "runtime_error")


def check_report(path):
    from offline_c_runner import (
        LOCK_PATH,
        LOCK_SHA256,
        check_probe,
        interpret_case,
        validate_commands,
    )
    from offline_c_ownership import check_ownership, MANIFEST_SHA256 as OWN_SHA

    raw = safe_file(path.parent, path.name).read_bytes()
    if len(raw) > 4 * 1048576:
        raise AdmissionError("report too large")
    report = json.loads(raw)
    if set(report) != REPORT_KEYS:
        raise AdmissionError("report fields mismatch")
    seal = json.loads(safe_file(path.parent, "report.seal.json").read_bytes())
    if seal["report_sha256"] != sha(raw):
        raise AdmissionError("report bytes changed")
    original_binding = report["report_binding"]
    unbound = {k: v for k, v in report.items() if k != "report_binding"}
    if (
        original_binding != sha(canonical(unbound))
        or seal["binding"] != original_binding
    ):
        raise AdmissionError("report binding mismatch")
    if report["execution_sources"] != source_snapshot():
        raise AdmissionError("executor version mismatch; use exact frozen source")
    if report["provider_calls"] != 0 or report["version"] != "fixed-c-report-v1":
        raise AdmissionError("wrong protocol")
    import re
    import subprocess

    baseline = report["execution_baseline_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise AdmissionError("invalid execution baseline")
    subprocess.run(
        ["git", "cat-file", "-e", baseline + "^{commit}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    check_manifest()
    lock_raw = LOCK_PATH.read_bytes()
    if sha(lock_raw) != LOCK_SHA256:
        raise AdmissionError("toolchain lock mismatch")
    lock = json.loads(lock_raw)
    check_probe(report["preflight"]["probe"], lock)
    if (
        report["preflight"]["host_timeout"]["reason"] != "timeout"
        or report["preflight"]["host_output"]["reason"] != "output_limit"
    ):
        raise AdmissionError("missing effective limit probes")
    child = report["preflight"]["child_output"]
    validate_commands([child])
    if not child["output_limit"] or child["stdout"]["bytes"] != 65536:
        raise AdmissionError("missing child output cap")
    manifest = json.loads((ROOT / FIXTURES / "manifest.json").read_bytes())
    if report["suite"] in {"all", "ownership"}:
        ext = check_ownership()
        manifest["artifacts"] = {**manifest["artifacts"], **ext["artifacts"]}
        manifest.update(
            _ownership_digest=OWN_SHA, _ownership_review=ext["review_registry_sha256"]
        )
    schedule = expected_schedule(report["suite"])
    if [(c["source_id"], c["case_id"]) for c in report["cases"]] != schedule:
        raise AdmissionError("case list incomplete, duplicate or reordered")
    if len(report["evidence_index"]) != len(schedule):
        raise AdmissionError("case index incomplete")
    pre_digest = sha(json.dumps(report["preflight"], sort_keys=True).encode())
    compilation_count = run_count = 0
    for i, case in enumerate(report["cases"]):
        if set(case) != CASE_KEYS or case["run_id"] != report["run_id"]:
            raise AdmissionError("case identity/fields mismatch")
        entry = report["evidence_index"][i]
        if entry["path"] != f"cases/{i:03}.json":
            raise AdmissionError("unsafe/incorrect evidence path")
        data = safe_file(path.parent, entry["path"]).read_bytes()
        if sha(data) != entry["sha256"] or json.loads(data) != case:
            raise AdmissionError("case evidence changed/missing")
        if (entry["source_id"], entry["case_id"]) != schedule[i]:
            raise AdmissionError("cross-sample index")
        if case["toolchain"] != lock:
            raise AdmissionError("mixed toolchain")
        from offline_c_docker import container_argv

        isolation = case["isolation"]
        required_limits = {
            "NetworkMode": "none",
            "IpcMode": "none",
            "ReadonlyRootfs": True,
            "Memory": 536870912,
            "MemorySwap": 536870912,
            "NanoCpus": 1000000000,
            "PidsLimit": 64,
        }
        if (
            isolation["effective"] != required_limits
            or isolation["user"] != "10001:10001"
            or isolation["cap_drop"] != ["ALL"]
            or isolation["security_opt"] != ["no-new-privileges:true"]
        ):
            raise AdmissionError("case isolation metadata inconsistent")
        argv = isolation["container_argv"]
        mount = argv[argv.index("--mount") + 1]
        if not mount.startswith("type=bind,source=/") or not mount.endswith(
            ",target=/bundle,readonly"
        ):
            raise AdmissionError("wrong bundle mount")
        source_path = mount[len("type=bind,source=") : -len(",target=/bundle,readonly")]
        if "," in source_path or "\n" in source_path:
            raise AdmissionError("invalid bundle path")
        if argv != container_argv(
            lock["image_id"],
            argv[argv.index("--name") + 1],
            Path(source_path),
            [case["source_id"], case["case_id"]],
        ):
            raise AdmissionError("case container command changed")
        validate_commands(case["commands"])
        expected_compile, expected_run = expected_commands(
            case["source_id"], case["case_id"]
        )
        if case["commands"] and case["commands"][0]["argv"] != expected_compile:
            raise AdmissionError("wrong compiler/source/flags")
        if len(case["commands"]) == 2 and case["commands"][1]["argv"] != expected_run:
            raise AdmissionError("wrong program/arguments")
        status, reason = raw_verdict(case)
        result = {
            "reason": None,
            "exit_code": 0,
            "stdout": json.dumps(
                {"commands": case["commands"], "status": status, "reason": reason}
            ).encode(),
            "stderr": b"",
            "isolation": case["isolation"],
            "argv": case["isolation"]["container_argv"],
        }
        derived = interpret_case(
            lock,
            ROOT / FIXTURES,
            case["source_id"],
            case["case_id"],
            manifest,
            pre_digest,
            result,
        )
        for key in [
            "status",
            "reason",
            "observations",
            "expected_observation_matched",
            "kind",
            "fault_at",
            "scope_limitations",
        ]:
            if derived[key] != case[key]:
                raise AdmissionError("unsupported conclusion/observation: " + key)
        # Baseline is the actual historical run commit; other binding digests must recompute.
        if case["bindings"]["baseline_commit"] != baseline:
            raise AdmissionError("mixed baseline commit")
        derived["bindings"]["baseline_commit"] = baseline
        if derived["bindings"] != case["bindings"]:
            raise AdmissionError("cross-source/spec/driver binding")
        if (
            case["isolation"]["preflight_sha256"] != pre_digest
            or case["isolation"]["cleanup"] != "removed"
        ):
            raise AdmissionError("preflight or cleanup binding")
        compilation_count += 1
        run_count += len(case["commands"]) - 1
    if (report["compilations"], report["sample_processes"]) != (
        compilation_count,
        run_count,
    ):
        raise AdmissionError("wrong usage counters")
    complete = report["stopped"] is None and all(
        c["expected_observation_matched"] is True for c in report["cases"]
    )
    return {
        "integrity_valid": True,
        "execution_complete": complete,
        "expected_observations_matched": complete,
        "cases": len(schedule),
        "program_pass": sum(c["status"] == "pass" for c in report["cases"]),
        "program_fail": sum(c["status"] == "fail" for c in report["cases"]),
        "not_run": sum(c["status"] == "not_run" for c in report["cases"]),
        "provider_calls": 0,
        "publication_qualified": False,
        "meaning": "offline fixed cases only; hashes are not remote execution attestation",
    }
