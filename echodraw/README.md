> Imported from [berlogabob/echodraw-project](https://github.com/berlogabob/echodraw-project) on 2026-08-03 (curated: text, configs, designs). Photo archives and vendored p5.js libraries, plus the original repo's `.github/`, `flutter-app/`, and `docs/reports/` scaffolding, remain in the original repo and were not carried into this curated subset.

What actually lives here:

```
echodraw/
├── bom/                    # Bill of materials
├── docs/
│   └── explanatory-note.md # Original project explanatory note (Andrey Dyakov, 2026-01)
├── hardware/                # Module 1: NEJE -> FluidNC plotter conversion
│   ├── README.md            # Machine spec, board/component table
│   ├── GEOMETRY.md           # Single source of truth for machine dimensions
│   └── configs/config.yaml   # FluidNC config (TMC2209, travel limits)
└── generative-core/          # Module 2: p5.js pattern generator
    ├── README.md              # Link to the author's p5.js editor collection
    ├── generators/             # Standalone generator sketches (e.g. 01_Circles.js)
    └── web/                    # Live sketch served by the operator GUI's "6 GENERATIVE" tab
        ├── index.html
        └── sketch.js            # Pattern-generator library — see root README
```

Module 3 (Flutter wrapper) is covered by `public_gallery/` in the repo root, not by an `echodraw/flutter-app/` folder.
