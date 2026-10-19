"""Validate fixed C evidence; never run a compiler, Docker, Provider or database."""

import argparse
import json
import subprocess
from pathlib import Path
from offline_c_evidence import check_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    options = parser.parse_args()
    try:
        result = check_report(options.report.absolute())
    except (OSError, ValueError, KeyError, AssertionError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Evidence rejected: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["execution_complete"]:
        parser.exit(1, "Incomplete run is not qualified.\n")


if __name__ == "__main__":
    main()
