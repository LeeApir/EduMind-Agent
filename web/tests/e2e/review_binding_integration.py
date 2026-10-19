"""T070 real Chromium + explicit route mocks; preserve earlier evidence directories."""
import os
from pathlib import Path

BASE = os.getenv("EDUMIND_TEACHING_UI_URL", "http://127.0.0.1:4194")
os.environ["EDUMIND_TEACHING_UI_URL"] = BASE
os.environ["EDUMIND_HYBRID_UI_URL"] = BASE
import teaching_node_binding as binding  # noqa: E402
import hybrid_review_flow as hybrid  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def main():
    binding.EVIDENCE = ROOT / "local-materials/phase-1-t070/browser/teaching"
    hybrid.EVIDENCE = ROOT / "local-materials/phase-1-t070/browser/hybrid"
    binding.main()
    hybrid.main()
    print("T070 Chromium: teaching choice/exact GET recovery/human wait, no unpublished body; Mock API, Provider0")


if __name__ == "__main__":
    main()
