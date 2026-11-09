#!/usr/bin/env python3
"""Decide whether a push to a release branch publishes, and check it is safe.

The release workflow runs this on every push to the beta and release branches.
It reads the package version, asks the registry whether that version is
already published and applies the branch rules:

- A version that is already on the registry is never published again. The
  workflow then only runs CI, so merging other work into a release branch is
  harmless.
- The release branch publishes only final versions, such as 1.2.0.
- The beta branch publishes only pre-release versions, such as 1.2.0b1 on PyPI
  or 1.2.0-beta.1 on crates.io.
- The changelog must have a section for the version. For a pre-release the
  section of its final version is accepted, so 1.2.0b1 can use [1.2.0]. A
  final release must have a dated section, not one marked Unreleased.

The release notes, which are the changelog section, are written to the file
given by --notes. The decision is printed and, under GitHub Actions, written to
GITHUB_OUTPUT as publish, prerelease, version and tag.

Run it locally to check a release before pushing:

    python .github/scripts/release_plan.py --registry pypi --branch release
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# PEP 440 public versions without epochs or local labels, which PyPI rejects.
_PEP440 = re.compile(
    r"^(?P<release>\d+(?:\.\d+)*)"
    r"(?P<pre>(?:a|b|rc)\d+)?"
    r"(?P<post>\.post\d+)?"
    r"(?P<dev>\.dev\d+)?$"
)
# Semantic Versioning 2.0.0 without build metadata.
_SEMVER = re.compile(
    r"^(?P<release>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class PlanError(Exception):
    """A release that must not go ahead, with the reason."""


def read_version(registry: str) -> tuple[str, str]:
    """Return the package name and version from the project manifest."""
    if registry == "pypi":
        manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        name = manifest["project"]["name"]
        source = ROOT / manifest["tool"]["hatch"]["version"]["path"]
        match = re.search(
            r'^__version__\s*=\s*["\']([^"\']+)["\']', source.read_text(encoding="utf-8"), re.M
        )
        if match is None:
            raise PlanError(f"no __version__ in {source.relative_to(ROOT)}")
        return name, match.group(1)
    manifest = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    return manifest["package"]["name"], manifest["package"]["version"]


def parse(registry: str, version: str) -> tuple[str, bool]:
    """Return the final version that *version* leads to and whether it is a pre-release."""
    if registry == "pypi":
        match = _PEP440.match(version)
        if match is None:
            raise PlanError(f"{version} is not a version PyPI accepts")
        if match.group("dev"):
            raise PlanError(f"{version} is a development release, which is never published")
        return match.group("release"), bool(match.group("pre"))
    match = _SEMVER.match(version)
    if match is None:
        raise PlanError(f"{version} is not a semantic version")
    return match.group("release"), bool(match.group("pre"))


def is_published(registry: str, name: str, version: str) -> bool:
    """Ask the registry whether *version* of *name* exists."""
    if registry == "pypi":
        url = f"https://pypi.org/pypi/{name}/{version}/json"
    else:
        url = f"https://crates.io/api/v1/crates/{name}/{version}"
    # crates.io rejects requests without a descriptive user agent.
    request = urllib.request.Request(url, headers={"User-Agent": f"{name}-release-plan"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise PlanError(f"{url} answered {exc.code}, so the version could not be checked")
    except urllib.error.URLError as exc:
        raise PlanError(f"{url} could not be reached: {exc.reason}")


def release_notes(version: str, final: str, prerelease: bool) -> str:
    """Return the changelog section for *version*, checking that it is complete."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = list(re.finditer(r"^## \[([^\]]+)\](.*)$", changelog, re.M))
    candidates = [version, final] if prerelease else [version]
    for wanted in candidates:
        for index, heading in enumerate(headings):
            if heading.group(1) != wanted:
                continue
            if not prerelease and "unreleased" in heading.group(2).lower():
                raise PlanError(
                    f"CHANGELOG.md marks {version} as Unreleased. "
                    f"Give the heading a date, for example ## [{version}] - 2026-01-31"
                )
            end = headings[index + 1].start() if index + 1 < len(headings) else len(changelog)
            return changelog[heading.end():end].strip() + "\n"
    raise PlanError(f"CHANGELOG.md has no ## [{candidates[-1]}] section for {version}")


def plan(registry: str, branch: str, enabled: bool, notes: Path | None) -> dict[str, str]:
    """Return the outputs for the workflow, or raise PlanError."""
    name, version = read_version(registry)
    final, prerelease = parse(registry, version)
    tag = f"v{version}"
    outputs = {
        "publish": "false",
        "prerelease": str(prerelease).lower(),
        "version": version,
        "tag": tag,
    }
    if is_published(registry, name, version):
        print(f"{name} {version} is already published, so nothing is published.")
        return outputs
    if branch == "release" and prerelease:
        raise PlanError(
            f"{version} is a pre-release. The release branch publishes final versions, "
            "and the beta branch publishes pre-releases."
        )
    if branch == "beta" and not prerelease:
        raise PlanError(
            f"{version} is a final version. The beta branch publishes pre-releases, "
            "and the release branch publishes final versions."
        )
    if branch not in ("beta", "release"):
        raise PlanError(f"branch {branch} never publishes")
    text = release_notes(version, final, prerelease)
    if registry == "crates" and (ROOT / "Cargo.lock").is_file():
        lock = (ROOT / "Cargo.lock").read_text(encoding="utf-8")
        if f'name = "{name}"\nversion = "{version}"' not in lock:
            raise PlanError(f"Cargo.lock does not record {name} {version}. Run cargo update -p {name}")
    if notes is not None:
        notes.write_text(text, encoding="utf-8")
    if not enabled:
        print(
            f"{name} {version} is ready to publish, but publishing is turned off. "
            "Set the repository variable PUBLISH_ENABLED to true to publish."
        )
        return outputs
    print(f"{name} {version} will be published as {tag} from {branch}.")
    outputs["publish"] = "true"
    return outputs


def main() -> int:
    """Parse the arguments, print the plan and write it to GITHUB_OUTPUT."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", choices=["pypi", "crates"], required=True)
    parser.add_argument("--branch", required=True, help="the branch that was pushed")
    parser.add_argument(
        "--enabled",
        default="true",
        help="publish only when this is true, the value of the PUBLISH_ENABLED variable",
    )
    parser.add_argument("--notes", type=Path, help="file to write the release notes to")
    args = parser.parse_args()
    enabled = args.enabled == "true"
    try:
        outputs = plan(args.registry, args.branch, enabled, args.notes)
    except PlanError as exc:
        # Until publishing is turned on, a release branch that is not ready is
        # reported as a warning so that pushing to it is not a failed run.
        level = "error" if enabled else "warning"
        print(f"::{level}::{exc}" if os.environ.get("GITHUB_ACTIONS") else f"{level}: {exc}")
        if enabled:
            return 1
        outputs = {"publish": "false", "prerelease": "false", "version": "", "tag": ""}
    print(json.dumps(outputs))
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            for key, value in outputs.items():
                fh.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
