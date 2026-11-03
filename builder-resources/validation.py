"""Validate naming once before the generator creates files."""

import re


def validate_names(project: str, stage: str) -> None:
    """Require portable names and bounded Lambda/stack name lengths."""
    for name, value, limit in (("project", project, 32), ("stage", stage, 12)):
        if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value) or len(value) > limit:
            raise ValueError(f"{name} must start with a lowercase letter, use lowercase letters/digits/single hyphens, and be at most {limit} characters")
