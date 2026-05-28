"""Hatch build hook that adds the shared test fixtures to the sdist."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Copy the repository fixtures into tests/fixtures of the sdist.

    A source checkout keeps the fixtures in the fixtures directory at the
    repository root. An unpacked sdist already has them in tests/fixtures and
    has no such directory above it, so a build from it adds nothing.
    """

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Add the fixtures when tests/fixtures is missing and ../fixtures exists."""
        root = Path(self.root)
        fixtures = root.parent / "fixtures"
        if not (root / "tests" / "fixtures").is_dir() and fixtures.is_dir():
            build_data["force_include"][str(fixtures)] = "tests/fixtures"
