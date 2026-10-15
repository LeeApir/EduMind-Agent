"""One independent whole-unit consistency review; no global regeneration loop."""

from typing import Any

from app.agents.hybrid_resource_review import review_once
from app.agents.learning_unit_generator import StructuredResourceGateway
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import LearningContractError, canonical, validate_contract
from app.services.unit_material import restore_material


def resource_review_priority(material: dict[str, Any], records: list[dict[str, Any]]) -> str:
    if len(records) != 3:
        raise LearningContractError("RESOURCE_REVIEWS_INCOMPLETE")
    states = []
    for candidate, record in zip(material["candidates"], records, strict=True):
        validate_contract(record, "review_record")
        if (
            canonical(record["binding"]) != canonical(material["binding"])
            or record["target_digest"] != candidate["content_digest"]
            or record["result"]["scope"] != "resource"
            or any(a["resource_id"] != candidate["resource_id"] for a in record["anchor_catalog"])
        ):
            raise LearningContractError("RESOURCE_REVIEW_STALE")
        states.append(record["local_routing"]["verdict"])
    if "failed" in states:
        raise LearningContractError("RESOURCE_REVIEW_FAILED")
    if "reject" in states:
        return "rejected"
    if "revise" in states:
        raise LearningContractError("RESOURCE_REVIEW_UNFINISHED")
    return "needs_human" if "needs_human" in states else "auto_ready"


async def review_unit(
    gateway: StructuredResourceGateway,
    window: CallWindow,
    material: dict[str, Any],
    resource_records: list[dict[str, Any]],
) -> dict[str, Any]:
    workspace, checked = restore_material(material)
    prior = resource_review_priority(checked, resource_records)
    if prior == "rejected":
        return {"state": "rejected", "review": None}
    record = await review_once(
        gateway,
        window,
        binding=workspace.binding,
        target_digest=checked["unit_digest"],
        payload={"unit": checked, "reference_context": workspace.reference_context},
        candidates=workspace.candidates(),
        scope="unit",
    )
    verdict = record["local_routing"]["verdict"]
    state = (
        "rejected"
        if verdict == "reject"
        else "needs_human"
        if verdict == "needs_human" or prior == "needs_human"
        else "auto_ready"
    )
    return {"state": state, "review": record}
