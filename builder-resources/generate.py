"""Clone the reviewed CDK starter with validated project and environment names."""

import argparse
import json
from pathlib import Path
import shutil

from validation import validate_names


def generate_project(project: str, stage: str, destination: Path) -> Path:
    """Create a new output directory without overwriting an existing project."""
    validate_names(project, stage)
    template = Path(__file__).resolve().parent / "templates" / "serverless-cdk"
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(template, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "cdk.out", ".venv", "node_modules"))
    config = {"project": project, "stage": stage}
    (destination / "project.json").write_text(json.dumps(config, indent=2) + "\n")

    return destination


def main() -> None:
    """Read clone options and report the generated directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    destination = generate_project(args.project, args.stage, args.output)
    print(destination.resolve())


if __name__ == "__main__":
    main()
