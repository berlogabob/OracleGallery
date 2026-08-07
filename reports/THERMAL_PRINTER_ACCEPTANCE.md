# Thermal Printer Acceptance Report

Date: 2026-05-20

## Scope

Implemented the physical thermal receipt path (original plan superseded; see git history) for the ESP32 printer bridge and Mac GUI workflow.

## Current Receipt Contract

- `receipt_title`: `ORACLE`
- `subtitle`: `THE ORACLE THAT WEARS US`
- `symbol_label`: normalized uppercase display name
- `qr_required`: `true`
- `persona_image_allowed`: `false`
- `session_url`: required public route, used as QR source
- `symbol_escpos_base64`: simplified symbol fallback for ESC/POS
- `qr_escpos_base64`: raster QR fallback for ESC/POS
- `receipt_raster_rle_base64`: compact full receipt raster for iLabel/WP9509
- `ilabel_width_dots` / `ilabel_height_dots`: raster dimensions

## Generated Artifacts

- Preview PNG: `reports/thermal_acceptance_preview.png`
- Dry-run JSON payload: `reports/thermal_acceptance_payload.json`

Reference session used:

```text
assets/sessions/20260518_154452
```

## Verification Completed

- Python receipt tests pass:

```text
uv run pytest tests/test_thermal_receipt.py
3 passed
```

- Firmware compile passes:

```text
arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly
Sketch uses 1248680 bytes (95%) of program storage space.
```

- CLI dry-run builds QR-required payload and preview:

```text
uv run python ESP32-BTN_Printer/tools/printer_connect.py receipt assets/sessions/20260518_154452 --dry-run --preview-png /tmp/oracle_connect_preview.png
```

## Manual Print Steps

Use the ESP32 URL shown by the hotspot:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py receipt \
  assets/sessions/20260518_154452 \
  --protocol ilabel \
  --esp32 http://<esp32-ip>
```

Acceptance criteria for the physical receipt:

- Contains `ORACLE`
- Contains session ID
- Contains symbol image and symbol name
- Contains oracle output text
- Contains intensity, instability, confidence
- Contains themes
- Contains QR code
- QR opens `https://berlogabob.github.io/OracleGallery/#/session/20260518_154452`

## Notes

- Gap-label mode remains disabled for roll paper.
- Printer offline status is treated as a warning in the GUI and does not block Firebase upload or plotter workflow.
- iLabel receipts no longer use text-only printing; they require the full raster payload so QR output is preserved.
