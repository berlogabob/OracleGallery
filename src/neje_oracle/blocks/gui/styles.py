"""The one stylesheet, from the tokens.

PAGE_STYLE is every CSS rule the operator GUI ships; tokens.py supplies the variables it
references. This file is a STYLE_OWNER together with ui.py and tokens.py: view code
composes components and never styles. It used to be a 200-line string literal inside
service.py -- 60% of the module -- where every layout comment competed with the shell's
lifecycle code for attention.
"""

from __future__ import annotations

from . import tokens

PAGE_STYLE = """
<style>
__TOKENS_PLACEHOLDER__
  body { background: var(--bg); color: var(--text); overflow: auto; font-family: var(--font-ui); }
  .q-field__control { min-height: 40px !important; }
  .q-field__label { font-size: var(--type-sm); }
  /* nicegui's own page padding is absent from every height calculation below, so the
     shell owns the viewport outright rather than racing it. */
  .nicegui-content { padding: 0 !important; }
  .oracle-shell { min-height: 100dvh; overflow: visible; box-sizing: border-box; }
  .oracle-card {
    width: 100%;
    padding: var(--space-md);
    /* nicegui puts gap:1rem between every child of .nicegui-card. The old override set
       padding only, so calibration's third card carried ~300px of invisible gap. */
    gap: var(--space-sm);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    box-shadow: 0 8px 22px rgba(15, 18, 20, 0.06);
  }
  .oracle-title { letter-spacing: 0.16em; color: var(--accent); }
  .compact-card { padding: 10px 12px !important; }
  /* One 40px bar carries identity, navigation, state, position, profile and the stops.
     It replaces a 44px header row plus a ~40px status row; the reclaimed height goes to
     the canvas, which is the thing an operator actually watches. */
  .top-bar {
    height: 40px;
    flex-wrap: nowrap;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 2px 10px;
  }
  .top-title { font-size: var(--type-lg); }
  .top-bar .workspace-tabs { border: 0; background: transparent; min-height: 36px; flex: 0 1 auto; }
  .top-bar .q-tab { min-height: 34px; }
  .print-canvas { min-width: 0; overflow: hidden; }
  /* CREATE panes: one source visible at a time, canvas track + 340px knobs track.
     grid-auto-rows pins the single row to the pane height so h-full children resolve. */
  .create-pane { flex: 1 1 auto; min-height: 0; grid-auto-rows: 100%; }
  .create-canvas { min-width: 0; overflow: hidden; }
  .create-panel { overflow-y: auto; }
  .create-strip { border-top: 1px solid var(--border); padding-top: var(--space-xs); flex: 0 0 auto; }
  .preview-fill { background: var(--sunken); border: 1px solid var(--border); border-radius: var(--radius-md); }
  /* Quasar's tab panel is not a flex child by default, so height:100% below it resolves
     to auto and the canvas column grows past the viewport instead of letting the
     preview scroll internally. Chain the height down explicitly. */
  .workspace-panel .q-tab-panels { height: 100%; }
  .workspace-panel .q-tab-panel { height: 100%; display: flex; flex-direction: column; padding: 0; }
  .workspace-panel .q-tab-panel > * { flex: 1 1 auto; min-height: 0; }
  /* The run band: slim rows on one flat surface, hairline-separated -- not stacked cards. */
  .run-band {
    border-left: 1px solid var(--border);
    padding: 4px 8px;
    overflow-y: auto;
    min-height: 0;
  }
  .status-spacer { flex: 1 1 auto; }
  /* A deliberate dead zone, not decoration: the one control that must never be pressed
     by accident does not sit flush against the one next to it. */
  .estop-gap { width: var(--space-lg); flex: 0 0 auto; }
  .state-chip {
    font-size: var(--type-sm);
    font-weight: 700;
    letter-spacing: 0.12em;
    padding: 5px 10px;
    border-radius: var(--radius-pill);
    border: 1px solid var(--border);
    white-space: nowrap;
    transition: color var(--dur-med) var(--ease-standard), background var(--dur-med) var(--ease-standard),
      border-color var(--dur-med) var(--ease-standard);
  }
  .state-ok { color: var(--ok); border-color: var(--ok); }
  .state-run { color: var(--text); border-color: var(--text); }
  .state-warn { color: var(--warn); border-color: var(--warn); background: var(--warn-wash); }
  .state-danger { color: var(--surface); background: var(--danger); border-color: var(--danger); }
  .state-offline { color: var(--text-muted); border-color: var(--border); }
  .position-readout {
    font-family: var(--font-mono);
    font-size: var(--type-sm);
    color: var(--text);
    white-space: nowrap;
  }
  .live-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(104px, 1fr));
    gap: 6px;
    align-items: stretch;
    flex: 0 1 auto;
  }
  .live-strip .mini-metric { background: var(--surface); }
  .live-strip .next-action { border-color: var(--accent); background: var(--surface); }
  .mobile-operator-warning {
    display: none;
    background: var(--warn-wash);
    border: 1px solid var(--warn);
    border-radius: var(--radius-md);
    color: var(--warn);
    padding: 8px 10px;
    font-size: var(--type-sm);
    font-weight: 700;
  }
  /* One definition. A second, unscoped block used to set .q-tab to 42px, beating the
     .top-bar rule at equal specificity and overflowing the 40px bar by 2px (audit F-tabs). */
  .workspace-tabs .q-tab { padding: 0 12px; letter-spacing: 0.08em; font-weight: 700; }
  .workspace-tabs .q-tab--active { color: var(--accent); }
  /* These were three hand-counted constants and all three were wrong: 104px was reserved
     against 235px of real chrome, so 131px fell off the bottom -- clipped rather than
     scrolled, because the shell is overflow:hidden at >=1200px. The scroll box was also
     83px taller than the area it displayed in, putting the bottom of every workspace out
     of reach even at the end of the scroll. Flex takes whatever the header actually
     leaves, at any header height, so there is no number left to get wrong.
     width:100% is what fills the dead column: workspace roots sized to their content. */
  .workspace-panel { flex: 1 1 auto; min-height: 0; }
  .workspace-scroll {
    width: 100%;
    height: 100%;
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 8px;
    box-sizing: border-box;
  }
  .preview-frame { flex: 1 1 auto; min-height: 0; overflow: auto; width: 100%; }
  .preview-frame svg { display: block; width: auto; height: auto; max-width: none; max-height: none; }
  .path-label { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tight-slider .q-slider { min-height: 28px; }
  .warning-banner { background: var(--warn-wash); border: 1px solid var(--warn); border-radius: var(--radius-md); color: var(--warn); padding: 6px 8px; font-size: var(--type-sm); }
  .log-viewer textarea { font-family: var(--font-mono); font-size: 11px; line-height: 1.35; }
  .q-btn { min-height: 30px; }
  .mini-metric { border: 1px solid var(--border); border-radius: var(--radius-md); padding: 5px 7px; background: var(--surface); }
  .mini-metric .label { font-size: var(--type-xs); letter-spacing: 0.16em; color: var(--text-muted); text-transform: uppercase; }
  .mini-metric .value { font-size: var(--type-sm); font-weight: 700; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .preview-legend { border-top: 1px solid var(--border); padding-top: 6px; }
  .legend-chip { display: flex; align-items: center; gap: 5px; font-size: var(--type-xs); color: var(--text); white-space: nowrap; }
  .legend-dot { width: 9px; height: 9px; border-radius: var(--radius-pill); border: 1px solid var(--text); display: inline-block; flex: 0 0 auto; }
  .legend-ring { width: 15px; height: 15px; border-radius: var(--radius-pill); border: 1.5px solid var(--text); display: inline-block; flex: 0 0 auto; }
  .legend-double-ring { box-shadow: inset 0 0 0 3px var(--surface), inset 0 0 0 4.4px var(--text); }
  @media (min-width: 1200px) {
    body { overflow: hidden; }
    .oracle-shell { height: 100dvh; max-height: 100dvh; overflow: hidden; }
  }
  @media (max-width: 1199px) {
    .oracle-shell { height: auto; overflow: visible; }
    .workspace-grid { grid-template-columns: 1fr !important; height: auto !important; overflow: visible !important; }
    .workspace-scroll { height: auto; max-height: none; overflow: visible; padding-right: 0; }
    .preview-frame { max-height: 70vh; }
    .path-label { max-width: 100%; white-space: normal; }
    .live-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .status-spacer { display: none; }
  }
  @media (max-width: 760px) {
    .oracle-shell { min-width: 560px; }
    .mobile-operator-warning { display: block; }
    .workspace-tabs { overflow-x: auto; }
  }
  /* The rail is fixed-width and always present, so it must not shrink with the
     workspace beside it -- a jog button that moves is a jog button you mis-hit. */
  .machine-rail { display: flex; flex-direction: column; gap: var(--space-sm); width: 100%; }
  .jog-pad { display: grid; gap: var(--space-xs); width: 100%; justify-items: center; }
  .jog-pad .q-btn { width: 100%; min-width: 0; }
  /* --- components (blocks/gui/ui.py emits these; nothing else styles) --- */
  .oracle-workspace { display: flex; flex-direction: column; gap: var(--space-sm); }
  .oracle-card-title { font-size: var(--type-md); font-weight: 700; color: var(--text); }
  .oracle-helper { font-size: var(--type-sm); color: var(--text-mid); max-width: 65ch; }
  .oracle-toolbar { display: flex; align-items: center; gap: var(--space-sm); }
  .oracle-toolbar-wide { width: 100%; }
  .oracle-field { min-width: 7rem; }
  .oracle-btn {
    border-radius: var(--radius-sm);
    letter-spacing: 0.04em;
    transition: background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard),
      border-color var(--dur-fast) var(--ease-standard);
  }
  .oracle-btn-primary { background: var(--accent) !important; color: var(--surface) !important; }
  /* A bordered ghost, not bare text. Flat Quasar buttons render as a label with no
     chrome, which is how PEN UP / HOME X / Z UP ended up visually indistinguishable from
     static text while filled buttons sat beside them running the same class of machine
     command (audit F-006, F-007, F-023, F-024). Every clickable action gets an
     affordance. */
  .oracle-btn-safe {
    color: var(--text-mid) !important;
    border: 1px solid var(--border);
    background: var(--surface) !important;
  }
  .oracle-btn-safe:hover { border-color: var(--accent); color: var(--accent) !important; }
  .oracle-btn-danger { background: var(--danger) !important; color: var(--surface) !important; }
  .oracle-btn-stop {
    color: var(--danger) !important;
    border: 1px solid var(--danger);
    background: var(--surface) !important;
  }
  .oracle-btn-estop { background: var(--danger) !important; color: var(--surface) !important; font-weight: 800; }
  .oracle-btn-nudge { color: var(--text-mid) !important; min-width: 0; }
  .oracle-embed { width: 100%; border: 0; background: var(--surface); border-radius: var(--radius-md); }
  .oracle-embed-fill { flex: 1 1 auto; min-height: 0; height: 100%; }
  .oracle-metric-line { font-size: var(--type-sm); color: var(--text-muted); }
  .oracle-micro-label {
    font-size: var(--type-xs);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }
</style>
"""


def page_style() -> str:
    """The stylesheet with the token variables substituted in."""
    return PAGE_STYLE.replace("__TOKENS_PLACEHOLDER__", tokens.css_root_block())
