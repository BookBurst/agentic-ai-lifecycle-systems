from __future__ import annotations

import json

import sys

import time

from dataclasses import dataclass, field

from enum import Enum

from typing import Any, Callable

# ---------------------------------------------------------------------------

# Threshold tiers. Calibrate these as your eval suite matures -- tighten

# HARD_PASS_FLOOR incrementally as your case coverage grows over time.

# ---------------------------------------------------------------------------
