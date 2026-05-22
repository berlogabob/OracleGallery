# NejeDraw GUI Redesign Audit Plan

## Summary
- Scanned both GUI surfaces: the NiceGUI operator app in [gui_service.py](/Users/berloga/Documents/GitHub/NejeDraw/src/neje_oracle/gui_service.py) and the Flutter public gallery in [public_gallery/lib](/Users/berloga/Documents/GitHub/NejeDraw/public_gallery/lib).
- Compared current UI against the project design system and wireframe brief in [oracle_design_system.html](/Users/berloga/Documents/GitHub/NejeDraw/assets/Design%20system/oracle_design_system.html) and [oracle_wireframe_brief.md](/Users/berloga/Documents/GitHub/NejeDraw/assets/WebsiteWireframe/Oracle_website_wireframe/uploads/oracle_wireframe_brief.md).
- Visual-tested desktop `1280x720` and mobile `390x844`. Automated checks passed: Python compile, 47 GUI-related Python tests, Flutter tests, and Flutter analyze.

## Key Improvements
- **Operator GUI: clarify the live operating state.** Add a persistent “Now / Next / Blockers” strip showing FluidNC, work zero, Firebase, queue, current sheet, and next permitted action. This reduces exhibition stress because operators should not infer readiness from scattered cards.
- **Operator GUI: simplify action hierarchy.** Use one dominant primary action per workspace, reserve red for emergency/reset/stop, and normalize labels such as `START`, `Start`, `PRINT SELECTED`, `Generate G-code only`. Current mixed button styles make operational risk feel equal to routine actions.
- **Operator GUI: make calibration progressive.** Keep sheet size, cell, margin, gap, preview mode visible; move sampling, organic/Voronoi, symbol correction, and streaming mode behind “Advanced”. This preserves power while keeping setup scannable.
- **Operator GUI: improve empty/right-column states.** Tests and some workspaces can leave large blank panels. Replace blanks with contextual checklists, recent status, or “not applicable in this workspace” states so operators trust the layout.
- **Operator GUI: define supported viewport.** Mobile currently overflows (`595px` content in a `390px` viewport). Either make the operator app tablet/desktop-only with a clear minimum-width warning, or add a true single-column mobile layout.

- **Public gallery: fix mobile navigation overflow.** At `390px`, nav clips links and Flutter reports overflow. Reduce logo/link spacing and letter spacing, or use a compact two-row nav while keeping all links visible as the brief requires.
- **Public gallery: align home with the brief.** Current hero is text-only. Add the Oracle portrait/primary visual signal, use “The Oracle That Wears Us” where appropriate, and make lookup copy “Find your mark”. This makes the site feel like the installation, not a generic landing page.
- **Public gallery: make lookup behavior consistent.** Home and cloth lookup should route to `/cloth?session=<id>` for highlighting; QR receipt can keep `/#/session/<id>`. This matches the brief and improves visitor recovery from printed receipts.
- **Public gallery: strengthen the cloth viewer.** Keep the performant painted grid, but add clear scroll/zoom affordances, found-session highlight behavior, a reading/details panel, and actual share prompt. Mobile visitors need obvious proof that lookup worked.
- **Public gallery: redesign marks cards.** Current marks read as similar circular outlines at small size. Use the brief’s card structure: void visual panel, larger high-contrast SVG, emotion/name/description/oracle reading. This makes the eight marks distinguishable and meaningful.
- **Public gallery: complete missing structure.** Add the `Team` route/page if the website brief remains authoritative, and expand About with video/how-it-works content. Current public IA is smaller than the approved wireframe.

## Interfaces
- No backend or Firebase data contract changes required for the redesign.
- Public route behavior should standardize as:
  - `/#/session/<session_id>` remains QR receipt detail.
  - `/#/cloth?session=<session_id>` becomes the lookup/highlight destination.
  - `/#/team` is added only if the wireframe brief is still in scope.
- Add UI-only state for cloth highlight/details/share; derive it from existing `SessionData`.

## Test Plan
- Keep existing checks: `uv run python -m py_compile src/neje_oracle/*.py`, GUI pytest suite, `flutter test`, and `flutter analyze`.
- Add visual regression screenshots for operator workspaces at desktop/tablet and public routes at desktop/mobile.
- Add Flutter widget tests for mobile nav fitting, lookup routing to `/cloth?session=...`, session-not-found state, and marks card rendering with visible non-empty SVG content.
- Add manual exhibition scenario test: Connection → Calibration → Tests → Work → Exhibition, verifying that the next action and blockers are visible at every step.

## Assumptions
- Redesign covers both the operator control GUI and the public gallery because the request asked for a full GUI scan.
- Operator GUI should optimize for a MacBook/tablet exhibition operator, not phone-first use.
- Public gallery should optimize for phone QR visitors first, especially `/cloth` and `/session/<id>`.
- The bundled design system and wireframe brief are treated as the visual/product authority unless superseded by the team.
