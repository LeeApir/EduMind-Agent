"""Trusted-host operator authentication and safe CLI review projections."""

import json
import os
import stat
from pathlib import Path
from typing import Any

from app.services.learning_contract import LearningContractError


def maintainer_identity(path: Path) -> tuple[str, str]:
    """Trust host admin/current uid config, not a caller-supplied reviewer string."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid not in (0, os.geteuid())
                or info.st_mode & 0o077
                or info.st_size > 16384
            ):
                raise ValueError
            raw = os.read(fd, 16385)
        finally:
            os.close(fd)

        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result

        value = json.loads(raw, object_pairs_hook=unique)
        if set(value) != {"version", "operators"} or value["version"] != "local-reviewers-v1":
            raise ValueError
        matches = [
            r
            for r in value["operators"]
            if set(r) == {"uid", "reviewer_id"}
            and type(r["uid"]) is int
            and r["uid"] == os.geteuid()
        ]
        if len(matches) != 1 or not isinstance(matches[0]["reviewer_id"], str):
            raise ValueError
        reviewer = matches[0]["reviewer_id"]
        if not 1 <= len(reviewer) <= 128 or any(ord(c) < 32 for c in reviewer):
            raise ValueError
        return reviewer, f"local-os-uid:{os.geteuid()}"
    except (OSError, ValueError, TypeError, KeyError):
        raise LearningContractError("MAINTAINER_NOT_AUTHORIZED") from None


def export_case(path: Path, payload: object) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except (OSError, ValueError):
        raise LearningContractError("CASE_EXPORT_FAILED") from None
