"""Synthetic-only ADR-0013 replay. No Provider, credentials, HTTP or production registration."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "claim-review-offline-v1"
MAX_CLAIMS = 16
MAX_BLOCKS = 48
MAX_BYTES = 48 * 1024
MAX_CALLS = 3 * (MAX_CLAIMS + 3) + 2


class Invalid(ValueError):
    pass


def encoded(value):
    def check(item, depth=0):
        if depth > 128:
            raise Invalid("INVALID_JSON")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise Invalid("INVALID_JSON")
            for child in item.values():
                check(child, depth + 1)
        elif type(item) is list:
            for child in item:
                check(child, depth + 1)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise Invalid("INVALID_JSON")

    check(value)
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise Invalid("INVALID_JSON") from exc


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def obj(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        raise Invalid("INVALID_SCHEMA")
    return value


def seq(value):
    if type(value) is not list:
        raise Invalid("INVALID_SCHEMA")
    return value


def text(value):
    if type(value) is not str or not value.strip():
        raise Invalid("INVALID_TEXT")
    return value


def issue(value):
    obj(value, "area severity message")
    if value["area"] not in ("fact", "code_safety", "difficulty", "misconception"):
        raise Invalid("INVALID_AREA")
    if value["severity"] not in ("minor", "major", "severe"):
        raise Invalid("INVALID_SEVERITY")
    text(value["message"])
    return json.loads(encoded(value))


@dataclass(frozen=True)
class Snapshot:
    serialized: bytes
    candidate_sha256: str
    context_sha256: str
    config_sha256: str

    @property
    def data(self):
        return json.loads(self.serialized)

    @property
    def identity(self):
        return {
            k: getattr(self, k) for k in ("candidate_sha256", "context_sha256", "config_sha256")
        }

    @property
    def blocks(self):
        result = []

        def walk(value, path, depth=0):
            if depth > 16:
                raise Invalid("TOO_DEEP")
            if type(value) is dict:
                for key in sorted(value):
                    if type(key) is not str:
                        raise Invalid("INVALID_KEY")
                    walk(
                        value[key],
                        path + "/" + key.replace("~", "~0").replace("/", "~1"),
                        depth + 1,
                    )
            elif type(value) is list:
                for i, item in enumerate(value):
                    walk(item, path + f"/{i}", depth + 1)
            else:
                raw = value if type(value) is str else encoded(value).decode()
                result.append(
                    {
                        "block_id": digest(
                            ["resource-field-blocks-v1", self.candidate_sha256, path]
                        ),
                        "path": path,
                        "text": raw,
                    }
                )
                if len(result) > MAX_BLOCKS:
                    raise Invalid("TOO_MANY_BLOCKS")

        walk(self.data["content"], "/content")
        return result


def freeze(resource_type, content, context=None, config=None):
    if resource_type not in ("explanation", "code", "exercise") or type(content) is not dict:
        raise Invalid("INVALID_RESOURCE")
    value = {"resource_type": resource_type, "content": content, "reference_context": context}
    wire = encoded(value)
    if len(wire) > MAX_BYTES:
        raise Invalid("INPUT_TOO_LARGE")
    snap = Snapshot(
        wire,
        digest({"resource_type": resource_type, "content": content}),
        digest(context),
        digest(config),
    )
    snap.blocks
    return snap


def anchor(snap, value):
    obj(value, "block_id start end quote")
    blocks = {b["block_id"]: b for b in snap.blocks}
    if type(value["block_id"]) is not str or value["block_id"] not in blocks:
        raise Invalid("UNKNOWN_BLOCK")
    start, end = value["start"], value["end"]
    raw = blocks[value["block_id"]]["text"]
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(raw)
        or type(value["quote"]) is not str
        or raw[start:end] != value["quote"]
    ):
        raise Invalid("INVALID_ANCHOR")
    return json.loads(encoded(value))


def claim(snap, value):
    obj(value, "text anchors related_anchors")
    description = text(value["text"])
    anchors = [anchor(snap, a) for a in seq(value["anchors"])]
    related = [anchor(snap, a) for a in seq(value["related_anchors"])]
    if not anchors or len(anchors) > MAX_BLOCKS or len(related) > MAX_BLOCKS:
        raise Invalid("INVALID_ANCHOR_COUNT")
    anchors.sort(key=encoded)
    if len({encoded(a) for a in anchors}) != len(anchors):
        raise Invalid("DUPLICATE_ANCHOR")
    return {
        "claim_id": digest([snap.candidate_sha256, anchors, description]),
        "text": description,
        "anchors": anchors,
        "related_anchors": related,
    }


def inventory(snap, raw, coverage):
    obj(raw, "version claims exclusions")
    obj(coverage, "version missing_claims uncertainties invalid_exclusions")
    if raw["version"] != "claim-inventory-v1" or coverage["version"] != "claim-coverage-v1":
        raise Invalid("INVALID_VERSION")
    if seq(coverage["uncertainties"]) or seq(coverage["invalid_exclusions"]):
        raise Invalid("COVERAGE_UNRESOLVED")
    initial = [claim(snap, c) for c in seq(raw["claims"])]
    added = [claim(snap, c) for c in seq(coverage["missing_claims"])]
    claims = initial + added
    if len(claims) > MAX_CLAIMS:
        raise Invalid("TOO_MANY_CLAIMS")
    if len({c["claim_id"] for c in claims}) != len(claims):
        raise Invalid("DUPLICATE_CLAIM")
    block_ids = {b["block_id"] for b in snap.blocks}
    covered = {a["block_id"] for c in initial for a in c["anchors"]}
    excluded = set()
    exclusions = seq(raw["exclusions"])
    for e in exclusions:
        obj(e, "block_id reason")
        bid = text(e["block_id"])
        text(e["reason"])
        if bid not in block_ids or bid in excluded or bid in covered:
            raise Invalid("INVALID_EXCLUSION")
        excluded.add(bid)
    if covered | excluded != block_ids:
        raise Invalid("UNMAPPED_BLOCK")
    added_blocks = {a["block_id"] for c in added for a in c["anchors"]}
    return {
        "version": "claim-inventory-frozen-v1",
        "claims": claims,
        "exclusions": [e for e in exclusions if e["block_id"] not in added_blocks],
    }


def binding(snap, inv, claim_id):
    return {**snap.identity, "inventory_sha256": digest(inv), "claim_id": claim_id}


def checked_review(snap, inv, value, claim_id, overall=False):
    keys = "version identity verdict findings incidental_findings"
    obj(value, keys + (" uncovered uncertain" if overall else ""))
    expected_version = "claim-overall-v1" if overall else "claim-review-v1"
    if value["version"] != expected_version or value["identity"] != binding(snap, inv, claim_id):
        raise Invalid("STALE_OR_WRONG_BINDING")
    findings = [issue(i) for i in seq(value["findings"])]
    verdict = value["verdict"]
    if verdict not in ("pass", "revise", "reject") or ((verdict == "pass") != (not findings)):
        raise Invalid("INVALID_VERDICT")
    if overall:
        if type(value["uncovered"]) is not bool or type(value["uncertain"]) is not bool:
            raise Invalid("INVALID_SCHEMA")
    incidental = []
    ids = {c["claim_id"]: c for c in inv["claims"]}
    for other in seq(value["incidental_findings"]):
        obj(other, "claim_id anchors finding")
        aid = other["claim_id"]
        aa = [anchor(snap, a) for a in seq(other["anchors"])]
        finding = issue(other["finding"])
        if type(aid) is not str or not aid.strip() or not aa:
            raise Invalid("INVALID_INCIDENTAL")
        if aid == claim_id or (aid in ids and any(a not in ids[aid]["anchors"] for a in aa)):
            raise Invalid("INCIDENTAL_ANCHOR_MISMATCH")
        incidental.append({"claim_id": aid, "anchors": aa, "finding": finding})
    return verdict, findings, incidental


@dataclass
class Result:
    status: str
    issues: list = field(default_factory=list)
    provenance: list = field(default_factory=list)
    error: str | None = None
    synthetic_only: bool = True

    @property
    def approved(self):
        return self.status == "pass"


class Replay:
    """Canned JSON tape only. It cannot accept a transport, key, URL or model callback."""

    def __init__(
        self,
        tape,
        ledger: Path,
        *,
        max_calls=MAX_CALLS,
        deadline_seconds=30,
        input_token_cap=65536,
        output_token_cap=8192,
    ):
        self.tape = json.loads(encoded(tape))
        if type(self.tape) is not dict:
            raise Invalid("INVALID_TAPE")
        if type(max_calls) is not int or not 1 <= max_calls <= MAX_CALLS:
            raise Invalid("INVALID_CALL_LIMIT")
        if (
            type(deadline_seconds) not in (int, float)
            or not math.isfinite(deadline_seconds)
            or deadline_seconds <= 0
        ):
            raise Invalid("INVALID_DEADLINE")
        for cap in (input_token_cap, output_token_cap):
            if type(cap) is not int or cap <= 0:
                raise Invalid("INVALID_TOKEN_CAP")
        self.token_caps = {"input_tokens": input_token_cap, "output_tokens": output_token_cap}
        self.halted = False
        self.rounds = set()
        self.max_calls = max_calls
        self.deadline = time.monotonic() + deadline_seconds
        self.requests = []
        self.parent = digest([VERSION, "synthetic-only"])
        self.db = sqlite3.connect(ledger)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS offline_run (id INTEGER PRIMARY KEY, version TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS offline_calls (slot TEXT PRIMARY KEY, "
            "request_hash TEXT, parent_hash TEXT, response_hash TEXT)"
        )
        # A crash/restart never starts a second run on the same ledger.
        try:
            self.db.execute("INSERT INTO offline_run VALUES(1, ?)", (VERSION,))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            self.db.close()
            raise Invalid("OFFLINE_REPLAY_FORBIDDEN") from exc

    def close(self):
        self.db.close()

    def take(self, slot, snap, payload):
        if self.halted:
            raise Invalid("OFFLINE_RUN_HALTED")
        if time.monotonic() >= self.deadline:
            raise Invalid("DEADLINE")
        if self.db.execute("SELECT COUNT(*) FROM offline_calls").fetchone()[0] >= self.max_calls:
            raise Invalid("CALL_LIMIT")
        request = {
            "synthetic_only": True,
            "slot": slot,
            "identity": snap.identity,
            "candidate": snap.data,
            "payload": payload,
        }
        request_hash = digest(request)
        self.db.execute(
            "INSERT INTO offline_calls VALUES(?,?,?,NULL)", (slot, request_hash, self.parent)
        )
        self.db.commit()
        self.requests.append(request)
        envelope = self.tape.get(slot)
        obj(envelope, "synthetic_only status input_tokens output_tokens value")
        if envelope["synthetic_only"] is not True or envelope["status"] != "completed":
            raise Invalid("SYNTHETIC_COMPLETION_REQUIRED")
        for name in ("input_tokens", "output_tokens"):
            if type(envelope[name]) is not int or envelope[name] < 0:
                raise Invalid("UNKNOWN_USAGE")
            if envelope[name] > self.token_caps[name]:
                raise Invalid("USAGE_EXCEEDED")
        response_hash = digest(envelope)
        self.db.execute(
            "UPDATE offline_calls SET response_hash=? WHERE slot=?", (response_hash, slot)
        )
        self.db.commit()
        self.parent = response_hash
        if time.monotonic() >= self.deadline:
            raise Invalid("DEADLINE")
        return envelope["value"]

    def run_round(self, snap, round_index):
        issues, provenance = [], []

        def keep(found, source, origin, anchors=None):
            for finding in found:
                # Dedup only byte-identical finding AND location; retain every origin.
                key = digest([source, anchors, finding])
                if key not in {p["key"] for p in provenance}:
                    issues.append(finding)
                provenance.append(
                    {
                        "key": key,
                        "source": source,
                        "origin": origin,
                        "anchors": anchors,
                        "finding": finding,
                    }
                )

        prefix = str(round_index)
        try:
            if (
                round_index in self.rounds
                or type(round_index) is not int
                or not 0 <= round_index <= 2
            ):
                raise Invalid("ROUND_REPLAY")
            self.rounds.add(round_index)
            raw = self.take(prefix + ".inventory", snap, {})
            inventory(
                snap,
                raw,
                {
                    "version": "claim-coverage-v1",
                    "missing_claims": [],
                    "uncertainties": [],
                    "invalid_exclusions": [],
                },
            )
            coverage = self.take(prefix + ".coverage", snap, {"inventory": raw})
            inv = inventory(snap, raw, coverage)
            verdicts, incidental = {}, []
            for c in inv["claims"]:
                cid = c["claim_id"]
                value = self.take(prefix + ".claim." + cid, snap, {"inventory": inv, "focus": c})
                verdict, found, extra = checked_review(snap, inv, value, cid)
                verdicts[cid] = verdict
                keep(found, cid, prefix + ".claim." + cid, c["anchors"])
                incidental.extend(extra)
                for other in extra:
                    keep(
                        [other["finding"]],
                        other["claim_id"],
                        prefix + ".claim." + cid,
                        other["anchors"],
                    )
                if any(e["claim_id"] not in {c["claim_id"] for c in inv["claims"]} for e in extra):
                    raise Invalid("UNCOVERED_INCIDENTAL")
            value = self.take(prefix + ".overall", snap, {"inventory": inv})
            overall, found, extra = checked_review(snap, inv, value, "__overall__", True)
            keep(found, "__overall__", prefix + ".overall")
            incidental.extend(extra)
            for other in extra:
                keep([other["finding"]], other["claim_id"], prefix + ".overall", other["anchors"])
            if any(e["claim_id"] not in verdicts for e in incidental):
                raise Invalid("UNCOVERED_INCIDENTAL")
            if value["uncovered"] or value["uncertain"]:
                raise Invalid("OVERALL_INCOMPLETE")
            if any(verdicts[e["claim_id"]] == "pass" for e in incidental):
                raise Invalid("CONFLICTING_VERDICTS")
            if issues:
                status = "reject" if "reject" in [overall, *verdicts.values()] else "revise"
            else:
                status = "pass"
            return Result(status, issues, provenance)
        except (Invalid, sqlite3.IntegrityError) as exc:
            self.halted = True
            return Result("unavailable", issues, provenance, str(exc))

    def run(self, snap):
        """At most two canned corrections. Every changed candidate restarts inventory."""
        for round_index in range(3):
            result = self.run_round(snap, round_index)
            if result.status != "revise":
                return result
            if round_index == 2:
                return Result("reject", result.issues, result.provenance, "CORRECTION_LIMIT")
            try:
                corrected = self.take(
                    str(round_index) + ".correction", snap, {"issues": result.issues}
                )
                obj(corrected, "resource_type content")
                if corrected["resource_type"] != snap.data["resource_type"]:
                    raise Invalid("CORRECTION_RESOURCE_CHANGED")
                new_snap = freeze(
                    corrected["resource_type"], corrected["content"], snap.data["reference_context"]
                )
                # Freeze the same configuration even when its JSON value is not retained.
                snap = Snapshot(
                    new_snap.serialized,
                    new_snap.candidate_sha256,
                    new_snap.context_sha256,
                    snap.config_sha256,
                )
            except Invalid as exc:
                self.halted = True
                return Result("unavailable", result.issues, result.provenance, str(exc))
        raise AssertionError("unreachable")
