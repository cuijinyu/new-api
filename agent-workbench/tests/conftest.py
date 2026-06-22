"""Shared pytest fixtures and path setup."""

from __future__ import annotations

import sys
from pathlib import Path

WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH_ROOT))
