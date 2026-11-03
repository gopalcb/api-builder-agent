"""Test portable names and non-overwriting project generation."""

from pathlib import Path
import tempfile
import unittest
import json

from generate import generate_project


class GeneratorTests(unittest.TestCase):
    """Exercise generation in isolated temporary folders."""

    def test_named_clone_and_no_overwrite(self) -> None:
        """Clone two distinct project configurations and reject existing outputs."""
        with tempfile.TemporaryDirectory() as directory:
            for name in ("orders-api", "inventory-api"):
                target = generate_project(name, "test", Path(directory) / name)
                self.assertEqual(json.loads((target / "project.json").read_text())["project"], name)
                self.assertTrue((target / "lambda/handler.py").is_file())

                with self.assertRaises(FileExistsError):
                    generate_project(name, "prod", target)

    def test_invalid_names_leave_no_files(self) -> None:
        """Reject traversal, shell text, oversized names and invalid stages."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"

            for name, stage in (("../escape", "dev"), ("$(id)", "dev"), ("A", "dev"), ("a" * 33, "dev"), ("api", "bad_stage")):
                with self.assertRaises(ValueError):
                    generate_project(name, stage, target)

                self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
