> Imported from [berlogabob/echodraw-project](https://github.com/berlogabob/echodraw-project) on 2026-08-03 (curated: text, configs, designs). Photo archives and vendored p5.js libraries remain in the original repo.

```
EchoDraw/
├── .github/                # CI/CD and templates
│   └── workflows/          # GitHub Actions YAML files for testing
│       └── ci.yml          # Example: build for Flutter, lint for p5.js
├── docs/                   # Documentation and reports module
│   ├── README.md           # Overview of docs: how to generate reports
│   ├── reports/            # Reports: progress logs, specifications
│   │   └── stage1-report.md # Example: Report for stage 1
│   ├── bom/                # Bill of Materials (CSV/Excel for components)
│   │   └── hardware-bom.csv
│   └── images/             # Screenshots and diagrams for documentation
├── hardware/               # Module 1: Hardware component
│   ├── README.md           # Instructions: assembly, NEJE pinout
│   ├── configs/            # YAML files for FluidNC
│   │   └── config.yaml     # Basic config for TMC2209
│   ├── designs/            # 3D models (STL, CAD from Fusion360/Tinkercad)
│   │   └── pen-holder.stl  # Holder for single pen
│   ├── firmware/           # Custom firmware (if needed)
│   └── tests/              # G-code examples for testing
│       └── test-line.gcode
├── generative-core/        # Module 2: p5.js + ml5.js
│   ├── README.md           # How to run: npm install, etc.
│   ├── src/                # Code: sketches, libraries
│   │   ├── index.html      # Basic p5.js canvas
│   │   ├── sketch.js       # Pattern generator (stage 1)
│   │   └── ml-integration.js # ml5.js integration for handpose
│   ├── examples/           # Pattern examples (SVG/G-code)
│   └── package.json        # Dependencies (p5, ml5)
├── flutter-app/            # Module 3: Flutter wrapper
│   ├── README.md           # Flutter setup: flutter pub get
│   ├── lib/                # Code: main.dart, screens
│   │   └── main.dart       # Basic app (stage 1)
│   ├── assets/             # Icons, images
│   └── pubspec.yaml        # Flutter dependencies
├── .gitignore              # Ignore: build/, .DS_Store, etc.
├── LICENSE                 # MIT license text
├── README.md               # Main: Project overview, structure, how to run
└── CONTRIBUTING.md         # Contribution guidelines (for the team)
```
