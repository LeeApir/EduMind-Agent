"""One opt-in request isolates Review schema transport, not review quality."""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from os import getenv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.agents.review_schema import REVIEW_PROMPT_VERSION, review_output_schema
from app.core.provider_factory import build_default_provider_gateway
from app.services.provider_gateway import ChatMessage, ProviderError, StructuredRequest, TextRequest


async def run():
    if getenv("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT") != "beta_tools":
        raise RuntimeError("EXPLICIT_BETA_SELECTION_REQUIRED")
    report = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "provider_calls": 1,
        "retry": False,
        "schema_conformant": False,
    }
    request = StructuredRequest(
        TextRequest(
            messages=(
                ChatMessage(
                    "user",
                    f"Return review_version={REVIEW_PROMPT_VERSION}, "
                    "verdict=pass, issues=[] as structured data.",
                ),
            ),
            max_output_tokens=512,
        ),
        review_output_schema(),
    )
    try:
        result = await build_default_provider_gateway().generate_structured(
            request, retry_safe=False
        )
        report.update(schema_conformant=True, model=result.model_id)
    except ProviderError as error:
        report["error_code"] = error.code.value
        if error.schema_keyword is not None:
            report["schema_keyword"] = error.schema_keyword
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_billable or args.output.exists():
        parser.error("Requires explicit billing and new evidence path")
    report = asyncio.run(run())
    with args.output.open("x") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
