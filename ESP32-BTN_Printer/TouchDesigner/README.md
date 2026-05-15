# TouchDesigner ESP32 Button Bridge

Open the single project file, `TD_BTN.toe`, in TouchDesigner.

The project can listen for the current ESP32 firmware in two ways:

- UDP `START` packets on port `7000`.
- USB serial logs on `/dev/cu.usbserial-0001` at `115200`, matching the connected ESP32.

Choose the active input in `esp32_bridge/source_switch`:

- `wifi = 0`: USB serial only.
- `wifi = 1`: Wi-Fi UDP only.

USB is the default because the ESP32 is already connected to the MacBook.

When a selected `START` message arrives, the bridge and its main operators flash
bright green for about 1.5 seconds and `esp32_bridge/status_log` gets a `START`
row.

The limit switch wiring expected by the firmware is:

```text
Limit switch COM -> ESP32 GND
Limit switch NO  -> ESP32 GPIO 27
```

GPIO 27 is configured as `INPUT_PULLUP`, so a pressed switch reads `LOW`.

## Local Test

With `TD_BTN.toe` open, set `esp32_bridge/source_switch` to `wifi = 1`, then run:

```bash
python3 ESP32-BTN_Printer/TouchDesigner/send_start_test.py
```

The `esp32_bridge` operator should flash green and `esp32_bridge/status_log`
should get a `START` row. Set `wifi = 0` again to return to the USB serial
trigger.

## Notes

The firmware sends UDP broadcast `START` to `255.255.255.255:7000`. For that path,
the MacBook and ESP32 need to be on the same network. USB serial still works for
button detection because the firmware prints `Button pressed: START` before it
attempts UDP.
