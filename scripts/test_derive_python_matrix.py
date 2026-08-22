#!/usr/bin/env python3
"""Fixtures for scripts/derive_python_matrix.py — run with `python3 this_file.py`.

Covers the PEP 440 specifier forms present in the fleet plus the failure modes the
derivation must NOT paper over (floor above ceiling, versions outside the range, garbage).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from packaging.specifiers import InvalidSpecifier  # noqa: E402

from derive_python_matrix import derive  # noqa: E402

# (requires-python, expected matrix) with the default floor=3.10, ceiling=3.14.
OK_CASES = [
    (">=3.10, <3.15", ["3.10", "3.11", "3.12", "3.13", "3.14"]),
    (">=3.11, <3.15", ["3.11", "3.12", "3.13", "3.14"]),
    (">=3.10, <3.13", ["3.10", "3.11", "3.12"]),          # dep-blocked: never 3.14
    (">=3.11, <3.12", ["3.11"]),                            # single version
    (">=3.11", ["3.11", "3.12", "3.13", "3.14"]),          # no ceiling -> clamp to fleet
    (">=3.8", ["3.10", "3.11", "3.12", "3.13", "3.14"]),   # old floor -> clamp up to 3.10
    ("", ["3.10", "3.11", "3.12", "3.13", "3.14"]),        # absent -> full fleet range
    ("~=3.11", ["3.11", "3.12", "3.13", "3.14"]),          # compatible-release
    (">3.10", ["3.11", "3.12", "3.13", "3.14"]),           # bare '>' excludes 3.10
    ("==3.12", ["3.12"]),                                    # exact
    (">=3.10, !=3.12, <3.15", ["3.10", "3.11", "3.13", "3.14"]),  # exclusion
]

# Specifiers that must fail loudly rather than narrow to a wrong matrix.
ERROR_CASES = [
    ">=3.16",            # floor above ceiling -> empty
    "<3.9",              # ceiling below floor -> empty
    "==3.15",            # outside the fleet range -> empty
    "not-a-specifier",   # malformed -> InvalidSpecifier
]

failures = 0

for requires_python, expected in OK_CASES:
    got = derive(requires_python)
    if got != expected:
        failures += 1
        print(f"FAIL: derive({requires_python!r}) = {got} != {expected}")
    else:
        print(f"ok:   {requires_python or '(absent)':24} -> {got}")

for requires_python in ERROR_CASES:
    try:
        got = derive(requires_python)
        failures += 1
        print(f"FAIL: derive({requires_python!r}) should have raised, returned {got}")
    except (ValueError, InvalidSpecifier):
        print(f"ok:   {requires_python!r:24} -> raised as expected")

# A non-default ceiling is honored (e.g. once 3.15 ships, bumping ceiling adds it).
got = derive(">=3.11, <3.16", floor="3.10", ceiling="3.15")
if got != ["3.11", "3.12", "3.13", "3.14", "3.15"]:
    failures += 1
    print(f"FAIL: custom ceiling -> {got}")
else:
    print(f"ok:   custom ceiling 3.15 -> {got}")

if failures:
    print(f"\n{failures} failure(s)")
    sys.exit(1)
print("\nall derivation fixtures passed")
