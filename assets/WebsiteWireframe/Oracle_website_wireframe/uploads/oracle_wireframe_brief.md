# Oracle Website — Wireframe Brief
**For: Claude Design**
**Version: 1.0 · April 30, 2026**
**Project: The Oracle That Wears Us · IADE M-CCIA**

---

## How to use this document

This brief defines the structure and content of the Oracle website across five pages. Use it alongside `oracle_design_system.html`, which is the visual authority for all colour, typography, spacing, and component decisions.

**Your task:** Produce a mid-fidelity wireframe for all five pages. Follow the structure defined here precisely — do not add, remove, or rename pages or sections.

---

## Wireframe requirements

- **Fidelity:** Mid-fidelity. Grey boxes for images. Real labels for all text elements. Annotate content sources where specified.
- **Pages:** All five pages shown.
- **Navigation:** Persistent nav shown on every page.
- **Mobile:** Show mobile layout for The Cloth page only — this is the page most visited on phone (QR code destination).
- **Annotations:** Annotate the two-layer cloth viewer clearly (see Page 2). Annotate content sources throughout (e.g. "text from oracle_narrative.html Chapter I").
- **Motion:** Do not apply motion or animation — static wireframe only.
- **Tone:** Ritual, archaic, restrained. Nothing should feel like a generic portfolio or tech product.

---

## Design system reference

The visual design system is in `oracle_design_system.html`. Reference it for all visual decisions. Do not invent colours, fonts, spacing, or components.

**Two registers:**
- **Document register** — cream `#f7f4ef` background, charcoal text. Default for all pages.
- **Installation register** — void `#0a0a12` background, gold `#c9a84c` accents. Used for hero sections and the cloth viewer only.

**Fonts:**
- `Cinzel Decorative` — logo only ("ORACLE"). Never in body or labels.
- `Cinzel` — all labels, headings, navigation, buttons.
- `EB Garamond` — all body text, captions, oracle readings.

---

## Navigation (persistent, all pages)

| Element | Detail |
|---|---|
| Logo | "ORACLE" — Cinzel Decorative, small, left-aligned |
| Links | Home · The Cloth · The Marks · About · Team |
| Register | Document (cream background) |
| Mobile | All four links visible — no hamburger needed |

---

## Page 1 — Home `/`

### Section 1: Hero
- Full-bleed void background
- Oracle portrait image (gold liquid figure), centred
- Project name: "THE ORACLE THAT WEARS US" in Cinzel below portrait
- All eight mark SVGs cycling in slow fade rotation beneath the title — no labels, no identification. Intrigue only.

### Section 2: Session lookup
*Most important interaction on the page. Place immediately below hero.*

- Label: **"Find your mark"**
- Single text input: `Enter your session ID`
- Submit button: "Find" — primary button style (void background, gold border, Cinzel)
- On submit: navigates to `/cloth?session=[id]`
- Supporting line beneath input: *"Your session ID is printed on your receipt."*

### Section 3: What the oracle is
- Register: cream (document)
- Three paragraphs — source: `oracle_narrative.html` Chapter I
- No images

### Section 4: The cloth preview
- Register: void (installation)
- Small static or live preview of the collective cloth
- Live mark count: `"47 marks drawn"` — sourced from Firebase
- CTA: "View the cloth →" — primary button

---

## Page 2 — The Cloth `/cloth`

*Primary destination for receipt visitors via QR code. Must work well on mobile.*

### Section 1: Session lookup
*Repeated here — visitors may arrive directly on this page.*

- Same component as home page
- Supporting text below input: *"No receipt? Browse The Marks to find yours."* — link to `/marks`

### Section 2: Live cloth viewer
- Full-width canvas or SVG element
- Void register
- Shows all marks in sequence, arranged left-to-right, top-to-bottom, matching physical fabric layout

**Two data layers — annotate clearly in wireframe:**

| Layer | Source | Behaviour |
|---|---|---|
| Background marks | Pre-generated SVG pool (static assets) | Visual texture only. Not queryable. Visitor never knows these are not real sessions. |
| Real session marks | Firebase (live) | Respond to session ID lookup. Highlighted on match. |

**On session found:**
- Visitor's mark highlights in gold
- All other marks dim slightly
- Viewer scrolls to mark position
- Mark name and oracle reading appear alongside the highlighted mark
- Share prompt appears: "Share your mark" — generates shareable image (mark SVG + name on void background)

**Mobile layout:** Cloth viewer is scrollable and pinch-zoomable. Single column. Session lookup stays above viewer.

### Section 3: About the cloth
- Register: cream (document)
- Two paragraphs — source: `oracle_narrative.html` Chapter V, first two paragraphs
- Positioned below the viewer

---

## Page 3 — The Marks `/marks`

### Section 1: Framing
- One sentence — source: `oracle_narrative.html` Chapter IV, first sentence of opening paragraph
  > *"These signs were once used by itinerant workers to leave messages for those who came after — the oracle has learned to read them differently."*
- Failsafe note immediately below:
  > *"Didn't receive your receipt? Browse the eight marks below to find yours."*

### Section 2: Eight mark cards
- Full grid — all eight marks
- Register: each card has void left panel (SVG) and cream right panel (text)

**Each card contains:**

| Element | Detail | Source |
|---|---|---|
| SVG | Mark drawn large on void background | `oracle_narrative.html` Ch. IV |
| Emotion label | Small, rust, Cinzel, letter-spaced | `oracle_narrative.html` Ch. IV |
| Mark name | Gold, Cinzel | `oracle_narrative.html` Ch. IV |
| Description | Body paragraph | `oracle_narrative.html` Ch. IV |
| Oracle reading | *"The oracle heard..."* — italic, EB Garamond | `oracle_narrative.html` Ch. IV |

*Copy all content exactly from source. Do not rewrite.*

### Section 3: AI transparency note
- Short paragraph — source: `oracle_website_brief.html` Section 02, The Marks page copy block
- Plain language. No jargon.
- Register: cream, below the eight cards

---

## Page 4 — About `/about`

### Section 1: The project
- One paragraph: what Oracle is, course context, when and where it was shown
- Factual, not promotional
- *Andrey or team to write this paragraph — it is the only copy on the site not pre-written*

### Section 2: Video
- Embedded video player placeholder
- Label in wireframe: `[Dmitrii's video — embed here]`
- Full width or centred, cream register

### Section 3: How it works
- Plain language technical overview — one sentence per step
- Source: `oracle_website_brief.html` About page copy block
- AI systems named: Vosk · Ollama · RAVDESS · ONNX · KittenTTS

### Section 4: Making-of *(Phase 2 — not needed for launch)*
- Photo/video grid placeholder
- Label in wireframe: `[Phase 2 — not required for May 20 launch]`

---

## Page 5 — Team `/team`

- Three entries — one per team member
- Register: cream (document)
- Simple layout — no complex components needed

**Each entry:**

| Element | Detail |
|---|---|
| Photo | Placeholder box — include only if high-quality image available. Omit if not. |
| Name | Cinzel, small heading |
| Role | EB Garamond italic, one line |
| Bio | 4–6 sentences, EB Garamond body |

---

## Content sources — summary

| Content | Source document | Location |
|---|---|---|
| What the oracle is | `oracle_narrative.html` | Chapter I, all four paragraphs |
| The exchange steps | `oracle_narrative.html` | Chapter II, all six steps |
| Each mark description + oracle reading | `oracle_narrative.html` | Chapter IV, all eight cards |
| About the cloth | `oracle_narrative.html` | Chapter V, first two paragraphs |
| Hobo framing sentence | `oracle_narrative.html` | Chapter IV, first sentence |
| AI transparency note | `oracle_website_brief.html` | Section 02, The Marks copy block |
| How it works | `oracle_website_brief.html` | Section 02, About copy block |
| Project description paragraph | Written by team | About page only |
| Team bios | Written by team | Team page |

*All other copy is pre-written. Do not rewrite or paraphrase.*

---

## Build priorities

| Phase | Pages | Target | Notes |
|---|---|---|---|
| 1 | Home (no session lookup yet) · The Marks · About · Team | May 10 | Static. No Firebase. |
| 2 | The Cloth — static cloth view | May 14 | SVGs displayed, no live updates yet |
| 3 | Firebase integration · Session lookup · Live cloth | May 20 | Full feature |
| 4 | Social sharing · QR deep link | May 20 | Share card + `/cloth?session=[id]` |

*If Phase 3 is not ready before installation opens: point QR code to `/marks` temporarily. Update when Phase 3 is live.*

---

*Read alongside `oracle_design_system.html` and `oracle_narrative.html`*
*Oracle · The Oracle That Wears Us · IADE M-CCIA · 2026*
