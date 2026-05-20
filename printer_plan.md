# Hermes Plan: Thermal Printer Receipt

Status: implemented 2026-05-20. See `reports/THERMAL_PRINTER_ACCEPTANCE.md`, `reports/thermal_acceptance_preview.png`, and `reports/thermal_acceptance_payload.json`.

## Summary
- Build a simplified physical receipt for the thermal printer based on the current digital receipt design.
- Do not print the persona image.
- Mandatory receipt content:
  - `ORACLE`
  - Session ID
  - Symbol image/mark and symbol name
  - Oracle output text
  - System measured values
  - Themes
  - QR code to the public session route
- Thermal design must be black-on-white, high contrast, narrow width, short text blocks, and reliable on low-resolution paper.

## Hermes / Goose Orchestration
- Hermes should run goose tasks in this order:
  1. `thermal-receipt-data-contract`
  2. `thermal-receipt-renderer`
  3. `esp32-printer-bridge-update`
  4. `macbook-gui-print-action`
  5. `thermal-receipt-tests`
  6. `manual-printer-acceptance-report`
- Goose must work inside `/Users/berloga/Documents/GitHub/NejeDraw`.
- Goose must not revert existing dirty work. Inspect first, then patch narrowly.
- Main files to inspect first:
  - `ESP32-BTN_Printer/tools/send_receipt.py`
  - `ESP32-BTN_Printer/tools/printer_connect.py`
  - `ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
  - `src/neje_oracle/session_uploader.py`
  - `public_gallery/lib/pages/session_receipt_page.dart`

## Key Changes
- Receipt data contract:
  - Keep existing payload fields: `session_id`, `mark_name`, `oracle_text`, `themes`, `measures`, `session_url`.
  - Add explicit thermal fields:
    - `receipt_title`: `ORACLE`
    - `subtitle`: `THE ORACLE THAT WEARS US`
    - `symbol_label`: normalized display name, for example `THE HORIZON`
    - `qr_required`: `true`
    - `persona_image_allowed`: `false`
  - QR source must be `session_url`, not a local-only debug route.

- Thermal layout:
  - Width defaults:
    - `384 dots` for 58mm ESC/POS printers.
    - `576 dots` for iLabel-style printers when configured.
  - Print order:
    1. Centered `ORACLE`
    2. Small subtitle
    3. Session ID
    4. Simplified symbol bitmap
    5. Symbol name
    6. Section: `WHAT THE ORACLE PERCEIVED`
    7. Wrapped oracle text
    8. Section: `WHAT THE SYSTEM MEASURED`
    9. `intensity`, `instability`, `confidence`
    10. Section: `THEMES`
    11. Theme words
    12. Section: `VIEW YOUR MARK ONLINE`
    13. QR code
    14. Session ID repeated below QR
  - Use ASCII-safe typography for printer output. No gold/dark background, no serif dependency, no persona portrait.

- Renderer approach:
  - Add a Python thermal receipt renderer that can produce:
    - structured JSON payload for ESP32
    - preview PNG for local debugging
    - raster bytes/base64 for printers that cannot handle native QR reliably
  - Use the existing session folder assets:
    - `<session_id>_receipt.txt`
    - optional `<session_id>_receipt.csv`
    - `<session_id>_plotter.svg`
    - optional `<session_id>_qr.png`
  - If local QR PNG is missing, generate QR from `session_url`.

- ESP32 bridge:
  - Make QR mandatory for `/print`.
  - For `escpos`, allow either native QR or raster QR, but fallback to raster if native QR fails.
  - For `ilabel`, print a full monochrome raster receipt or raster QR block because current `sendIlabelText(...)` cannot guarantee QR output.
  - Keep `/test-print`, `/probe-print`, and `/status` unchanged.

- MacBook GUI integration:
  - Add a thermal printer panel in Work or Exhibition tab:
    - Discover ESP32 printer bridge
    - Connect printer
    - Print latest session receipt
    - Print selected session receipt
    - Print test receipt
  - Do not block Firebase upload or plotter workflow if printer is offline; show printer status as warning only.

## Test Plan
- Python tests:
  - Build thermal payload from a real session folder.
  - Assert persona image is never included.
  - Assert QR/session URL is always present.
  - Assert long oracle text wraps cleanly.
  - Assert missing measures/themes degrade gracefully.
  - Assert symbol rendering works from `<session_id>_plotter.svg`.

- Firmware/helper tests:
  - `printer_connect.py receipt --dry-run` returns payload with QR-required fields.
  - ESP32 `/print` rejects payloads with no `session_url`.
  - ESC/POS receipt path includes QR section.
  - iLabel receipt path does not use text-only printing for QR receipts.

- Manual acceptance:
  - Use latest real session folder.
  - Run dry preview PNG and inspect readability.
  - Send to ESP32 printer bridge.
  - Confirm printed receipt contains ORACLE, session ID, symbol/name, oracle text, measures, themes, and scannable QR.
  - Scan QR and confirm it opens the public digital receipt.

## Assumptions
- Thermal paper output should be a simplified physical companion to the digital receipt, not a full visual copy.
- Persona image is intentionally skipped for printer reliability.
- QR code is mandatory and must work even if the printer protocol cannot print native QR commands.
- ESC/POS and iLabel-style printers may both remain supported, but the receipt design must be identical in content.
