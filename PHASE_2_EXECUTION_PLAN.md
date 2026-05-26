# PHASE 2: GUI Refactoring - Execution Plan

**Execution Date:** 2026-05-26  
**Target Timeline:** 2-3 weeks (1-2 developers)  
**Risk Level:** Medium (architectural changes, well-tested)  
**Value:** Very High (enables safe feature development)

---

## Goal

Break the monolithic GUI service from **1,231 LOC** (with `build_page()` ~1,100 LOC) into:
- **~300 LOC** `gui_service.py` (main entry, initialization)
- **~50 LOC** `build_page()` (only workspace routing)
- **5+ workspace modules** (connection, calibration, tests, work, exhibition)
- **Reusable component library** (buttons, status, inputs)
- **Clear state model** (immutable SystemState)

---

## Architecture Target

```
gui_service.py (entry point)
├── main() - entry, RBAC check, port config
├── build_page() - workspace router only
└── Components/
    ├── components/
    │   ├── buttons.py (safe/danger/primary buttons)
    │   ├── status.py (status pills, badges)
    │   ├── inputs.py (number/text controls)
    │   └── layout.py (common containers, grids)
    ├── workspaces/
    │   ├── connection_workspace.py (~150 LOC)
    │   ├── calibration_workspace.py (~150 LOC)
    │   ├── tests_workspace.py (~120 LOC)
    │   ├── work_workspace.py (~200 LOC)
    │   └── exhibition_workspace.py (~120 LOC)
    ├── state/
    │   └── gui_state.py (immutable SystemState)
    └── handlers/
        └── event_handlers.py (all async handlers)
```

---

## Key Refactoring Principles

1. **Single Responsibility**: Each component/workspace has ONE job
2. **Immutable State**: All state changes create new objects, never mutate
3. **No Side Effects in Functions**: Event handlers are pure, effects explicit
4. **Clear Dependencies**: No circular imports, dependency tiers enforced
5. **Testability**: Each component can be unit tested in isolation
6. **Reusability**: Components work with any workspace

---

## Phase 2 Detailed Tasks

### Week 1: Foundation & Component Library

#### Task 2.1: Create Component Library Structure
- [ ] Create `src/neje_oracle/gui_components/` directory
- [ ] Create `__init__.py` with exports
- [ ] Create `components/buttons.py` with:
  - `safe_action_button()` - green, safe operations
  - `danger_action_button()` - red, destructive operations
  - `primary_action_button()` - primary actions
  - All accept size, color, icon parameters
- [ ] Create `components/status.py` with:
  - `status_pill()` - colored status badge
  - `update_status_pill()` - reactive updates
  - Support all ComponentStatus states
- [ ] Create `components/inputs.py` with:
  - `number_control()` - input + slider
  - All validation built-in
- [ ] Create `components/layout.py` with:
  - `oracle_card()` - styled container
  - `live_strip()` - 6-column layout
  - `section_header()` - titled sections
- [ ] Run tests (should still pass: 175/175)

**Effort:** ~2-3 hours  
**Risk:** Very Low (pure extraction)

---

#### Task 2.2: Create Immutable GUI State Model
- [ ] Create `src/neje_oracle/gui_state.py`
- [ ] Define `GUIState` dataclass (immutable):
  ```python
  @dataclass(frozen=True)
  class GUIState:
      active_workspace: str = "connection"
      preview_mode: str = "preview"
      selected_svg_name: str = ""
      selected_svg_bytes: bytes = b""
      all_fields: dict[str, Any] = field(default_factory=dict)
      all_scales: dict[str, Any] = field(default_factory=dict)
      all_symbols: list[str] = field(default_factory=list)
      
      def with_workspace(self, workspace: str) -> "GUIState": ...
      def with_preview_mode(self, mode: str) -> "GUIState": ...
      # ... other immutable updates
  ```
- [ ] Create `GUIStateManager` class for persisting to runtime store
- [ ] Add type hints everywhere
- [ ] No mutable state anywhere
- [ ] Run tests (should still pass: 175/175)

**Effort:** ~1-2 hours  
**Risk:** Very Low (new code, no existing logic changes)

---

#### Task 2.3: Extract Event Handlers Module
- [ ] Create `src/neje_oracle/gui_handlers.py`
- [ ] Extract all nested functions from `build_page()`:
  - `pull_settings_from_fields()`
  - `persist_and_refresh()`
  - `update_gcode_detail_labels()`
  - `update_scales_from_fields()`
  - `handle_svg_upload()`
  - `print_uploaded_svg()`
  - `generate_dry_run()`
  - `update_preview()`
  - `refresh_status()`
  - `refresh_component_status()`
  - `start_system()`
  - `stop_system()`
  - `reset_baseline()`
  - `set_system_mode()`
  - `workspace_changed()`
  - `preview_mode_changed()`
  - `run_system_check()`
  - `start_print()`
  - `start_test_print()`
  - ... all ~20+ handlers
- [ ] Convert to standalone functions that take state as parameter
- [ ] Return new state instead of mutating
- [ ] All handlers are async-safe
- [ ] Run tests (should still pass: 175/175)

**Effort:** ~3-4 hours  
**Risk:** Low (pure extraction, no logic changes)

---

#### Task 2.4: Extract Workspace Router Function
- [ ] Create minimal `build_page()` that:
  ```python
  def build_page() -> None:
      state = load_gui_state()
      
      with ui.column().classes("oracle-shell"):
          with ui.tabs().classes("workspace-tabs") as tabs:
              tabs.on_change(handle_workspace_change)
              
              with ui.tab_panels(tabs).classes("workspace-panels"):
                  with ui.tab_panel("connection"):
                      build_connection_workspace(state)
                  with ui.tab_panel("calibration"):
                      build_calibration_workspace(state)
                  with ui.tab_panel("tests"):
                      build_tests_workspace(state)
                  with ui.tab_panel("work"):
                      build_work_workspace(state)
                  with ui.tab_panel("exhibition"):
                      build_exhibition_workspace(state)
  ```
- [ ] ~50 LOC instead of 1,100
- [ ] No business logic
- [ ] Just routing + layout
- [ ] Run tests (should still pass: 175/175)

**Effort:** ~1-2 hours  
**Risk:** Low (structural refactoring)

---

### Week 2: Workspace Extraction

#### Task 2.5: Extract Connection Workspace
- [ ] Create `src/neje_oracle/gui_workspaces/connection.py`
- [ ] Move connection setup UI from `build_page()`:
  - Printer connect button
  - Plotter connect section
  - FluidNC connect section
  - Status pills for each
- [ ] Signature: `def build_connection_workspace(state: GUIState) -> None:`
- [ ] ~150 LOC expected
- [ ] All handlers reference from `gui_handlers.py`
- [ ] Test thoroughly (verify status updates work)

**Effort:** ~2-3 hours  
**Risk:** Medium (UI behavior must match exactly)

---

#### Task 2.6: Extract Calibration Workspace
- [ ] Create `src/neje_oracle/gui_workspaces/calibration.py`
- [ ] Move calibration/setup UI:
  - Symbol origin selection (6 options with preview)
  - Origin preview SVG
  - Randomness slider
  - Sample step controls
  - Save/apply buttons
- [ ] ~150 LOC expected
- [ ] Signature: `def build_calibration_workspace(state: GUIState) -> None:`
- [ ] Test preview updates on value changes

**Effort:** ~2-3 hours  
**Risk:** Medium (SVG preview must match)

---

#### Task 2.7: Extract Tests Workspace
- [ ] Create `src/neje_oracle/gui_workspaces/tests.py`
- [ ] Move test UI:
  - System check button
  - Test print button
  - Set work zero button
  - FluidNC status check
  - Test results display
- [ ] ~120 LOC expected
- [ ] Signature: `def build_tests_workspace(state: GUIState) -> None:`
- [ ] All async handlers working

**Effort:** ~2 hours  
**Risk:** Medium (async behavior)

---

#### Task 2.8: Extract Work Workspace
- [ ] Create `src/neje_oracle/gui_workspaces/work.py`
- [ ] Move production UI:
  - SVG upload
  - G-code preview modes
  - Dry run generation
  - Print button
  - Live strip (status + next action)
  - Log viewer
  - Queue status display
- [ ] ~200 LOC expected (largest workspace)
- [ ] Signature: `def build_work_workspace(state: GUIState) -> None:`
- [ ] This is core production workflow - test heavily

**Effort:** ~3-4 hours  
**Risk:** HIGH (core workflow, test thoroughly)

---

#### Task 2.9: Extract Exhibition Workspace
- [ ] Create `src/neje_oracle/gui_workspaces/exhibition.py`
- [ ] Move exhibition mode UI:
  - Full-screen mode toggle
  - Live plotter status
  - Minimal controls (start/stop)
  - Large status display
  - No settings shown
- [ ] ~120 LOC expected
- [ ] Signature: `def build_exhibition_workspace(state: GUIState) -> None:`
- [ ] Focus on visibility and minimal controls

**Effort:** ~2 hours  
**Risk:** Medium (new UX pattern)

---

### Week 3: Integration & Testing

#### Task 2.10: Verify All Tests Still Pass
- [ ] Run full test suite: `uv run pytest -q`
- [ ] Expected: 175/175 passing
- [ ] No logic changes, so no new failures expected
- [ ] If any fail, debug immediately
- [ ] Create test log: `PHASE_2_TEST_LOG.txt`

**Effort:** ~30 minutes  
**Risk:** Low (should pass - pure refactoring)

---

#### Task 2.11: Integration Testing - Connection Workflow
- [ ] Start GUI: `uv run nje-gui`
- [ ] Test Connection workspace:
  - [ ] Click printer connect button
  - [ ] Verify status pill updates
  - [ ] Click plotter connect
  - [ ] Verify status pill updates
  - [ ] Click FluidNC check
  - [ ] Verify all statuses correct
  - [ ] Switch workspaces, come back
  - [ ] Verify state persists
- [ ] Duration: ~15 minutes
- [ ] Create test report: `TEST_CONNECTION_WORKSPACE.md`

**Effort:** ~30 minutes  
**Risk:** Medium (live system)

---

#### Task 2.12: Integration Testing - Work Workflow
- [ ] Start GUI: `uv run nje-gui`
- [ ] Test Work workspace (core workflow):
  - [ ] Upload test SVG
  - [ ] Verify preview renders
  - [ ] Switch to "printing" preview mode
  - [ ] Verify G-code preview shows
  - [ ] Click dry run
  - [ ] Verify G-code file path shown
  - [ ] Try print button (should check system first)
  - [ ] Verify all status updates work
- [ ] Duration: ~20 minutes
- [ ] Create test report: `TEST_WORK_WORKSPACE.md`

**Effort:** ~45 minutes  
**Risk:** Medium (core workflow)

---

#### Task 2.13: Code Quality & Cleanup
- [ ] All imports organized (no unused)
- [ ] Type hints on all functions
- [ ] Docstrings on all public functions
- [ ] No trailing whitespace
- [ ] Line lengths < 100 characters
- [ ] No print() statements (use logger)
- [ ] Run black formatter: `uv run black src/`
- [ ] Run mypy type checking: `uv run mypy src/`

**Effort:** ~1-2 hours  
**Risk:** Very Low

---

#### Task 2.14: Create Phase 2 Completion Report
- [ ] Lines of code before/after
- [ ] Complexity metrics (cyclomatic complexity reduction)
- [ ] Test coverage summary
- [ ] Performance comparison (GUI load time)
- [ ] Risk assessment
- [ ] Recommendations for Phase 3

**Effort:** ~1 hour  
**Risk:** Very Low

---

## Testing Strategy

### Unit Tests (Auto, via pytest)
- Should continue passing (175/175)
- No logic changed, only refactored

### Manual GUI Tests
1. **Connection workflow** (5 min)
   - Verify all connect buttons work
   - Status pills update correctly

2. **Settings workflow** (5 min)
   - Change values in each workspace
   - Verify persistence across workspace switches
   - Reload page, verify settings restored

3. **Work workflow** (10 min)
   - Upload SVG
   - Generate dry run
   - Try print (with system check)

4. **Performance** (5 min)
   - Measure GUI load time
   - Verify no lag when switching workspaces
   - Verify no memory leaks (leave running 5 min)

### Edge Cases
- [ ] Rapidly switch between workspaces
- [ ] Upload large SVG file
- [ ] Change settings while print running
- [ ] Refresh page mid-operation
- [ ] Verify error messages appear correctly

---

## Risk Mitigation

### High-Risk Areas
1. **Work workspace (core workflow)**
   - **Risk:** Production workflow must work perfectly
   - **Mitigation:** Test every button, every state transition
   - **Rollback:** Keep original gui_service.py as `gui_service.py.bak`

2. **State management**
   - **Risk:** Immutable state requires different mental model
   - **Mitigation:** Start simple, expand gradually
   - **Fallback:** Can revert to mutable state if needed

3. **Workspace persistence**
   - **Risk:** Saving/loading workspace selection might break
   - **Mitigation:** Test persistence explicitly
   - **Fallback:** Clear runtime store and reload

### Testing Checklist
- [ ] All 175 tests passing
- [ ] Manual GUI tests passed (all workspaces)
- [ ] No console errors in browser dev tools
- [ ] No memory leaks (watched for 5 minutes)
- [ ] Performance not degraded (GUI loads in <2s)
- [ ] All error messages display correctly
- [ ] Backwards compatible (if old settings exist, still loads)

---

## Success Criteria

✅ All 175 tests passing  
✅ GUI renders correctly in all 5 workspaces  
✅ All buttons responsive and working  
✅ Settings persist across workspace switches  
✅ `gui_service.py` reduced from 1,231 LOC to ~300 LOC  
✅ `build_page()` reduced from 1,100 LOC to ~50 LOC  
✅ No breaking changes (backwards compatible)  
✅ Code formatted and type-checked  
✅ All edge cases tested manually  
✅ Completion report created  

---

## Phase 2 → Phase 3 Transition

Once Phase 2 complete, Phase 3 will:
- **Extract state consolidation** (single SystemState source of truth)
- **Create immutable state flows** (state transitions explicit)
- **Refactor service architecture** (clear dependency tiers)
- **Move thermal printer** to independent service

---

## Rollback Plan

If any critical issue found:

1. **Full rollback:**
   ```bash
   git revert HEAD~3..HEAD  # Revert all Phase 2 commits
   uv run pytest -q        # Verify tests pass
   git checkout <old-branch>  # Or manual git operations
   ```

2. **Partial rollback:**
   - Can revert individual workspace if one is broken
   - Keep others as refactored

3. **Recovery:**
   - Original code still in git history
   - Archive files backed up
   - Can always go back to working state

---

## Resource Estimation

| Task | Duration | Effort |
|------|----------|--------|
| 2.1: Component Library | 2-3h | ~½ day |
| 2.2: State Model | 1-2h | ~¼ day |
| 2.3: Extract Handlers | 3-4h | ~½-¾ day |
| 2.4: Workspace Router | 1-2h | ~¼ day |
| 2.5: Connection WS | 2-3h | ~½ day |
| 2.6: Calibration WS | 2-3h | ~½ day |
| 2.7: Tests WS | 2h | ~¼ day |
| 2.8: Work WS (core) | 3-4h | ~¾ day |
| 2.9: Exhibition WS | 2h | ~¼ day |
| 2.10: Test Suite | 0.5h | ~15 min |
| 2.11: Integration Test 1 | 0.5h | ~30 min |
| 2.12: Integration Test 2 | 0.75h | ~45 min |
| 2.13: Code Quality | 1-2h | ~¼-½ day |
| 2.14: Completion Report | 1h | ~¼ day |
| **TOTAL** | **~27-34h** | **~3-4 days** |

**For 1 developer:** ~1 week (part-time) or ~4 days (full-time)  
**For 2 developers:** ~2-3 days (parallel work on workspaces)

---

## Next Phase (Phase 3)

Once Phase 2 complete:
- **State Model Consolidation** (weeks 2)
- **Service Architecture** (weeks 1)
- **Independent Thermal Service** (days 2)
- **Circular Dependency Cleanup** (days 2)

---

## Success Metrics

### Code Metrics
- ✅ LOC: 1,231 → ~800 (35% reduction)
- ✅ Cyclomatic complexity: Significant reduction
- ✅ Module cohesion: High (each workspace is self-contained)
- ✅ Coupling: Low (workspace independent)

### Quality Metrics
- ✅ Test passing: 175/175 (no regression)
- ✅ Type checking: All functions typed
- ✅ Code coverage: Same as before
- ✅ Performance: Same or better (component reuse)

### Maintainability Metrics
- ✅ Time to add feature: Shorter (add to workspace)
- ✅ Time to debug: Shorter (isolated workspace)
- ✅ Onboarding time: Reduced (clear structure)

---

**Status:** Ready to execute  
**Start Date:** 2026-05-27 (after Phase 1 verification)  
**Expected Completion:** 2026-06-09 (2-week target)
