# Disposition Register

Every removal, hide, or retirement of something operator-meaningful gets a row here
before it happens. "Deleted" requires proof of unreachability or equivalence; "hidden"
means still in code, off by default. Nothing operator-meaningful is silently deleted.

| Date | Item | Disposition | Evidence / equivalence | Commit |
|---|---|---|---|---|
| 2026-08-15 | `chore/simplify` branch (local + origin) | deleted | `git cherry main chore/simplify` — all 41 commits have equivalents on main (D3=68fff43, D4=1117146, E1=c19c23f, live-preview=6322f42, stream gate=d374497) | — |
| 2026-08-15 | Parked defect B9 (sketch.js `buildSvg` serializer) | closed in code | All emitted shape types (`circle` ×9, `polyline` ×33) serialized by `buildSvg` (sketch.js:74); whole-frame guarantee for `window.currentSvg()` at sketch.js:1118-1162. Physical print verification pending in redesign Phase F smoke plots. | — |
| 2026-08-16 | Five dead `build()` shims (calibration, generative, image, texture, work) | deleted | Unreachable from service.py; only tests called them. Tests re-pointed to the real entry points (`build_sections`, `build_controls`, `build_diagnostics`, canvas+controls pair), preserving the ctx-key assertions. | B1/B2 commit |
| 2026-08-16 | Five section-builder return contracts | replaced | One `ui.Section` dataclass (root/refresh/print/print_label/on_show); behavior identical, `measure_gui --gate` still 1.0x, 612 tests green. | B1/B2 commit |
| 2026-08-16 | M2 target "print entry points -> 1" | revised to 2 (met) | The two remaining calls are different artifacts (CREATE strip payload path; VERIFY uploaded-SVG). Folding one into ui.py would move it out of the counted glob without simplifying anything -- metric gaming. | B6-B8 commit |
