"""Trusted-host maintenance CLI. Does not load .env, Provider keys or model clients."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402
from app.core.database import create_database_engine  # noqa: E402
from app.models.learning_review import LearningReviewRecord  # noqa: E402
from app.models.learning_review_case import LearningReviewCase  # noqa: E402
from app.services.learning_contract import LearningContractError  # noqa: E402
from app.services.learning_review_cases import decide_case  # noqa: E402
from app.services.learning_review_cli import maintainer_identity, export_case  # noqa: E402


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="command", required=True)
    subs.add_parser("list")
    show = subs.add_parser("show")
    show.add_argument("case_id", type=UUID)
    show.add_argument(
        "--body",
        action="store_true",
        help="Show private full content on trusted terminal",
    )
    show.add_argument(
        "--export", type=Path, help="Explicit new private export path (no overwrite)"
    )
    decide = subs.add_parser("decide")
    decide.add_argument("case_id", type=UUID)
    decide.add_argument("--case-digest", required=True)
    decide.add_argument("--verdict", choices=["approve", "reject"], required=True)
    decide.add_argument("--reason", required=True)
    decide.add_argument("--idempotency-key", required=True)
    return p


def summary(case):
    return {
        "case_id": str(case.id),
        "owner_id": str(case.user_id),
        "unit_id": str(case.learning_unit_id),
        "case_digest": case.case_digest,
        "state": case.state,
        "created_at": case.created_at.isoformat(),
    }


async def run(args):
    configured = os.getenv("EDUMIND_REVIEWER_CONFIG")
    if not configured:
        raise LearningContractError("MAINTAINER_NOT_AUTHORIZED")
    reviewer, source = maintainer_identity(Path(configured))
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            if args.command == "list":
                cases = (
                    await db.scalars(
                        select(LearningReviewCase)
                        .where(LearningReviewCase.state == "pending")
                        .order_by(LearningReviewCase.created_at)
                        .limit(100)
                    )
                ).all()
                return {"cases": [summary(c) for c in cases], "limit": 100}
            case = await db.get(LearningReviewCase, args.case_id)
            if case is None:
                raise LearningContractError("REVIEW_CASE_NOT_FOUND")
            if args.command == "show":
                value = summary(case)
                if args.body or args.export:
                    value["payload"] = case.payload
                    ids = case.payload["review_ids"]
                    records = (
                        await db.scalars(
                            select(LearningReviewRecord).where(
                                LearningReviewRecord.id.in_([UUID(v) for v in ids]),
                                LearningReviewRecord.user_id == case.user_id,
                            )
                        )
                    ).all()
                    value["automatic_reviews"] = [r.record for r in records]
                if args.export:
                    export_case(args.export, value)
                    return {**summary(case), "exported": True}
                return value
            decision = await decide_case(
                db,
                owner_id=case.user_id,
                case_id=case.id,
                expected_digest=args.case_digest,
                reviewer_id=reviewer,
                identity_source=source,
                verdict=args.verdict,
                reason=args.reason,
                idempotency_key=args.idempotency_key,
            )
            if decision.verdict == "approve":
                from app.services.hybrid_learning_publication import (
                    publish_approved_case,
                )

                await publish_approved_case(db, owner_id=case.user_id, case_id=case.id)
            await db.commit()
            return {
                "case_id": str(case.id),
                "decision_id": str(decision.id),
                "state": case.state,
            }
    finally:
        await engine.dispose()


def main():
    args = parser().parse_args()
    try:
        result = asyncio.run(run(args))
    except LearningContractError as error:
        print(json.dumps({"code": error.code}))
        return 1
    except Exception:
        print(json.dumps({"code": "REVIEW_CLI_UNAVAILABLE"}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
