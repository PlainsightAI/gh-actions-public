#!/usr/bin/env python3
"""Derive the security-scan Python matrix from a repo's ``requires-python``.

The reusable ``security-scan.yaml`` workflow scans each Python version its consumer
supports. Rather than hardcoding that list per repo (which drifts), we read the repo's
own ``requires-python`` and intersect it with the fleet-supported range
``[floor, ceiling]``.

This module is the canonical, unit-tested implementation (see
``scripts/test_derive_python_matrix.py``). The ``resolve-matrix`` job in
``.github/workflows/security-scan.yaml`` carries an inline copy of ``derive`` because a
reusable workflow runs in the *caller's* checkout, where this file is not present — keep
the two in sync.
"""
import json
import os
import re
import sys

from packaging.specifiers import InvalidSpecifier, SpecifierSet


def read_requires_python(pyproject_path="pyproject.toml"):
    """Return the raw ``requires-python`` string from pyproject.toml, or "" if absent."""
    try:
        with open(pyproject_path) as fh:
            match = re.search(r"""requires-python\s*=\s*["']([^"']+)""", fh.read())
            return match.group(1).strip() if match else ""
    except FileNotFoundError:
        return ""


def derive(requires_python, floor="3.10", ceiling="3.14"):
    """Return the "3.x" versions in [floor, ceiling] admitted by ``requires-python``.

    - An empty/absent ``requires-python`` yields the full ``[floor..ceiling]`` fleet range
      (e.g. a service with no pyproject.toml — it should pass an explicit override instead,
      but the full range is a safe default).
    - Every PEP 440 form is honored via ``packaging`` (>=, >, <, <=, ==, !=, ~=, and
      multi-clause specifiers), so nothing silently falls back to the full range.
    - Raises ``ValueError`` if the specifier admits no version in ``[floor..ceiling]``
      (e.g. ``>=3.16`` when the ceiling is 3.14), so a real floor/ceiling mismatch fails
      loudly instead of collapsing to a wrong single version.
    - Propagates ``packaging.specifiers.InvalidSpecifier`` for a malformed specifier.
    """
    floor_i = int(floor.split(".")[1])
    ceil_i = int(ceiling.split(".")[1])
    candidates = [f"3.{minor}" for minor in range(floor_i, ceil_i + 1)]

    spec_str = (requires_python or "").strip()
    if not spec_str:
        return candidates

    spec = SpecifierSet(spec_str)
    versions = [v for v in candidates if spec.contains(v)]
    if not versions:
        raise ValueError(
            f"requires-python {spec_str!r} admits no Python in "
            f"[{floor}..{ceiling}] — bump python_ceiling or fix requires-python"
        )
    return versions


def main():
    floor = os.environ.get("FLOOR", "3.10")
    ceiling = os.environ.get("CEILING", "3.14")
    try:
        versions = derive(read_requires_python(), floor, ceiling)
    except (ValueError, InvalidSpecifier) as exc:
        print(f"::error::derive-python-matrix: {exc}", file=sys.stderr)
        sys.exit(1)
    print("versions=" + json.dumps(versions))


if __name__ == "__main__":
    main()
