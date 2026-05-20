# 📘 Action Plan: NejeDraw Codebase Modernization

## 📌 Phase 1: Critical Debt Resolution (2-3 weeks)
### 📑 Chapter 1: Mypy Error Elimination
**Objective:** Resolve 62 mypy errors across 8 files

**Steps:**
1. Prioritize `gui_service.py` (28% of total mypy errors)
   - [ ] Run `mypy src/neje_oracle/gui_service.py` and categorize errors
   - [ ] Create fix matrix: Type hints (40%), Type Guards (30%), Type Narrowing (20%), Other (10%)
   - [ ] Implement fixes with type annotations and stubs

2. Address remaining errors in:
   - `supervisor.py` (10 BLE001)
   - `plotter_daemon.py` (6 BLE001)
   - `session_generator.py` (no tests)

**Microtasks:**
- [ ] Create mypy error tracking spreadsheet
- [ ] Implement type narrowing in `supervisor.py`
- [ ] Add type guards to `plotter_daemon.py`

### 📑 Chapter 2: BLE001 Cleanup
**Objective:** Eliminate 37 broad-except warnings

**Steps:**
1. Focus on high-risk files:
   - [ ] `supervisor.py` (10 occurrences)
   - [ ] `plotter_daemon.py` (6 occurrences)
   - [ ] `preflight.py` (4 occurrences)

2. Implement:
   - [ ] Specific exception handling
   - [ ] Add typing for exception types
   - [ ] Create exception mapping documentation

**Microtasks:**
- [ ] Create BLE001 tracking matrix
- [ ] Add exception typing to `supervisor.py`
- [ ] Implement specific handlers for `plotter_daemon.py`

---

## 📌 Phase 2: Documentation Revival (1-2 weeks)
### 📑 Chapter 1: Public API Documentation
**Objective:** Achieve 100% docstring coverage for public API

**Steps:**
1. Focus on:
   - [ ] `models.py` (586 LOC, 0% coverage)
   - [ ] `config.py` (161 LOC, 0% coverage)
   - [ ] `firebase_io.py` (482 LOC, 0% coverage)

2. Implement:
   - [ ] Google-style docstrings
   - [ ] Parameter/return value documentation
   - [ ] Example usage blocks

**Microtasks:**
- [ ] Create docstring template
- [ ] Document `models.py` classes
- [ ] Add parameter docs to `config.py`

### 📑 Chapter 2: Test Coverage Expansion
**Objective:** Achieve 100% test coverage

**Steps:**
1. Target new files:
   - [ ] `firebase_svg_normalizer.py`
   - [ ] `gui_modes.py`

2. Expand coverage for:
   - [ ] `plotter_service.py`
   - [ ] `uploader_service.py`

**Microtasks:**
- [ ] Create test templates
- [ ] Implement unit tests for `firebase_svg_normalizer.py`
- [ ] Add integration tests for `gui_modes.py`

---

## 📌 Phase 3: Code Quality Enhancement (Ongoing)
### 📑 Chapter 1: Cyclomatic Complexity Reduction
**Objective:** Reduce complexity in high-risk files

**Steps:**
1. Target:
   - [ ] `heatmap.svg_normalizer.py` (CC=19)
   - [ ] `preflight.py` (CC=17)
   - [ ] `svg_gcode.py` (CC=14)

2. Implement:
   - [ ] Extract complex functions
   - [ ] Add complexity guards
   - [ ] Create complexity baseline metrics

**Microtasks:**
- [ ] Create complexity mapping
- [ ] Refactor `heatmap.svg_normalizer.py`
- [ ] Implement guards in `preflight.py`

### 📑 Chapter 2: CI/CD Integration
**Objective:** Automate quality checks

**Steps:**
1. Implement:
   - [ ] GitHub Actions for mypy
   - [ ] GitHub Actions for BLE001
   - [ ] GitHub Actions for complexity checks

2. Set up:
   - [ ] Pre-commit hooks
   - [ ] Code coverage threshold rules
   - [ ] Linter auto-fix rules

**Microtasks:**
- [ ] Create GitHub Actions workflow
- [ ] Configure pre-commit hooks
- [ ] Set coverage thresholds

---

## 📌 Phase 4: Knowledge Transfer (1 week)
### 📑 Chapter 1: Documentation Systematization
**Objective:** Create sustainable documentation practices

**Steps:**
1. Implement:
   - [ ] Docstring template standard
   - [ ] API reference documentation
   - [ ] Architecture documentation

2. Set up:
   - [ ] Documentation review process
   - [ ] Documentation quality metrics
   - [ ] Documentation CI checks

**Microtasks:**
- [ ] Create documentation template
- [ ] Write architecture overview
- [ ] Implement docstring reviews

### 📑 Chapter 2: Team Onboarding
**Objective:** Ensure sustainable maintenance

**Steps:**
1. Create:
   - [ ] Development guidelines
   - [ ] Contribution workflow
   - [ ] Code ownership matrix

2. Implement:
   - [ ] Code review standards
   - [ ] Pair programming protocols
   - [ ] Code health metrics dashboard

**Microtasks:**
- [ ] Create development guidelines
- [ ] Set up code ownership matrix
- [ ] Implement review standards

---

## 📌 Phase 5: Final Validation
### 📑 Chapter 1: Quality Assurance
**Objective:** Verify all improvements

**Steps:**
1. Run:
   - [ ] Full mypy check
   - [ ] Full test suite
   - [ ] Complexity analysis
   - [ ] Code coverage check

2. Validate:
   - [ ] Docstring coverage
   - [ ] BLE001 compliance
   - [ ] CI/CD pipeline health

**Microtasks:**
- [ ] Run final mypy scan
- [ ] Execute full test suite
- [ ] Validate documentation coverage

### 📑 Chapter 2: Post-Audit Review
**Objective:** Ensure long-term sustainability

**Steps:**
1. Create:
   - [ ] Audit review process
   - [ ] Debt tracking system
   - [ ] Quality metrics dashboard

2. Set up:
   - [ ] Monthly audit cycles
   - [ ] Debt reduction targets
   - [ ] Quality improvement KPIs

**Microtasks:**
- [ ] Create audit review process
- [ ] Set debt tracking system
- [ ] Implement monthly audit cycles

---

## 📊 Final Metrics Tracking
| Metric             | Target | Tracking Method      |
|--------------------|--------|----------------------|
| Mypy Errors        | 0      | GitHub Actions       |
| BLE001             | 0      | GitHub Actions       |
| Docstring Coverage | 100%   | GitHub Actions       |
| Test Coverage      | 100%   | Coverage reports     |
| Complexity         | <10    | SonarQube metrics    |
| Debt Reduction     | 90%    | Debt tracking system |
Would you like me to export this plan to a file or generate a Gantt chart for visualization?
