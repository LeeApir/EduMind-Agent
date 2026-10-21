"""Check frozen fixture admission without compiling or running C."""
import argparse
import json
from offline_c_fixtures import AdmissionError, check_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    try:
        print(json.dumps(check_manifest(), ensure_ascii=False, indent=2))
    except (AdmissionError, OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Fixture admission failed: {error}\n")


if __name__ == "__main__":
    main()
