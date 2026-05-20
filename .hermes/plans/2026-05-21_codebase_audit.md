# NejeDraw — 2026-05-21 Codebase Self-Audit Report

**Date:** 2026-05-21
**Scope:** `src/neje_oracle/` (25 files, 9,423 LOC total)

## 🔍 Key Findings
- **Mypy Errors**: 62 errors (unchanged from 2025-05-20 audit)
- **Docstring Coverage**: Still 0.7% (2/269 public API)
- **BLE001 Warnings**: 37 broad-except occurrences (hotspots in `supervisor.py` [10], `plotter_daemon.py` [6])
- **Test Coverage**: 163/163 tests passed, but **6 files remain untested**
- **New Files**: `firebase_svg_normalizer.py` (95 LOC) and `gui_modes.py` (62 LOC) added since last audit

## 📊 Structural Analysis
| File | LOC | Risk Flags |
|------|-----|------------|
| `gui_service.py` | 1K | 28% mypy errors |
| `heatmap.svg_normalizer.py` | 356 | CC=19 (highest) |
| `preflight.py` | 210 | CC=17, 4 BLE001 |
| `svg_gcode.py` | 488 | CC=14 |
| `supervisor.py` | 830 | 10 BLE001 |
| `firebase_svg_normalizer.py` | 95 | New file (no audit data yet) |
| `gui_modes.py` | 62 | New file (no audit data yet) |

## 🚨 Critical Concerns
1. **Legacy Debt**: `models.py` (586 LOC) and `config.py` (161 LOC) still have **no docstrings**
2. **Uncovered Code**: `plotter_service.py`, `uploader_service.py`, and 4 new files lack test coverage
3. **Complexity Hotspots**: `heatmap.svg_normalizer.py` (CC=19) and `preflight.py` (CC=17) remain problematic

## ✅ Improvements Detected
- `store.py` (440 LOC) maintains **zero BLE001** and clean structure
- `transport.py` (413 LOC) shows **reduced complexity** compared to 2025 audit

## 🛠️ Recommendations
1. Add docstrings to **all public API** (target 100% coverage)
2. Implement tests for **new files** (`firebase_svg_normalizer.py`, `gui_modes.py`)
3. Refactor `heatmap.svg_normalizer.py` (CC=19) and `preflight.py` (CC=17)
4. Address **mypy errors in gui_service.py** (28% of total errors)

Audit completed in 2026-05-21 at 00:10:00