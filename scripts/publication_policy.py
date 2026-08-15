#!/usr/bin/env python3
"""Portable entry point for canonical publication policy validation."""

from __future__ import annotations

import runpy
from pathlib import Path


TARGET = (
    Path(__file__).resolve().parents[1]
    / "skills/loop-debate-agentes/scripts/publication_policy.py"
)


if __name__ == "__main__":
    runpy.run_path(str(TARGET), run_name="__main__")
