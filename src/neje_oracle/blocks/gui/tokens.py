"""The Oracle design system, for the operator GUI.

Ported verbatim from `public_gallery/lib/theme/oracle_theme.dart`, which is the faithful
implementation of `assets/Design system/oracle_design_system.html`. Those two already agree
1:1; the operator GUI was the outlier, carrying a fourth palette that was *near* the system
but never equal -- cream #f7f1e7 vs #F7F4EF, rust #8f4f2b (27 uses) vs #8B4513, and four
different border colors where the system has one `rule`.

Adopting these makes the operator app the third faithful consumer instead of the odd one
out. The visual shift is small but real: rust and cream move by a few points.

Everything here is a name. If a hex literal appears anywhere else under blocks/gui, the
ratchet in tests/test_gui_design_system.py will say so.
"""

from __future__ import annotations

# --- colour ---------------------------------------------------------------------
# The 10 system colours. Names match oracle_theme.dart so the two can be diffed by eye.
CREAM = "#F7F4EF"  # page ground
PAPER = "#FBF8F1"  # raised surfaces: cards, panels
INK = "#1A1A1A"  # primary text
INK_MID = "#3A3A3A"  # secondary text
INK_MUTED = "#6A6A6A"  # captions, disabled
RUST = "#8B4513"  # the accent: helper text, links, focus
RUST_LIGHT = "#C4752A"  # hover / lighter accent
GOLD = "#C9A84C"  # highlight, in-progress
GOLD_DIM = "#8A6F2E"  # gold on light ground, where GOLD fails contrast
RULE = "#CCC5B8"  # every border and divider
VOID = "#0A0A12"  # the installation register, not used in the operator tool

# Status colours are semantic, not decorative: an operator reads these under time
# pressure, so they stay distinct from the brand accents rather than reusing RUST.
# The prior audit raised DS-COL-1 -- gold meant both STOP and HOME ALL, so one colour
# carried two opposite meanings. Three states, three colours, no overlap with the accent.
OK = "#4A6741"  # moss; desaturated to sit on cream without shouting
WARN = GOLD_DIM  # gold reads as caution here and only here
DANGER = "#8C2F1D"  # deeper and redder than RUST, so it cannot be mistaken for the accent
# A tinted ground for the warning banner and the "next action" highlight. The system
# has no wash colour; these two places need one to lift off CREAM at a glance.
WARN_WASH = "#FFF4DF"

# --- type -----------------------------------------------------------------------
FONT_BODY = "'EB Garamond', 'Times New Roman', Georgia, serif"
FONT_DISPLAY = "'Cinzel', serif"
FONT_LOGO = "'Cinzel Decorative', serif"

# --- motion ---------------------------------------------------------------------
DUR_INSTANT = "0ms"
DUR_FAST = "200ms"
DUR_MEDIUM = "600ms"
DUR_SLOW = "1800ms"
DUR_RITUAL = "4000ms"

EASE_ORACLE = "cubic-bezier(0.4, 0, 0.2, 1)"
EASE_IN_BREATH = "cubic-bezier(0.4, 0, 1, 1)"
EASE_OUT_BREATH = "cubic-bezier(0, 0, 0.2, 1)"

# --- space and shape ------------------------------------------------------------
# A scale, replacing the ad-hoc 5/6/7/8/10/12px paddings and 10/14/999px radii in the
# old PAGE_STYLE. Operator density is tight on purpose: the app is a control panel.
SPACE_XS = "4px"
SPACE_SM = "6px"
SPACE_MD = "10px"
SPACE_LG = "16px"
RADIUS_SM = "6px"
RADIUS_MD = "10px"
RADIUS_PILL = "999px"

CSS_VARIABLES: dict[str, str] = {
    "--cream": CREAM,
    "--paper": PAPER,
    "--ink": INK,
    "--ink-mid": INK_MID,
    "--ink-muted": INK_MUTED,
    "--rust": RUST,
    "--rust-light": RUST_LIGHT,
    "--gold": GOLD,
    "--gold-dim": GOLD_DIM,
    "--rule": RULE,
    "--void": VOID,
    "--ok": OK,
    "--warn": WARN,
    "--danger": DANGER,
    "--warn-wash": WARN_WASH,
    "--font-body": FONT_BODY,
    "--font-display": FONT_DISPLAY,
    "--font-logo": FONT_LOGO,
    "--dur-instant": DUR_INSTANT,
    "--dur-fast": DUR_FAST,
    "--dur-medium": DUR_MEDIUM,
    "--dur-slow": DUR_SLOW,
    "--dur-ritual": DUR_RITUAL,
    "--ease-oracle": EASE_ORACLE,
    "--ease-in-breath": EASE_IN_BREATH,
    "--ease-out-breath": EASE_OUT_BREATH,
    "--space-xs": SPACE_XS,
    "--space-sm": SPACE_SM,
    "--space-md": SPACE_MD,
    "--space-lg": SPACE_LG,
    "--radius-sm": RADIUS_SM,
    "--radius-md": RADIUS_MD,
    "--radius-pill": RADIUS_PILL,
}


def css_root_block() -> str:
    """`:root { ... }` for injection into PAGE_STYLE, so CSS can use var(--rust)."""
    body = "\n".join(f"  {name}: {value};" for name, value in CSS_VARIABLES.items())
    return f":root {{\n{body}\n}}"
