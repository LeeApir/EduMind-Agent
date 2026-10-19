"""Run only admitted fixed C cases inside the approved locked Docker environment."""
import argparse
from pathlib import Path
from offline_c_fixtures import AdmissionError
from offline_c_runner import run_compile_suite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--suite", choices=["compile-output", "ownership", "all"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    try:
        report = run_compile_suite(options.manifest.absolute(), options.output, suite=options.suite)
    except (AdmissionError, OSError, ValueError) as error:
        parser.exit(1, f"Offline checks did not run: {error}\n")
    print(f"Fixed cases:{len(report['cases'])}, compilations:{report['compilations']}, sample processes:{report['sample_processes']}, Provider:0; stopped:{report['stopped']}")
    if report["stopped"]:
        parser.exit(1, "Run stopped; failures and not_run cases retained in report.json\n")


if __name__ == "__main__":
    main()
