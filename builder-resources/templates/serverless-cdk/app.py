"""Synthesize a named serverless stack using the generated project settings."""

import json
import os
from pathlib import Path

from aws_cdk import App, Tags

from stack import ServerlessStack


def main() -> None:
    """Build the stack without AWS lookups or deployment side effects."""
    config = json.loads((Path(__file__).parent / "project.json").read_text())
    app = App(outdir=os.environ.get("CDK_OUTDIR", "cdk.out"))
    stack = ServerlessStack(app, f'{config["project"]}-{config["stage"]}', config)
    Tags.of(stack).add("Project", config["project"])
    Tags.of(stack).add("Stage", config["stage"])
    app.synth()


if __name__ == "__main__":
    main()
