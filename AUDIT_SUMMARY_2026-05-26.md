# NejeDraw/Oracle Project Audit - Executive Summary

**Audit Date:** 2026-05-26  
**Auditor:** Senior Developer  
**Status:** Over-engineered, over-complicated, multiple waves of cruft accumulation  
**Risk Level:** MEDIUM (for exhibition operations)

---

## The Problem in One Sentence

**The project has grown through 6+ waves of development without consolidation, resulting in:** duplicate entry points, monolithic GUI (1,457 lines), fragmented state, orphaned subprocess management, and unclear architecture that makes changes dangerous and debugging hard.

---

## By The Numbers

| Metric | Value | Assessment |
|--------|-------|-----------|
| Python modules | 27 | OK (but some should merge) |
| Total Python LOC | 10,851 | OK (but monoliths inflate this) |
| Largest module | `gui_service.py` - 1,457 LOC | **TOO BIG** |
| Biggest function | `build_page()` - ~1,100 LOC | **UNACCEPTABLE** |
| Entry points defined | 7 | **TOO MANY** (should be 3) |
| Duplicate services | 2+ (uploader, plotter) | **REMOVE** |
| Test coverage | 193 tests passing | ✅ Good |
| Architecture layers | Unclear/mixed | **NEEDS CLARITY** |
| State sources | 4+ (SQLite, memory, Firebase, GUI) | **TOO MANY** |

---

## Top 5 Problems

### 1. **Monolithic GUI Service** 🚨 CRITICAL
- 1,457 lines, all logic in one `build_page()` function
- Unmaintainable, untestable, high risk for changes
- Business logic tightly coupled to NiceGUI framework
- Single bug in one workspace crashes entire GUI

### 2. **Duplicate Entry Points** 🔴 HIGH
- `niej-uploader` and `niej-uploader-agent` do same thing
- `niej-plotter` may be unused (unclear)
- Operators confused which to run
- Maintenance burden (duplicated code)

### 3. **GUI Manages Thermal Printer Subprocess** 🔴 HIGH
- GUI spawns thermal autoprint as external process
- Uses global variable to track PID
- Polls filesystem to detect crashes
- Process orphans if GUI crashes

### 4. **State Fragmentation** 🟡 MEDIUM
- State split between: SQLite, in-memory objects, Firebase, GUI runtime
- No single source of truth
- Race conditions possible
- Hard to reason about system state

### 5. **Unclear Architecture** 🟡 MEDIUM
- Mixed patterns: simple loops, FastAPI wrappers, daemons, synchronous/async
- Dependencies are circular and unclear
- Services have conflicting responsibilities
- New developers can't understand the design

---

## Recommended Roadmap

### Week 1: Quick Wins (Low Risk)
- Delete duplicate entry points
- Consolidate launchers
- Clean repository root
- Update `.gitignore`
- Add role-based access control

### Weeks 2-7: Architectural Refactoring (Medium Risk)
- Break GUI monolith into components
- Consolidate state management
- Establish service architecture
- Clear dependency tiers

### Week 8: Documentation
- Complete operator runbook
- Improve test organization
- Create architecture guides

---

## Bottom Line

**The project works, but is over-engineered and hard to maintain.** This can be fixed incrementally without breaking exhibition operations. The quick wins alone (1-2 days of work) will eliminate operator confusion and reduce the most obvious duplication.

**Recommendation:** Start with Phase 1 quick wins this week.
