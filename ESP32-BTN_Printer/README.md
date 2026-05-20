# ESP32 Button + Thermal Receipt Printer

Arduino IDE firmware for the Oracle installation button and thermal printer bridge.

There are two Arduino sketches:

- `ESP32_BTN_Printer`: button plus TouchDesigner UDP plus printer HTTP endpoints.
- `ESP32_PrinterOnly`: printer-focused HTTP bridge only. Use this while finding the exact print protocol.

Both sketches join the `Nothing32` hotspot and expose printer commands over HTTP. The button sketch also reads a limit switch and sends `START` to TouchDesigner over UDP.

## Hardware

- ESP32 dev board.
- Limit switch or button.
- WP9509 thermal printer.
- Printer and ESP32 powered separately.

Button wiring:

```text
Limit switch COM  -> ESP32 GND
Limit switch NO   -> ESP32 GPIO 27
```

The firmware uses `INPUT_PULLUP`, so no external resistor is required. Pressed reads `LOW`.

## Arduino Libraries

Install these in Arduino IDE Library Manager:

- `ArduinoJson`
- `NimBLE-Arduino`

Use the Espressif ESP32 Arduino board package. Select your ESP32 board and upload from one of these sketch folders:

```text
ESP32-BTN_Printer/PrinterDiscovery/PrinterDiscovery.ino
ESP32-BTN_Printer/ESP32_BTN_Printer/ESP32_BTN_Printer.ino
ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino
```

## Configure

For the combined button/printer sketch, copy the example config:

```bash
cp ESP32-BTN_Printer/ESP32_BTN_Printer/config.example.h ESP32-BTN_Printer/ESP32_BTN_Printer/config.local.h
```

For the printer-only sketch, copy its config instead:

```bash
cp ESP32-BTN_Printer/ESP32_PrinterOnly/config.example.h ESP32-BTN_Printer/ESP32_PrinterOnly/config.local.h
```

Or reuse the already-working local config from the combined sketch:

```bash
cp ESP32-BTN_Printer/ESP32_BTN_Printer/config.local.h ESP32-BTN_Printer/ESP32_PrinterOnly/config.local.h
```

For the combined button/printer sketch, edit the network and button values:

```cpp
#define WIFI_SSID "Nothing32"
#define WIFI_PASSWORD "PUT_THE_HOTSPOT_PASSWORD_HERE"
#define BUTTON_PIN 27
#define TOUCHDESIGNER_UDP_PORT 7000
```

`config.local.h` is ignored by git.

The printer-only config does not contain button or TouchDesigner settings. Its important values are:

```cpp
#define PRINTER_BLE_ADDRESS "95:09:25:47:56:b3"
#define PRINTER_SERVICE_UUID "0000fff0-0000-1000-8000-00805f9b34fb"
#define PRINTER_WRITE_CHAR_UUID "0000fff1-0000-1000-8000-00805f9b34fb"
#define PRINTER_ALT_WRITE_CHAR_UUID "0000fff2-0000-1000-8000-00805f9b34fb"
#define PRINTER_NOTIFY_CHAR_UUID "0000fff4-0000-1000-8000-00805f9b34fb"
#define PRINTER_DEFAULT_PROTOCOL "escpos"
```

## Discover The Printer

1. Turn on the WP9509 and keep it near the ESP32.
2. Upload `PrinterDiscovery.ino`.
3. Open Serial Monitor at `115200`.
4. Copy the printer address, service UUID, and writable characteristic UUID.
5. Put those values in `config.local.h`:

```cpp
#define USE_CLASSIC_SPP 0
#define PRINTER_NAME_PREFIX "9509"
#define PRINTER_BLE_ADDRESS "95:09:25:47:56:b3"
#define PRINTER_SERVICE_UUID "0000fff0-0000-1000-8000-00805f9b34fb"
#define PRINTER_WRITE_CHAR_UUID "0000fff1-0000-1000-8000-00805f9b34fb"
#define PRINTER_ALT_WRITE_CHAR_UUID "0000fff2-0000-1000-8000-00805f9b34fb"
#define PRINTER_NOTIFY_CHAR_UUID "0000fff4-0000-1000-8000-00805f9b34fb"
```

`PrinterDiscovery.ino` connects only to devices whose name or address contains `9509` by default. Your printer was seen as `9509#09509254756B3` at `95:09:25:47:56:b3`. Its BLE print service is `0xfff0`, notify characteristic is `0xfff4`, and writable characteristics are `0xfff1` and `0xfff2`. The main firmware tries `0xfff1` first, can fall back to `0xfff2`, and subscribes to `0xfff4` during protocol probes. If the printer appears as `VSON`, `iLabel`, or another name, edit `DISCOVERY_NAME_FILTER` in that sketch and upload it again. Set it to `""` only when you want to inspect every BLE device found.

If phone testing proves the printer is Bluetooth Classic SPP instead of BLE, set:

```cpp
#define USE_CLASSIC_SPP 1
#define PRINTER_CLASSIC_NAME "WP9509"
#define PRINTER_CLASSIC_MAC "aa:bb:cc:dd:ee:ff"
```

## TouchDesigner

Open the single prepared TouchDesigner project:

```text
ESP32-BTN_Printer/TouchDesigner/TD_BTN.toe
```

It contains an `esp32_bridge` component with both input paths wired:

- `UDP In DAT` on port `7000`, for the firmware's broadcast `START` packet.
- `Serial DAT` on `/dev/cu.usbserial-0001` at `115200`, for the USB-connected ESP32 log line `Button pressed: START`.

Select the active path with `esp32_bridge/source_switch`:

- `wifi = 0`: USB serial only.
- `wifi = 1`: Wi-Fi UDP only.

When the selected input receives `START`, the `esp32_bridge` operator flashes
green and the `status_log` table records the event.

`WAKE_PRINTER_ON_BUTTON` is disabled by default so button presses stay responsive
for TouchDesigner. Printer code is still present; use `/wake`, `/test-print`, or
`/print` when you want the ESP32 to talk to the BLE printer.

If you are rebuilding the network manually, create a `UDP In DAT`:

- Network Port: `7000`
- Active: `On`
- Callback DAT: check incoming lines/messages for `START`

The ESP32 sends `START` to `255.255.255.255:7000` on every debounced button press. It also prints `Button pressed: START` over USB serial before attempting UDP, so the TouchDesigner project can still detect the switch while Wi-Fi is disconnected.

## Receipt JSON

The ESP32 accepts:

```json
{
  "session_id": "20260505_155503",
  "mark_name": "THE SKY EYE",
  "receipt_title": "ORACLE",
  "subtitle": "THE ORACLE THAT WEARS US",
  "symbol_label": "THE SKY EYE",
  "oracle_text": "You value the journey's end.",
  "themes": ["time", "barrier", "absence"],
  "measures": {
    "intensity": 0.7,
    "instability": 0.2,
    "confidence": 0.8
  },
  "session_url": "https://berlogabob.github.io/OracleGallery/#/session/20260505_155503",
  "qr_required": true,
  "persona_image_allowed": false,
  "symbol_escpos_base64": "optional ESC/POS symbol raster bytes",
  "qr_escpos_base64": "ESC/POS QR raster fallback bytes",
  "receipt_raster_rle_base64": "required compact full-raster receipt for ilabel",
  "ilabel_width_dots": 576,
  "ilabel_height_dots": 1000
}
```

`session_url` is required. `/print` rejects receipt payloads without it because the physical receipt must include a QR code to the public session route. Persona images are intentionally excluded from thermal output.

Test with curl:

```bash
curl -X POST "http://<esp32-ip>/print" \
  -H "Content-Type: application/json" \
  --data @ESP32-BTN_Printer/examples/receipt_payload.json
```

Generate a payload from the reference session:

```bash
uv run python ESP32-BTN_Printer/tools/send_receipt.py assets/sessions/20260518_154452 \
  --dry-run \
  --preview-png reports/thermal_preview.png
```

Send a real receipt:

```bash
uv run python ESP32-BTN_Printer/tools/send_receipt.py assets/sessions/20260518_154452 \
  --protocol ilabel \
  --esp32 http://<esp32-ip>
```

The helper reads `*_receipt.txt`, optional `*_receipt.csv`, and the session `*_plotter.svg`. It renders a black-on-white thermal receipt on the Mac, including symbol and QR, then sends either ESC/POS fallback rasters or the compact iLabel full-raster receipt payload.

When the ESP32 is on a phone hotspot and its IP can change, use the scanner helper:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py status
uv run python ESP32-BTN_Printer/tools/printer_connect.py wake
uv run python ESP32-BTN_Printer/tools/printer_connect.py test
uv run python ESP32-BTN_Printer/tools/printer_connect.py probe
uv run python ESP32-BTN_Printer/tools/printer_connect.py sample
uv run python ESP32-BTN_Printer/tools/printer_connect.py receipt assets/sessions/20260518_154452 --dry-run
uv run python ESP32-BTN_Printer/tools/printer_connect.py receipt assets/sessions/20260518_154452 --preview-png reports/thermal_preview.png
```

If auto-discovery cannot determine the hotspot subnet, pass it explicitly:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --subnet 10.60.149.0/24
```

If `/probe-print` returns `ok: true` but the printer does not move paper, check the `notify` and `notify_packets` fields. `ok` only means the BLE characteristic accepted bytes; a silent printer can still mean the WP9509 expects the proprietary VSON/iLabel command sequence before it will print.

## Printer-Only Sketch

Upload:

```text
ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino
```

Then use the helper:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py status
uv run python ESP32-BTN_Printer/tools/printer_connect.py connect
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol escpos
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol raw
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol tspl
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol cpcl
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol zpl
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol catfeed
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol catblack
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-info
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel --message "HELLO ROLL"
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-text
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-roll
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-black
uv run python ESP32-BTN_Printer/tools/printer_connect.py probe
```

Those commands are written for the repo root. If your terminal is already inside `ESP32-BTN_Printer`, use `uv run python tools/printer_connect.py ...` instead.

If `/connect` works but `/test-print` is silent, run `/probe-print`. It tries:

- writable characteristics `fff1` and `fff2`
- BLE write-no-response and write-with-response
- payload formats `raw`, `escpos`, `tspl`, `cpcl`, `zpl`, cat-printer packet probes, and iLabel-style WP9509 probes

The cat-printer probes are for app-driven pocket printers that ignore plain ESC/POS bytes:

- `catstate`: request printer state/info packets
- `catfeed`: send the packetized feed-paper command
- `catblack`: send a short packetized black bitmap stripe

The iLabel probes come from the official VSON app code path for WP9509:

- `ilabel`: print full-raster receipt payloads on continuous 57 mm roll paper, or wrapped raster text for `/test-print`
- `ilabel-status`: write `01` and collect notify bytes
- `ilabel-info`: write `AC` and collect notify bytes
- `ilabel-cancel`: write `04`
- `ilabel-text`: alias for the same continuous-roll raster text path
- `ilabel-roll`: send an iLabel print header with paper type `1` for continuous 57 mm roll paper, plus a short low-density 576-dot raster test
- `ilabel-black`: alias for the same continuous-roll raster test

Do not use gap-label mode with roll paper. The printer can keep feeding while trying to find a label gap and then enter an error state.

For a targeted BLE write test:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py test \
  --protocol tspl \
  --characteristic 0000fff2-0000-1000-8000-00805f9b34fb \
  --write-response
```

## Useful Endpoints

Printer-only sketch:

```text
GET  /status   ESP32 Wi-Fi/printer state
POST /connect  scan/connect to configured printer and report write/notify chars
POST /wake     send ESC/POS init bytes
POST /test-print?protocol=escpos print a small test using raw/escpos/tspl/cpcl/zpl/ilabel-*
POST /raw      write raw hex bytes and report notify bytes, for replaying captured app traffic
POST /ilabel-test?protocol=ilabel-status run one official-app-style iLabel probe
POST /probe-print try BLE chars/common protocols and report notify bytes
POST /print?protocol=ilabel print receipt JSON; requires session_url and receipt_raster_rle_base64 for iLabel
```

Raw replay helper:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py raw \
  --esp32 http://<esp32-ip> \
  --hex "51 78 a1 00 01 00 50 b9 ff"
```

Button/printer sketch:

```text
GET  /status   ESP32 Wi-Fi/printer state
POST /start    send START over UDP and queue printer wake
POST /wake     queue printer wake only
POST /test-print print a plain text receipt without symbol or QR
POST /probe-print try BLE chars/common protocols and report notify bytes
POST /print    print receipt JSON
```

## First Hardware Test Order

Printer-only path:

1. Upload `PrinterDiscovery.ino` and confirm the BLE address/service/characteristics.
2. Fill `ESP32_PrinterOnly/config.local.h`.
3. Upload `ESP32_PrinterOnly.ino`.
4. Run `printer_connect.py status`, then `printer_connect.py connect`.
5. Run `printer_connect.py test --protocol escpos`.
6. If no paper moves, run `printer_connect.py probe` and inspect which attempts return notifications.
7. After a protocol prints, set `PRINTER_DEFAULT_PROTOCOL` to that protocol and run `printer_connect.py sample`.

Full button plus printer path:

1. Upload `PrinterDiscovery.ino` and record BLE details.
2. Fill `config.local.h`.
3. Upload `ESP32_BTN_Printer.ino`.
4. Confirm Serial Monitor shows an IP on `Nothing32`.
5. Confirm TouchDesigner receives `START` when the switch is pressed.
6. Run `tools/send_receipt.py --esp32 http://<esp32-ip>`.
7. If text prints but symbol does not, retry with `--no-symbol` and reduce `--symbol-size`.
