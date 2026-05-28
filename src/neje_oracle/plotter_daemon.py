"""Compatibility alias for the plotter daemon block."""

from __future__ import annotations

import sys

from .blocks.plotter import daemon as _daemon

sys.modules[__name__] = _daemon
