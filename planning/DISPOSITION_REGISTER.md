# Disposition Register

Every removal, hide, or retirement of something operator-meaningful gets a row here
before it happens. "Deleted" requires proof of unreachability or equivalence; "hidden"
means still in code, off by default. Nothing operator-meaningful is silently deleted.

| Date | Item | Disposition | Evidence / equivalence | Commit |
|---|---|---|---|---|
| 2026-08-15 | `chore/simplify` branch (local + origin) | deleted | `git cherry main chore/simplify` — all 41 commits have equivalents on main (D3=68fff43, D4=1117146, E1=c19c23f, live-preview=6322f42, stream gate=d374497) | — |
| 2026-08-15 | Parked defect B9 (sketch.js `buildSvg` serializer) | closed in code | All emitted shape types (`circle` ×9, `polyline` ×33) serialized by `buildSvg` (sketch.js:74); whole-frame guarantee for `window.currentSvg()` at sketch.js:1118-1162. Physical print verification pending in redesign Phase F smoke plots. | — |
