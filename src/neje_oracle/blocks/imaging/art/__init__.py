"""Imaging modes added after modes.py passed 1600 lines: one module per mode.

Each module exposes the mode function `<name>(tone: ToneGrid, **params) -> Polylines`, a
`quality_params(spacing_mm) -> dict` hook the quality fader calls, and a one-line `HELP`.
Registration (MODES, MODE_HELP, _mode_params) happens in modes.py and gui/workspaces/image.py.
Every module is held to tests/mode_contract.py.
"""

# modes.py imports these modules at its bottom to register them, and each of them imports
# helpers from modes.py. Loading modes first, here, makes `import ...art.tsp` on its own
# safe: without it that import starts tsp, which starts modes, which asks for a half-built tsp.
from .. import modes  # noqa: E402, F401
