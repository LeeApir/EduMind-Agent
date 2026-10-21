"""Trusted local plan evidence inspection/notes; no model, approval, resume or publication."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, cast
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402
from app.core.database import create_database_engine  # noqa: E402
from app.models.learning_plan import LearningPlanVersion  # noqa: E402
from app.models.plan_check import PlanCheck, PlanCheckResolution, PlanRebuildEvent  # noqa: E402
from app.services.learning_contract import LearningContractError  # noqa: E402
from app.services.learning_review_cli import export_case, maintainer_identity  # noqa: E402
from app.services.plan_check import (
    owned_plan_check,
    save_plan_resolution,
    verify_snapshots,
    record_digest,
)  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("check_id", type=UUID)
    show.add_argument("--body", action="store_true")
    show.add_argument("--export", type=Path)
    note = commands.add_parser("note")
    note.add_argument("check_id", type=UUID)
    note.add_argument("--check-digest", required=True)
    note.add_argument(
        "--kind",
        choices=[
            "clarification_needed",
            "new_request_needed",
            "false_positive_confirmed",
            "rejected",
        ],
        required=True,
    )
    note.add_argument("--reason", required=True)
    note.add_argument("--idempotency-key", required=True)
    return p


def summary(row: PlanCheck) -> dict[str, Any]:
    return dict(
        check_id=str(row.id),
        owner_id=str(row.user_id),
        operation_id=str(row.operation_id),
        plan_id=str(row.plan_id),
        check_digest=row.record_digest,
        stage=row.stage,
        route=cast(dict[str, Any], row.record["server_assessment"])["route"],
        created_at=row.created_at.isoformat(),
    )


async def run(args: argparse.Namespace) -> dict[str, Any]:
    config = os.getenv("EDUMIND_REVIEWER_CONFIG")
    if not config:
        raise LearningContractError("MAINTAINER_NOT_AUTHORIZED")
    reviewer, source = maintainer_identity(Path(config))
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            if args.command == "list":
                # Trusted host maintainer only. Summary exposes no request/plan body.
                rows = (
                    await db.scalars(
                        select(PlanCheck)
                        .order_by(PlanCheck.created_at, PlanCheck.id)
                        .limit(100)
                    )
                ).all()
                return dict(checks=[summary(row) for row in rows], limit=100)
            row = await db.get(PlanCheck, args.check_id)
            if row is None:
                raise LearningContractError("PLAN_CHECK_NOT_FOUND")
            row = await owned_plan_check(db, owner_id=row.user_id, check_id=row.id)
            if args.command == "show":
                value = summary(row)
                if args.body or args.export:
                    value["record"] = row.record
                    plan = await db.get(LearningPlanVersion, row.plan_id)
                    if (
                        plan is None
                        or plan.user_id != row.user_id
                        or plan.learning_unit_id != row.learning_unit_id
                    ):
                        raise LearningContractError("PLAN_CHECK_BINDING_INVALID")
                    verify_snapshots(plan)
                    value["source_snapshots"] = dict(
                        plan=plan.plan_json,
                        input=plan.input_snapshot,
                        references=plan.references_snapshot,
                        policy=plan.policy_snapshot,
                    )
                    notes = (
                        await db.scalars(
                            select(PlanCheckResolution)
                            .where(PlanCheckResolution.check_id == row.id)
                            .order_by(
                                PlanCheckResolution.created_at, PlanCheckResolution.id
                            )
                        )
                    ).all()
                    if any(
                        note.record_digest != record_digest(note.record, "resolution")
                        for note in notes
                    ):
                        raise LearningContractError("PLAN_NOTE_CHANGED")
                    events = (
                        await db.scalars(
                            select(PlanRebuildEvent)
                            .where(
                                PlanRebuildEvent.user_id == row.user_id,
                                PlanRebuildEvent.operation_id == row.operation_id,
                            )
                            .order_by(PlanRebuildEvent.created_at, PlanRebuildEvent.id)
                        )
                    ).all()
                    if any(
                        e.record_digest != record_digest(e.record, "rebuild_event")
                        for e in events
                    ):
                        raise LearningContractError("PLAN_REBUILD_EVIDENCE_CHANGED")
                    value["rebuild_events"] = [e.record for e in events]
                    value["notes"] = [note.record for note in notes]
                if args.export:
                    export_case(args.export, value)
                    return dict(**summary(row), exported=True)
                return value
            value = dict(
                schema_version="plan-issue-resolution-v1",
                resolution_id=str(uuid4()),
                check_id=str(row.id),
                expected_check_digest=args.check_digest,
                reviewer_id=reviewer,
                identity_source=source,
                kind=args.kind,
                reason=args.reason,
                idempotency_key=args.idempotency_key,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            result = await save_plan_resolution(
                db,
                owner_id=row.user_id,
                value=value,
                trusted_reviewer_id=reviewer,
                trusted_identity_source=source,
            )
            await db.commit()
            return dict(
                check_id=str(row.id),
                resolution_id=str(result.id),
                effect="audit_note_only",
            )
    finally:
        await engine.dispose()


def main() -> int:
    try:
        value = asyncio.run(run(parser().parse_args()))
    except LearningContractError as error:
        print(json.dumps(dict(code=error.code)))
        return 1
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
