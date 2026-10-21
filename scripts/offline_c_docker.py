"""Fixed Docker isolation arguments shared by preparation and the offline runner."""
import re
from pathlib import Path

ENV = ["PATH=/usr/bin:/bin", "HOME=/tmp", "TMPDIR=/tmp", "LANG=C", "LC_ALL=C",
       "ASAN_OPTIONS=detect_leaks=0:abort_on_error=1:symbolize=0",
       "UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=0"]


def container_argv(image: str, name: str, bundle: Path | None, args: list[str]) -> list[str]:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("exact image digest required")
    if not re.fullmatch(r"edumind-fixed-c-[0-9a-f]{32}", name):
        raise ValueError("private run name required")
    valid = args in [["metadata"], ["probe"], ["probe-loop"], ["probe-output"], ["probe-child-output"]] or (len(args) == 2 and args[0] in {
        "edumind-r02-original", "om-original"} and args[1] in {
        "strict", "ordinary", "normal", "sanitized-normal"})
    if len(args) == 2 and args[0] in {"edumind-r02-original", "om-original"}:
        valid = valid or args[1] in {f"{mode}-{n}" for mode in ["program", "contract"] for n in range(4)}
        valid = valid or (args[0] == "edumind-r02-original" and args[1] in {"negative-drop-link", "negative-double-free", "negative-ignored-return"})
    if not valid:
        raise ValueError("unregistered command")
    argv = ["docker", "run", "--name", name, "--pull=never", "--network=none", "--ipc=none",
            "--user=10001:10001", "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            "--read-only", "--cpus=1", "--memory=512m", "--memory-swap=512m", "--pids-limit=64",
            "--ulimit=core=0:0", "--ulimit=nofile=128:128", "--ulimit=fsize=16777216:16777216",
            "--tmpfs=/work:rw,exec,nosuid,nodev,size=134217728,uid=10001,gid=10001,mode=0700",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16777216,uid=10001,gid=10001,mode=0700",
            "--log-driver=none", "--entrypoint=/usr/bin/env"]
    if bundle is not None:
        if not bundle.is_absolute() or bundle.is_symlink():
            raise ValueError("private absolute bundle required")
        argv += ["--mount", f"type=bind,source={bundle},target=/bundle,readonly"]
    return [*argv, image, "-i", *ENV, "/usr/local/bin/python3", "-I",
            "/opt/fixed-c/controller.py", *args]
