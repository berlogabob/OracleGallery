# Knowledge Graph Edge Audit: LLM-Inferred Relationships

**Date:** 2026-08-04

**Purpose:** Verification of LLM-inferred edges in the knowledge graph targeting three classes: `GuiSettings`, `SupervisorService`, and `FluidNCTransport`. This audit confirms whether the inferred relationships genuinely exist in the codebase by examining actual usage patterns and code references.

**Graph Source:** `graphify-out/graph.json`

---

## Edge Verification Table

| # | Edge | Relation | Verdict | Evidence (file:line) |
|---|------|----------|---------|----------------------|
| 1 | SupervisorService → SystemCheckService | uses | CORRECT | src/neje_oracle/app/supervisor.py:40 (import); :162-171 (instantiation and method calls) |
| 2 | BusyTransport → SupervisorService | uses | WRONG | Tests define BusyTransport as mock; passed TO supervisor, not used BY it. tests/test_supervisor.py:196 |
| 3 | DryTransport → SupervisorService | uses | WRONG | Tests define DryTransport as mock; passed TO supervisor, not used BY it. tests/test_supervisor.py:196 |
| 4 | EmptyRemote → SupervisorService | uses | WRONG | Tests define EmptyRemote as mock; passed TO supervisor, not used BY it. tests/test_supervisor.py:195 |
| 5 | HomeReconnectTransport → SupervisorService | uses | WRONG | Tests define HomeReconnectTransport as mock; passed TO supervisor, not used BY it. tests/test_supervisor.py:196 |
| 6 | HomingDisabledTransport → SupervisorService | uses | WRONG | Tests define HomingDisabledTransport as mock; passed TO supervisor, not used BY it. tests/test_supervisor.py:196 |
| 7 | InvalidConfigUnlockTransport → SupervisorService | uses | WRONG | Tests define InvalidConfigUnlockTransport as mock; passed TO supervisor, not used BY it. tests/test_supervisor.py:196 |
| 8 | FakeRemoteRepository → FluidNCTransport | uses | WRONG | FakeRemoteRepository is a test mock for remote job queuing, unrelated to FluidNCTransport. tests/test_plotter_daemon.py:32-59 |
| 9 | FakeCharCountServer → FluidNCTransport | uses | WRONG | FakeCharCountServer is a fake TCP server for testing; FluidNC connects TO it, not vice versa. tests/test_transport.py:140-171 |
| 10 | FakeFluidNCServer → FluidNCTransport | uses | WRONG | FakeFluidNCServer is a fake TCP server for testing; FluidNC connects TO it, not vice versa. tests/test_transport.py:21-139 |
| 11 | BusyTransport → GuiSettings | uses | WRONG | BusyTransport takes PlotterSettings, not GuiSettings. GuiSettings passed TO supervisor, not used by mocks. tests/test_supervisor.py:39-41 |
| 12 | DryTransport → GuiSettings | uses | WRONG | DryTransport takes PlotterSettings, not GuiSettings. GuiSettings passed TO supervisor, not used by mocks. tests/test_supervisor.py:39-41 |
| 13 | EmptyRemote → GuiSettings | uses | WRONG | EmptyRemote is a mock with no dependencies on GuiSettings. tests/test_supervisor.py:26-35 |
| 14 | HomeReconnectTransport → GuiSettings | uses | WRONG | HomeReconnectTransport is a mock taking PlotterSettings only. tests/test_supervisor.py:97-115 |
| 15 | HomingDisabledTransport → GuiSettings | uses | WRONG | HomingDisabledTransport is a mock taking PlotterSettings only. tests/test_supervisor.py:135-139 |
| 16 | InvalidConfigUnlockTransport → GuiSettings | uses | WRONG | InvalidConfigUnlockTransport is a mock taking PlotterSettings only. tests/test_supervisor.py:129-132 |

---

## Summary

- **CORRECT:** 1 edge (6%)
- **PARTIALLY:** 0 edges (0%)
- **WRONG:** 15 edges (94%)

**Total edges audited:** 16

### Key Finding

The inferred edges are heavily weighted toward test mock classes and incorrectly model their data dependencies. In reality:
- All `*Transport` mocks are **passed TO** `SupervisorService` as factory parameters, not used by it (inverse relationship).
- All `Fake*` server classes are **TCP servers that accept connections FROM** `FluidNCTransport`, not the other way around.
- `GuiSettings` is passed **TO** `SupervisorService` methods as a parameter; mock transport classes never interact with it directly.
- The single correct edge (`SupervisorService` → `SystemCheckService`) reflects a genuine composition pattern: supervisor instantiates and delegates system checks to this service.
