"""Expose shared agent modules from the project's hyphenated source directory."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "builder-agents"))
