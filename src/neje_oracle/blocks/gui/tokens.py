"""The operator theme: a neutral control panel, not the Oracle brand.

The cream/serif Oracle identity stays with the public work -- the Flutter gallery, the
website, the receipt. The operator GUI is a machine control panel read under time
pressure, and it now says so: neutral grey grounds (ISA-101's rationale: a quiet ground
so that status colors are the loudest thing on screen), one reserved interactive blue,
and a status triad that no accent reuses. The old tokens↔Flutter parity test is replaced
by self-consistency checks in tests/test_gui_design_system.py: every pair below is
asserted WCAG AA at the size it is used, computed from these values.

Everything here is a name. If a hex literal appears anywhere else under blocks/gui, the
ratchet will say so.
"""

from __future__ import annotations

# --- colour ---------------------------------------------------------------------
BG = "#ECEEF0"  # page ground
SURFACE = "#F7F8FA"  # raised surfaces: cards, panels, the bar
SUNKEN = "#E2E4E8"  # recessed wells: previews, logs
TEXT = "#1C1E21"  # primary text
TEXT_MID = "#44484D"  # secondary text, helper prose
TEXT_MUTED = "#5C6167"  # captions, disabled
BORDER = "#C9CDD2"  # every border and divider
ACCENT = "#2F5A8F"  # interactive: primary actions, active tab, links, focus

# Status colours are semantic, not decorative: an operator reads these under time
# pressure, so no accent reuses them and none reuses the accent. Three states, three
# hues -- green/amber/red -- each AA on SURFACE at caption size.
OK = "#1E6B3C"
WARN = "#8A5A00"
DANGER = "#A0221A"
# A tinted ground for the warning chip and banner; WARN stays AA on it.
WARN_WASH = "#FDF3D9"

# --- type -----------------------------------------------------------------------
# System stacks only: the gallery MacBook must render identically offline, and webfonts
# were declared for two years without a single CSS rule applying them.
FONT_UI = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_MONO = "ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace"

TYPE_XS = "10px"  # micro labels, metric captions -- the floor, nothing below it
TYPE_SM = "12px"  # helper text, chips, readouts
TYPE_MD = "13px"  # section titles
TYPE_LG = "14px"  # tabs, buttons, body

# --- motion ---------------------------------------------------------------------
# Two durations and one curve, and they are actually referenced by styles.py -- the
# brand's five ritual tempos were declared and never used by any rule.
DUR_FAST = "120ms"  # hover, press
DUR_MED = "200ms"  # state-chip colour changes
EASE_STANDARD = "cubic-bezier(0.2, 0, 0, 1)"

# --- space and shape ------------------------------------------------------------
# Operator density is tight on purpose: the app is a control panel.
SPACE_XS = "4px"
SPACE_SM = "6px"
SPACE_MD = "10px"
SPACE_LG = "16px"
RADIUS_SM = "6px"
RADIUS_MD = "10px"
RADIUS_PILL = "999px"

CSS_VARIABLES: dict[str, str] = {
    "--bg": BG,
    "--surface": SURFACE,
    "--sunken": SUNKEN,
    "--text": TEXT,
    "--text-mid": TEXT_MID,
    "--text-muted": TEXT_MUTED,
    "--border": BORDER,
    "--accent": ACCENT,
    "--ok": OK,
    "--warn": WARN,
    "--danger": DANGER,
    "--warn-wash": WARN_WASH,
    "--font-ui": FONT_UI,
    "--font-mono": FONT_MONO,
    "--type-xs": TYPE_XS,
    "--type-sm": TYPE_SM,
    "--type-md": TYPE_MD,
    "--type-lg": TYPE_LG,
    "--dur-fast": DUR_FAST,
    "--dur-med": DUR_MED,
    "--ease-standard": EASE_STANDARD,
    "--space-xs": SPACE_XS,
    "--space-sm": SPACE_SM,
    "--space-md": SPACE_MD,
    "--space-lg": SPACE_LG,
    "--radius-sm": RADIUS_SM,
    "--radius-md": RADIUS_MD,
    "--radius-pill": RADIUS_PILL,
}


def css_root_block() -> str:
    """`:root { ... }` for injection into PAGE_STYLE, so CSS can use var(--accent)."""
    body = "\n".join(f"  {name}: {value};" for name, value in CSS_VARIABLES.items())
    return f":root {{\n{body}\n}}"
