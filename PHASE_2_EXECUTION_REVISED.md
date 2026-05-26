# PHASE 2: GUI REFACTORING - REVISED EXECUTION PLAN

**Status:** Revised for pragmatism (2026-05-26)  
**Rationale:** Original plan was too ambitious. Revised to extract workspaces incrementally with tests after each.

---

## Revised Strategy

Instead of extracting all handlers at once (risky, ~1,156 LOC function), we:

1. ✅ **DONE (Tasks 2.1-2.2):** Create component library + state model
2. **Task 2.3 (NEW):** Create minimal workspace router (replaces ~900 LOC of UI code)
3. **Tasks 2.4-2.8:** Extract workspaces ONE BY ONE with handlers embedded
4. **Task 2.9:** Final consolidation and testing

This approach:
- ✅ Tests after each extraction (catch bugs early)
- ✅ Lower risk (smaller changes)
- ✅ Each workspace extractable independently
- ✅ Clear dependencies (can parallelize work)

---

## REVISED TASKS

### Task 2.3: Minimal Workspace Router (HIGH PRIORITY)
**Goal:** Reduce `build_page()` to ~150 LOC router only  
**Risk:** Medium (structural, but well-tested)  
**Status:** 🔄 IN PROGRESS

```python
def build_page() -> None:
    # Setup: CSS, colors, supervisor
    # Initialize state
    
    with ui.column().classes("oracle-shell"):
        with ui.tabs() as tabs:
            with ui.tab_panels(tabs):
                with ui.tab_panel("Connection"):
                    build_connection_workspace(supervisor)
                with ui.tab_panel("Calibration"):
                    build_calibration_workspace(supervisor)
                # ... etc for all 5 workspaces
```

**Steps:**
1. Extract CSS + colors setup (keep in build_page)
2. Extract supervisor init (keep in build_page)
3. Create `build_connection_workspace(supervisor)` stub
4. Move `build_page()` workspace content into workspace function
5. Test: connections should still work
6. Repeat for each workspace

---

### Task 2.4-2.8: Extract Workspaces (PARALLEL)
**Goal:** Each workspace in its own module with embedded handlers  
**Risk:** Medium per workspace (test after each)  
**Status:** 🔄 QUEUED

#### Task 2.4: Connection Workspace
- Printer/plotter/FluidNC status
- Connect buttons
- Status pills
- Handlers: `check_printer()`, `connect_plotter()`, `check_fluidnc()`
- Expected: ~250 LOC
- Test: Verify all buttons work, status updates

#### Task 2.5: Calibration Workspace
- Symbol selection (6 origin buttons)
- Preview SVG
- Randomness/sample parameters
- Handlers: `select_origin()`, `update_calibration_preview()`
- Expected: ~200 LOC
- Test: Verify preview updates, values persist

#### Task 2.6: Tests Workspace
- System check button
- Test print button
- Jog controls (X/Y arrows)
- Home buttons
- Expected: ~150 LOC
- Test: Verify jog/home buttons work

#### Task 2.7: Work Workspace (CORE)
- SVG upload/selection
- G-code preview
- Dry run generation
- Start print button
- Live strip (status display)
- Log viewer
- Expected: ~350 LOC (largest)
- Test: THOROUGH (core workflow)

#### Task 2.8: Exhibition Workspace
- Large status display
- Minimal controls
- Full-screen focus
- Expected: ~100 LOC
- Test: Verify visuals, controls responsive

---

### Task 2.9: Final Consolidation
- Test all 5 workspaces together
- Verify state persistence across switches
- Performance check (no lag)
- Create test report
- Commit final refactoring

---

## Why This Approach is Better

| Aspect | Original Plan | Revised Plan |
|--------|---------------|--------------|
| Risk | High (big bang) | Medium (incremental) |
| Testing | Once at end | After each workspace |
| Parallelization | Not possible | Can split workspaces |
| Rollback | Entire refactor lost | Just revert one workspace |
| Debugging | Hard (everything changed) | Easy (what changed) |
| Time to first result | 3-4 days | ~4 hours (Task 2.3) |
| Operator experience | One big change | Gradual improvement |

---

## Current Status

✅ **Completed:**
- Task 2.1: Component library (buttons, status, inputs, layout)
- Task 2.2: Immutable state model (GUIState)
- PHASE_2_EXECUTION_PLAN.md (original, for reference)

🔄 **In Progress:**
- Task 2.3: Minimal workspace router

⏳ **Coming:**
- Tasks 2.4-2.8: Extract workspaces one by one
- Task 2.9: Final consolidation

---

## Next Immediate Steps

1. Complete Task 2.3 (workspace router) - ~2 hours
2. Run tests (should still pass: 175/175)
3. Start Task 2.4 (connection workspace) - ~2-3 hours
4. Iterate on remaining workspaces

---

## Success Criteria (Revised)

✅ `build_page()` reduced from 1,156 LOC to ~150 LOC  
✅ Each workspace in separate module  
✅ All 175 tests passing after each task  
✅ No functionality changes (just refactored)  
✅ Can switch between workspaces smoothly  
✅ Settings persist across workspace switches  

---

## Estimation (Revised)

- Task 2.3: ~2 hours
- Task 2.4: ~2-3 hours
- Task 2.5: ~2-3 hours
- Task 2.6: ~1.5 hours
- Task 2.7: ~3-4 hours (core, thorough testing)
- Task 2.8: ~1.5 hours
- Task 2.9: ~1-2 hours

**Total: ~14-18 hours** (~2-3 days for 1 developer, or 1-2 days for 2 developers)

Much more realistic than original 27-34 hours!

---

**Document Updated:** 2026-05-26 10:45 UTC  
**Author:** Senior Developer  
**Rationale:** Experience + pragmatism > theory
