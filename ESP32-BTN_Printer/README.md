# ESP32 Button + Thermal Receipt Printer

Arduino IDE firmware for the Oracle installation button and thermal printer bridge.

The ESP32 joins the `Nothing32` hotspot, reads a limit switch, sends `START` to TouchDesigner over UDP, wakes the thermal printer, and accepts receipt JSON at `POST /print`.

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
```

## Configure

Copy the example config:

```bash
cp ESP32-BTN_Printer/ESP32_BTN_Printer/config.example.h ESP32-BTN_Printer/ESP32_BTN_Printer/config.local.h
```

Edit `config.local.h`:

```cpp
#define WIFI_SSID "Nothing32"
#define WIFI_PASSWORD "PUT_THE_HOTSPOT_PASSWORD_HERE"
#define BUTTON_PIN 27
#define TOUCHDESIGNER_UDP_PORT 7000
```

`config.local.h` is ignored by git.

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
  "oracle_text": "You value the journey's end.",
  "themes": ["time", "barrier", "absence"],
  "measures": {
    "intensity": 0.7,
    "instability": 0.2,
    "confidence": 0.8
  },
  "session_url": "https://berlogabob.github.io/OracleGallery/#/session/20260505_155503",
  "symbol_escpos_base64": "optional ESC/POS raster bytes"
}
```

Test with curl:

```bash
curl -X POST "http://<esp32-ip>/print" \
  -H "Content-Type: application/json" \
  --data @ESP32-BTN_Printer/examples/receipt_payload.json
```

Generate a payload from the reference session:

```bash
uv run python ESP32-BTN_Printer/tools/send_receipt.py --dry-run
```

Send a real receipt:

```bash
uv run python ESP32-BTN_Printer/tools/send_receipt.py assets/sessions/20260505_155503 --esp32 http://<esp32-ip>
```

The helper reads `*_receipt.txt`, optional `*_receipt.csv`, and the session `*_plotter.svg`. It rasterizes the SVG on the Mac and sends ESC/POS bytes as base64 so the ESP32 does not need SVG support.

When the ESP32 is on a phone hotspot and its IP can change, use the scanner helper:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py status
uv run python ESP32-BTN_Printer/tools/printer_connect.py wake
uv run python ESP32-BTN_Printer/tools/printer_connect.py test
uv run python ESP32-BTN_Printer/tools/printer_connect.py probe
uv run python ESP32-BTN_Printer/tools/printer_connect.py sample
uv run python ESP32-BTN_Printer/tools/printer_connect.py receipt assets/sessions/20260505_155503
```

If auto-discovery cannot determine the hotspot subnet, pass it explicitly:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --subnet 10.60.149.0/24
```

If `/probe-print` returns `ok: true` but the printer does not move paper, check the `notify` and `notify_packets` fields. `ok` only means the BLE characteristic accepted bytes; a silent printer can still mean the WP9509 expects a proprietary VSON/iDoodle frame before it will print.

## Useful Endpoints

```text
GET  /status   ESP32 Wi-Fi/printer state
POST /start    send START over UDP and queue printer wake
POST /wake     queue printer wake only
POST /test-print print a plain text receipt without symbol or QR
POST /probe-print try BLE chars/common protocols and report notify bytes
POST /print    print receipt JSON
```

## First Hardware Test Order

1. Upload `PrinterDiscovery.ino` and record BLE details.
2. Fill `config.local.h`.
3. Upload `ESP32_BTN_Printer.ino`.
4. Confirm Serial Monitor shows an IP on `Nothing32`.
5. Confirm TouchDesigner receives `START` when the switch is pressed.
6. Run `tools/send_receipt.py --esp32 http://<esp32-ip>`.
7. If text prints but symbol does not, retry with `--no-symbol` and reduce `--symbol-size`.
