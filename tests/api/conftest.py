"""Path setup for the Sentinel backend API tests.

Puts the repo root on ``sys.path`` so ``import sentinel_api.main`` (and the ``ml``
namespace package it pulls in) resolves no matter where pytest is invoked from.
Mirrors tests/ml/conftest.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
