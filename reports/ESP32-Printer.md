# Create printing-only project

> lets continue to work on printing.
> 1 create new arduino project file. dont add code for touchdesigner from [ESP32_BTN_Printer.ino](ESP32-BTN_Printer/ESP32_BTN_Printer/ESP32_BTN_Printer.ino) focus on printing only. we know that we can "call" "connec" to printer, lets find how we can print

<details><summary>11 previous messages</summary>

> I’ll inspect the existing Arduino sketch and nearby project structure first, then I’ll create a separate printing-only sketch that keeps the connection path but removes the TouchDesigner-related pieces.
>
> I found the existing ESP32 printer area and a few unrelated dirty Python changes. I’ll leave those alone and work only under `ESP32-BTN_Printer`.
>
> The existing sketch already has useful printer pieces: BLE discovery/connect, write-chunking, `/test-print`, `/probe-print`, and JSON receipt printing. I’m going to split those into a new `ESP32_PrinterOnly` Arduino project and add a direct `/connect` plus protocol-focused test/probe endpoints so the next hardware step is finding which payload actually makes the printer feed paper.
>
> I’m about to add two files for the new Arduino sketch: a localizable config header and the printer-only `.ino`. The code will keep Wi-Fi only as a control surface for HTTP calls, with no button or TouchDesigner UDP path.
>
> <details><summary>Created 2 files</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+1088 -0)
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/config.example.h` (+43 -0)
>
> </details>
>
> The new sketch is in place. I’m doing a static pass now for Arduino compile issues and then I’ll update the printer README with the new upload/test flow.
>
> `arduino-cli` is not installed here, so I can’t do a real board compile in this workspace. I found the local config ignore rule already covers the new sketch folder, and I’m tightening the helper/README so you can hit `/connect`, `/test-print`, and `/probe-print` from the Mac.
>
> <details><summary>Edited 3 files</summary>
>
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+24 -4)
> - Wrote `./ESP32-BTN_Printer/README.md` (+86 -2)
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+12 -3)
> - Wrote `./ESP32-BTN_Printer/README.md` (+1 -1)
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+2 -0)
>
> </details>
>
> One issue surfaced in the helper: auto-discovery was still looking for the old `button_pin` status field, so it would miss the new printer-only firmware. I’m fixing that now.
>
> <details><summary>Edited 1 file</summary>
>
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+3 -1)
>
> </details>
>
> `arduino-cli` is available now through the shell path, so I’m going to try a real compile against the installed ESP32 core if it’s present.
</details>

Implemented the printer-only Arduino project.

New files:
- [ESP32_PrinterOnly.ino](./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino:1)
- [config.example.h](./ESP32-BTN_Printer/ESP32_PrinterOnly/config.example.h:1)

What it does:
- No TouchDesigner, button, UDP, or `START` code.
- Adds HTTP endpoints: `/status`, `/connect`, `/wake`, `/test-print`, `/probe-print`, `/print`.
- `/probe-print` tries `raw`, `escpos`, `tspl`, `cpcl`, and `zpl` across `fff1`/`fff2` with both BLE write modes.
- `/print?protocol=escpos` keeps receipt printing; other protocols print a text-only receipt payload.

Also updated:
- [printer_connect.py](./ESP32-BTN_Printer/tools/printer_connect.py:30) with `connect`, protocol selection, write-response, and characteristic targeting.
- [README.md](./ESP32-BTN_Printer/README.md:201) with the printer-only workflow.

Verified:
- `python3 -m py_compile ESP32-BTN_Printer/tools/printer_connect.py`
- `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly` passed. Sketch uses 93% program storage.

Next hardware sequence:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py connect
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol escpos
uv run python ESP32-BTN_Printer/tools/printer_connect.py probe
```

I left the unrelated existing dirty Python/test files untouched.

> ive installed arduino-cli. test it

<details><summary>1 previous message</summary>

> I’ll verify the CLI is visible, confirm the ESP32 core and required libraries, then compile the new printer-only sketch against a generic ESP32 board target.
</details>

`arduino-cli` works.

Verified:
- CLI: `arduino-cli 1.4.1`
- ESP32 core installed: `esp32:esp32 3.3.8`
- Required libraries installed: `ArduinoJson 7.4.3`, `NimBLE-Arduino 2.5.0`
- New printer-only sketch compiles:

```text
Sketch uses 1228304 bytes (93%) of program storage space.
Global variables use 56968 bytes (17%) of dynamic memory.
```

I did not upload to the board, only compiled `ESP32-BTN_Printer/ESP32_PrinterOnly`.

> Last login: Sat May 16 21:11:42 on ttys002
> /Users/berloga/.zshrc:source:20: no such file or directory: /Users/berloga/.openclaw/completions/openclaw.zsh
> berloga@Berlogas-MacBook-Pro NejeDraw % cd ESP32-BTN_Printer
> berloga@Berlogas-MacBook-Pro ESP32-BTN_Printer % ls
> ESP32_BTN_Printer                                               Grok-ESP32 WiFi-to-Bluetooth thermal printer server.json
> ESP32_BTN_Printer.zip                                           PrinterDiscovery
> ESP32_PrinterOnly                                               README.md
> examples                                                        tools
> Grok-ESP32 Button to TouchDesigner via UDP.json                 TouchDesigner
> berloga@Berlogas-MacBook-Pro ESP32-BTN_Printer % uv run python ESP32-BTN_Printer/tools/printer_connect.py connect
> /Users/berloga/Documents/GitHub/NejeDraw/.venv/bin/python3: can't open file '/Users/berloga/Documents/GitHub/NejeDraw/ESP32-BTN_Printer/ESP32-BTN_Printer/tools/printer_connect.py': [Errno 2] No such file or directory
> berloga@Berlogas-MacBook-Pro ESP32-BTN_Printer % cd ..
> berloga@Berlogas-MacBook-Pro NejeDraw % uv run python ESP32-BTN_Printer/tools/printer_connect.py connect
> Scanning 253 host(s) for ESP32 printer bridge on port 80...
> No ESP32 printer bridge found. Check that this Mac is on the same phone hotspot, then try --subnet 10.60.149.0/24.
> berloga@Berlogas-MacBook-Pro NejeDraw % uv run python ESP32-BTN_Printer/tools/printer_connect.py connect
> Scanning 253 host(s) for ESP32 printer bridge on port 80...
> No ESP32 printer bridge found. Check that this Mac is on the same phone hotspot, then try --subnet 10.60.149.0/24.
> berloga@Berlogas-MacBook-Pro NejeDraw % uv run python ESP32-BTN_Printer/tools/printer_connect.py connect
> uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol escpos
> uv run python ESP32-BTN_Printer/tools/printer_connect.py probe
> Scanning 253 host(s) for ESP32 printer bridge on port 80...
> No ESP32 printer bridge found. Check that this Mac is on the same phone hotspot, then try --subnet 10.60.149.0/24.
> Scanning 253 host(s) for ESP32 printer bridge on port 80...
> No ESP32 printer bridge found. Check that this Mac is on the same phone hotspot, then try --subnet 10.60.149.0/24.
> Scanning 253 host(s) for ESP32 printer bridge on port 80...
> uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol escpos
>
> No ESP32 printer bridge found. Check that this Mac is on the same phone hotspot, then try --subnet 10.60.149.0/24.
> berloga@Berlogas-MacBook-Pro NejeDraw % uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol escpos
> Scanning 253 host(s) for ESP32 printer bridge on port 80...
>
> uv run python ESP32-BTN_Printer/tools/printer_connect.py probe
> No ESP32 printer bridge found. Check that this Mac is on the same phone hotspot, then try --subnet 10.60.149.0/24.
> berloga@Berlogas-MacBook-Pro NejeDraw %
> berloga@Berlogas-MacBook-Pro NejeDraw % uv run python ESP32-BTN_Printer/tools/printer_connect.py probe
> Scanning 253 host(s) for ESP32 printer bridge on port 80...

<details><summary>7 previous messages</summary>

> The path error is just because you were already inside `ESP32-BTN_Printer`; from there the command is `uv run python tools/printer_connect.py connect`. The repeated scan failures mean the Mac did not find any ESP32 HTTP `/status` endpoint on its detected `/24`, so I’m going to check board/port visibility and make the helper’s failure output more diagnostic.
>
> The Mac is on `10.28.8.51/24`, so the helper scanned `10.28.8.0/24`. I also see the ESP32 USB serial device at `/dev/cu.usbserial-0001`, which suggests the most likely missing step is uploading/running the printer-only firmware or checking its Serial Monitor Wi-Fi output.
>
> Upload succeeded, but I caught the important detail: the new `ESP32_PrinterOnly` folder has no `config.local.h`, so that upload used the placeholder Wi-Fi password from `config.example.h`. I’m going to copy the existing ignored local config from the old sketch into the new printer-only sketch and upload again so the ESP32 can actually join the hotspot.
>
> The corrected firmware is now uploaded using the copied local config. I’m giving it a moment to boot and join Wi-Fi, then I’ll run the helper against the network again.
>
> The bridge is now found at `http://10.28.8.56`, and `/connect` reports the printer connected on write char `0xfff1` with notify char `0xfff4`. I’m going to send the ESC/POS test next; whether paper moves is the hardware signal we need.
>
> The test endpoint returned `ok: true`, which means the ESP32 connected to the BLE printer and the write characteristic accepted the ESC/POS bytes. I can’t see the paper from here, so I’m adding a README note about copying the existing local config into the printer-only sketch because that was the actual blocker.
>
> <details><summary>Edited 1 file</summary>
>
> - Wrote `./ESP32-BTN_Printer/README.md` (+8 -0)
>
> </details>
</details>

The ESP32 was not discoverable because `ESP32_PrinterOnly/config.local.h` was missing, so the first upload used the placeholder Wi-Fi password. I copied the existing ignored config from `ESP32_BTN_Printer/config.local.h` into the printer-only sketch and re-uploaded.

Current status:

```text
ESP32: http://10.28.8.56
wifi: connected
printer: connected
transport: ble
write_char: 0xfff1
notify_char: 0xfff4
default_protocol: escpos
```

I also sent:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol escpos --esp32 http://10.28.8.56
```

The ESP32 returned `ok: true`, so the BLE write succeeded. The remaining question is physical: did the printer move paper or print text?

If your terminal is inside `ESP32-BTN_Printer`, use:

```bash
uv run python tools/printer_connect.py test --protocol escpos --esp32 http://10.28.8.56
uv run python tools/printer_connect.py probe --esp32 http://10.28.8.56
```

I updated the README with the config-copy note and the correct command path for both repo root and `ESP32-BTN_Printer` folder.

> no move paper or print text.
> erloga@Berlogas-MacBook-Pro NejeDraw % cd ESP32-BTN_Printer
> berloga@Berlogas-MacBook-Pro ESP32-BTN_Printer % uv run python tools/printer_connect.py test --protocol escpos --esp32 http://10.28.8.56
>
> ESP32 printer bridge: http://10.28.8.56
> {
>   "mode": "noresp",
>   "ok": true,
>   "printed": true,
>   "protocol": "escpos"
> }
> berloga@Berlogas-MacBook-Pro ESP32-BTN_Printer % uv run python tools/printer_connect.py probe --esp32 http://10.28.8.56
>
> ESP32 printer bridge: http://10.28.8.56
> {
>   "attempts": [
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "raw"
>     },
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "escpos"
>     },
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "tspl"
>     },
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "cpcl"
>     },
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "zpl"
>     },
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "raw"
>     },
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "escpos"
>     },
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "tspl"
>     },
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "cpcl"
>     },
>     {
>       "char": "0000fff1-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "zpl"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "raw"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "escpos"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "tspl"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "cpcl"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "noresp",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "zpl"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "raw"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "escpos"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "tspl"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "cpcl"
>     },
>     {
>       "char": "0000fff2-0000-1000-8000-00805f9b34fb",
>       "mode": "write",
>       "notify": "",
>       "notify_packets": 0,
>       "ok": true,
>       "protocol": "zpl"
>     }
>   ],
>   "ok": true
> }
> berloga@Berlogas-MacBook-Pro ESP32-BTN_Printer %

<details><summary>16 previous messages</summary>

> The probe result is useful: BLE accepts bytes on both `fff1` and `fff2`, but the printer gives no notify traffic and no physical output. That usually means we have the GATT pipe but not the app-layer frame the printer expects, so I’m going to look for WP9509/VSON protocol clues and add a lower-level probe path instead of repeating ESC/POS variants.
>
> <details><summary>Searched web 2 times</summary>
>
> <details><summary>Searched web 2 times</summary>
>
> - Searched web for `WP9509 BLE printer protocol fff0 fff1 fff2 VSON`
> - Searched web for `GitHub idoodle printer protocol VSON`
>
> </details>
>
> </details>
>
> The web/library trail points at the “cat printer” packet protocol, not plain ESC/POS. These small app-driven printers often use packets starting `51 78`, with commands for device state, print intensity, print line bitmap, feed, and stop; plain text protocols can be accepted by BLE but ignored by the print engine. I’m going to inspect the installed Arduino thermal library for the exact command sequence and then add a `cat` protocol probe.
>
> <details><summary>Searched web 1 time</summary>
>
> <details><summary>Searched web 1 time</summary>
>
> - Searched web for `https://github-wiki-see.page/m/fulda1/Thermal_Printer/wiki/Cat-printer-protocol`
>
> </details>
>
> </details>
>
> I found the relevant packet details in the installed Larry Bank `Thermal Printer Library` and its linked protocol notes: cat-printer commands are wrapped as `51 78 <cmd> 00 <len-lo> <len-hi> <data> <crc> FF`, with `A1` feed paper and `A2` bitmap line. I’m going to add three targeted probes: `catstate`, `catfeed`, and `catblack`; `catfeed` should physically move paper if this is the right app protocol.
>
> <details><summary>Edited 3 files</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+91 -0)
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+5 -1)
> - Wrote `./ESP32-BTN_Printer/README.md` (+9 -1)
>
> </details>
>
> The new probes are in the sketch and helper. I’m compiling now; if it passes, I’ll upload and run `catstate`, `catfeed`, and `catblack` against the ESP32.
>
> Upload finished. I’m waiting for Wi-Fi, then I’ll try the cat-printer state/feed/black probes directly against the same ESP32 URL.
>
> Those writes also succeeded at the BLE layer. I still need the physical result from you, but before stopping I’m going to run the full probe once because the new `catstate` command may produce notify bytes if this protocol is accepted.
>
> The expanded full probe now takes longer than the helper’s old 20 second timeout because `catblack` sends many packetized bitmap lines across every characteristic/mode. I’ll rerun it with a longer timeout, then I’ll probably split the probe so we can avoid this delay during hardware testing.
>
> <details><summary>Searched web 2 times</summary>
>
> <details><summary>Searched web 2 times</summary>
>
> - Searched web for `"VSON" "51 78" printer protocol`
> - Searched web for `idoodle apk VSON download`
>
> </details>
>
> </details>
>
> The full probe still reports zero notification packets, including cat-state requests. That may mean either this is a different proprietary protocol, or we are subscribed to the wrong notify characteristic. I’m going to make the firmware subscribe to every notifiable characteristic in the printer service so we don’t miss replies hidden on another UUID.
>
> <details><summary>Edited 2 files</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+33 -3)
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+1 -1)
>
> </details>
>
> After the notify-subscribe change, the first catstate write failed at the firmware layer. I’m checking `/connect` and `/status`; this may be a stale BLE connection after flashing rather than the protocol itself.
>
> The new subscribe-all code exposed a pointer-lifetime bug: after refreshing the characteristic list, `/status` showed `write_char` as `fff4`, which is a notify characteristic, so writes started failing. I’m fixing that by reacquiring the configured write characteristic after subscribing.
>
> <details><summary>Edited 1 file</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+5 -0)
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+5 -4)
>
> </details>
</details>

I added and uploaded a new test firmware with cat-printer protocol probes based on the documented `51 78 ... FF` packet format from the [Thermal_Printer cat protocol notes](https://github-wiki-see.page/m/fulda1/Thermal_Printer/wiki/Cat-printer-protocol).

What I tested:
- `catfeed`: packetized feed-paper command
- `catblack`: packetized short black bitmap stripe
- `catstate`: packetized state/info request
- Subscribe-all notify characteristics so we are less likely to miss printer replies

Result from ESP32:
- BLE connects.
- Writes still return `ok: true`.
- No notify bytes from any protocol/char/mode.
- I cannot confirm physical movement from here.

Please confirm whether either of these moved paper or printed a stripe:

```bash
uv run python tools/printer_connect.py test --protocol catfeed --esp32 http://10.28.8.56
uv run python tools/printer_connect.py test --protocol catblack --esp32 http://10.28.8.56
```

If both are silent, the next serious step is to capture what the official `idoodle` / `iLabel` app sends, because this printer is likely using a VSON-specific command sequence beyond ESC/POS and common cat-printer packets.

> no move or print

<details><summary>7 previous messages</summary>

> That rules out the easy paths: plain ESC/POS, label-language probes, and the common `51 78` cat-printer packets all reach BLE but do not trigger the mechanism. I’m going to stop guessing bytes and make the next step more direct: add a raw hex endpoint/helper so we can replay exact app traffic once captured, and look for the VSON app protocol in the Android APK/static code.
>
> I’m adding a `/raw` endpoint and a `printer_connect.py raw --hex ...` helper now. That gives us a stable replay tool: once we capture or discover real VSON bytes, we can send them immediately without recompiling firmware every time.
>
> <details><summary>Edited 3 files</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+120 -0)
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+15 -2)
> - Wrote `./ESP32-BTN_Printer/README.md` (+9 -0)
>
> </details>
>
> The raw replay path is added. I’ll compile and upload it now, then send one known `catfeed` packet through `/raw` just to confirm the endpoint works.
>
> The `/raw` endpoint is uploaded and working; it wrote the packet bytes successfully. I’m now checking whether we can statically inspect the official Android app for the real command sequence instead of continuing blind protocol guesses.
>
> `jadx` is installing so we can decompile the Android app once we get an APK/XAPK. The APKPure page is JavaScript-heavy and did not expose a direct APK link in the first HTML fetch, so I’m going to leave that as a separate reverse-engineering step rather than blocking the firmware work.
>
> `jadx` is installed now. I’m doing one quick pass over the APKPure/AppBrain pages for a direct APK/XAPK URL; if that doesn’t expose one cleanly, the practical next move is to capture traffic from the phone app rather than scraping app-store pages.
</details>

No movement from `catfeed`/`catblack` means we’ve exhausted the reasonable standard guesses. The ESP32 can connect and write to BLE, but the printer is ignoring the payloads.

I added and uploaded a raw replay endpoint so the next step is practical:

```bash
uv run python tools/printer_connect.py raw \
  --esp32 http://10.28.8.56 \
  --hex "..."
```

That lets us replay exact bytes without changing firmware.

The next useful move is to capture the official app’s BLE writes:

1. On Android, enable Developer Options → Enable Bluetooth HCI snoop log.
2. Open `idoodle`/`iLabel`, connect to WP9509, print a tiny label.
3. Pull the `btsnoop_hci.log` file.
4. Open in Wireshark and filter for ATT writes, usually `btatt`.
5. Copy the write payload hex and replay it with the new `raw --hex`.

I also installed `jadx` for static APK inspection. Because your shell has a bad `JAVA_HOME`, run it like this if you get an APK/XAPK:

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk jadx -d /tmp/idoodle_decompiled path/to/idoodle.apk
```

Current ESP32 status is still good:

```text
http://10.28.8.56
wifi: connected
printer: connected
write_char: 0xfff1
```

> [check_this_Original_App.jpg](check_this_Original_App.jpg) [check_this_Original_info.jpg](check_this_Original_info.jpg)  this are 2 screenshots from offisial app. could it help to finde answers how to force this printer to print from ESP32, not from its app. i have tested printer with native app and its working.

<details><summary>27 previous messages</summary>

> I’ll inspect those screenshots first and extract any printer model/app/version/protocol clues from them. If they show the app package/version or device info, that can directly guide either APK decompilation or BLE traffic capture.
>
> <details><summary>Explored 1 search, 1 list, ran 1 command</summary>
>
> - Ran `pwd`
>
> <details><summary>Explored 1 search, 1 list</summary>
>
> - Listed files
> - Searched for `check_this_Original_(App|info)\.jpg$|\.apk$|\.xapk$`
>
> </details>
>
> </details>
>
> ![Image](<./check_this_Original_App.jpg>)
> ![Image](<./check_this_Original_info.jpg>)
>
> <details><summary>Searched web 1 time</summary>
>
> <details><summary>Searched web 1 time</summary>
>
> - Searched web for `Google Play iLabel Vson Technology Co.,Ltd package name`
>
> </details>
>
> </details>
>
> The screenshots do help: they identify the correct app as **iLabel**, package `com.vson.ilabel`, not `idoodle`. The second screenshot also confirms the exact device profile the app sees: `WP9509`, firmware `V38`, MAC `95:09:25:47:56:B3`. That means our BLE target is correct; what is missing is the iLabel app-layer command sequence.
>
> <details><summary>Ran 3 commands</summary>
>
> - Ran `python3 - <<'PY'
> from pathlib import Path
> html=Path('/tmp/idoodle/download.html').read_text(errors='ignore')
> for needle in ['download_link','direct-down-btn','aegon-direct-download-btn','fast-download-start-btn','href="https://download','download_id','fastDownloadId','packageName']:
>     print('\n---', needle)
>     i=0
>     while True:
>         j=html.find(needle, i)
>         if j<0: break
>         print(html[max(0,j-500):j+700].replace('\n',' ')[:1400])
>         i=j+len(needle)
> PY`
> - Ran `curl -L 'https://apkpure.com/ilabel/com.vson.ilabel/download' -o /tmp/idoodle/ilabel_apkpure_com.html && python3 - <<'PY'
> from pathlib import Path
> html=Path('/tmp/idoodle/ilabel_apkpure_com.html').read_text(errors='ignore')
> print(len(html))
> for needle in ['download_link','direct-down-btn','fastDownloadId','packageName','download_id','href="https://download']:
>     print('\n---', needle)
>     j=html.find(needle)
>     print(html[max(0,j-500):j+700].replace('\n',' ')[:1400] if j>=0 else 'not found')
> PY`
> - Ran `curl -I -L 'https://d.apkpure.net/b/APK/com.vson.ilabel?version=latest' | sed -n '1,80p'`
>
> </details>
>
> The screenshots gave the exact APK target. APKPure exposes a direct APK URL for `com.vson.ilabel`, so I’m downloading/decompiling iLabel now and searching for BLE write code, UUIDs, model `WP9509`, and packet constants.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `mkdir -p /tmp/ilabel && curl -L 'https://d.apkpure.net/b/APK/com.vson.ilabel?version=latest' -o /tmp/ilabel/iLabel_3.3.apk && ls -lh /tmp/ilabel/iLabel_3.3.apk`
>
> </details>
>
> Context compaction
>
> Source: automatic
> Status: completed
>
> The screenshots help: they identify the exact app and model (`iLabel`, `WP9509`, firmware `V38`) and confirm this is an app-protocol problem, not a broken printer. I’m going to inspect the official APK now and look for the BLE write sequence it uses before we change the ESP32 sketch again.
>
> <details><summary>Ran 3 commands</summary>
>
> - Ran `ls -lh /tmp/ilabel/iLabel_3.3.apk 2>/dev/null || true`
> - Ran `command -v arduino-cli && arduino-cli version`
> - Ran `JAVA_HOME=/opt/homebrew/opt/openjdk jadx --version`
>
> </details>
>
> The APK download completed, and the local tooling is in place: `arduino-cli` is installed and `jadx` runs when pointed at Homebrew’s JDK. I’m decompiling the official iLabel APK and then I’ll search for the BLE service, characteristics, model IDs, and print command builders.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `rm -rf /tmp/ilabel/decompiled && JAVA_HOME=/opt/homebrew/opt/openjdk jadx -d /tmp/ilabel/decompiled /tmp/ilabel/iLabel_3.3.apk`
>
> </details>
>
> Decompilation finished with recoverable errors, which is common on Android apps with obfuscation; the source tree is still usable. I’m searching both Java/Kotlin output and raw APK strings so we can find protocol constants even if class names are scrambled.
>
> <details><summary>Explored 4 searches, 1 list, ran 1 command</summary>
>
> <details><summary>Explored 1 search, 1 list</summary>
>
> - Searched for `WP9509|95:09|fff0|fff1|fff2|fff4|0000fff|BluetoothGatt|writeCharacteristic|setValue|Firmware|firmware|ble|characteristic|service|MTU|GBK|bitmap|print` in `decompiled`
> - Listed files in `decompiled`
>
> </details>
>
> - Ran `strings /tmp/ilabel/iLabel_3.3.apk | rg -i "wp9509|fff0|fff1|fff2|fff4|0000fff|bluetooth|print|firmware|vson|label|mac|service|characteristic|mtu|write" | head -n 240`
>
> <details><summary>Explored 3 searches</summary>
>
> - Searched for `FFF2|FFF4|fff1|fff2|fff4|0000fff|0000FFF|49535343|6e4000|ffe0|FFE0` in `sources`
> - Searched for `WP9509|WP9503|WP9512|V38|V30|hardware|firmware|intermittent` in `sources`
> - Searched for `BluetoothGatt|BluetoothDevice|BluetoothAdapter|BluetoothLeScanner|writeCharacteristic|onCharacteristicChanged|onCharacteristicWrite|requestMtu|setCharacteristicNotification|getService|getCharacteristic` in `sources`
>
> </details>
>
> </details>
>
> The official app confirms our BLE layer is basically right: it uses service `fff0`, writes to `fff1`, and enables notifications on `fff4`. That means the printer is ignoring our payloads, so I’m tracing the app’s code path from “print” down to the byte arrays passed into `writeCharacteristic`.
>
> <details><summary>Explored 29 files, 12 searches, 1 list</summary>
>
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/VsonPtBLE.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/BleConnectHelper.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/e0.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/Constant.java`
> - Searched for `\.K\(|\.m0\(|\.l0\(|K\(byte\[\]|m0\(byte\[\]|l0\(BluetoothGattCharacteristic` in `ilabel`
> - Searched for `f26842p|f26843q|f26845s|f26846t|f26847u|f26848v|f26850x|f26851y|AAFFFFFFFFFFFF|ee01|cb01|0xAA|0xaa|0xBB|0xbb|0xCC|0xcc` in `ilabel`
> - Searched for `new byte\[|byte\[\]|toByteArray|ByteArrayOutputStream|bitmap|Bitmap|print|Print|打印|标签` in `ilabel`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Searched for `f27006j|f27004h|f27005i|f27022z|this\.I|this\.O|this\.Q|l1\(|k0\(|z1\(|y1\(|x1\(` in `t2.java`
> - Searched for `byte\[\] bArr|l1\(byte\[\]|this\.I|List<byte|ArrayList<byte|ArrayList<|new byte\[` in `t2.java`
> - Searched for `public .*\(byte\[|private .*\(byte\[|boolean .*byte\[|void .*byte\[` in `t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Searched for `f26997c\s*=|this\.f26997c|p0\(|VsonPtBLE\.z|VsonPtClassic` in `t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/k2.java`
> - Searched for `class k2|k2` in `bt`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/y1.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/z1.java`
> - Listed files in `bt`
> - Searched for `y1|z1|u1|v1|w1|x1`
> - Searched for `U0\(|A0\(|y0\(|M0\(|G0\(` in `t2.java`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/bt/t2.java`
> - Read `./ESP32-BTN_Printer/tools/printer_connect.py`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Searched for `\.i1\(|\.n1\(|i1\(` in `ilabel`
> - Read `/tmp/ilabel/decompiled/sources/com/vson/ilabel/ui/main/MainActivity.java`
> - Searched for `A3|H3` in `MainActivity.java`
>
> </details>
>
> I found a second important detail in the app code: iLabel does not wrap commands like ESC/POS. It sends raw one-byte commands such as `01`, `04`, `AC`, then print headers beginning with `02` and raster rows beginning with `03`. I’m adding those as explicit iLabel probes and making `/raw` return notification bytes, because those notifications are how the official app drives the next print chunk.
>
> <details><summary>Edited 2 files, explored 1 file</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+103 -0)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+116 -0)
>
> <details><summary>Explored 2 files</summary>
>
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
>
> </details>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+2 -0)
>
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+15 -1)
>
> </details>
>
> I patched the firmware to expose official iLabel-style probes: `ilabel-status`, `ilabel-info`, `ilabel-cancel`, `ilabel-black`, and `ilabel-black-gap`. I also fixed `/raw` so it can report `fff4` notification bytes, which should tell us whether the printer understands a command.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> The sketch still compiles; size is tight but under the ESP32 app limit. I’m uploading it now, then I’ll run the new iLabel probes against `http://10.28.8.56`.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
> - Ran `sleep 4 && uv run python ESP32-BTN_Printer/tools/printer_connect.py status --esp32 http://10.28.8.56`
>
> </details>
>
> After the upload, the ESP32 is no longer answering at the old `10.28.8.56` address, so I’m rediscovering it on the current subnet before running the probes.
>
> <details><summary>Ran 7 commands</summary>
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py status --timeout 8 --scan-timeout 0.8`
> - Ran `timeout 12 arduino-cli monitor -p /dev/cu.usbserial-0001 --config baudrate=115200 2>&1 || true`
> - Ran `arduino-cli monitor -p /dev/cu.usbserial-0001 --config baudrate=115200`
> - Ran `ls /dev/cu.usbserial* /dev/cu.SLAB_USBtoUART* /dev/cu.wchusbserial* 2>/dev/null || true`
> - Ran `networksetup -getairportnetwork en0 2>/dev/null || true; ifconfig | rg 'inet '`
> - Ran `arduino-cli board list`
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> The ESP32 upload succeeded, but this Mac is currently on `192.168.1.167`, not the `10.28.x.x` hotspot where the ESP32 was reachable. I’m doing one final upload of the exact compiled source, then the next live test needs the Mac and ESP32 back on the same hotspot/LAN.
>
> <details><summary>Edited 1 file, explored 1 file, 1 search, ran 4 commands</summary>
>
> - Ran `arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> <details><summary>Explored 1 file, 1 search</summary>
>
> - Searched for `PrinterOnly|raw|probe|test --protocol` in `README.md`
> - Read `./ESP32-BTN_Printer/README.md`
>
> </details>
>
> - Wrote `./ESP32-BTN_Printer/README.md` (+17 -4)
>
> - Ran `git status --short ESP32-BTN_Printer`
>
> - Ran `git diff -- ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino ESP32-BTN_Printer/tools/printer_connect.py ESP32-BTN_Printer/README.md | sed -n '1,260p'`
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py --help | rg "ilabel|protocol"`
>
> </details>
</details>

Yes, the screenshots helped. They confirmed the official app is **iLabel by Vson** and the printer is **WP9509 firmware V38**, so I decompiled the iLabel APK and found the app’s BLE path.

I updated the printer-only firmware with iLabel-style probes in [ESP32_PrinterOnly.ino](./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino):
- BLE service: `fff0`
- write char: `fff1`
- notify char: `fff4`
- official-app commands now exposed as:
  - `ilabel-status` sends `01`
  - `ilabel-info` sends `AC`
  - `ilabel-cancel` sends `04`
  - `ilabel-black`
  - `ilabel-black-gap`

I also updated [printer_connect.py](./ESP32-BTN_Printer/tools/printer_connect.py) and [README.md](./ESP32-BTN_Printer/README.md). `/raw` now reports notification bytes, which matters because the official app waits for printer notify packets while printing.

Verified:
- `arduino-cli` works: version `1.4.1`
- sketch compiles
- sketch uploaded successfully to `/dev/cu.usbserial-0001`

I could not run the live HTTP printer test after upload because this Mac is now on `192.168.1.167`, while the ESP32 was previously reachable on `10.28.8.56`. Reconnect the Mac to the same hotspot/LAN as the ESP32, then run:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py status
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-info
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-black-gap
```

If `ilabel-status` returns notify bytes, we are on the correct protocol path.

> i cannect to same hotspot from my phone grom macbook. lets continue to work

<details><summary>26 previous messages</summary>

> I’ll rediscover the ESP32 first so we don’t assume the old `10.28.8.56` address is still valid, then I’ll run the iLabel probes that came from the official app code.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `networksetup -getairportnetwork en0 2>/dev/null || true; ifconfig | rg 'inet '`
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py status --timeout 12 --scan-timeout 0.8`
>
> </details>
>
> The ESP32 is back at `http://10.28.8.56`. It is on Wi-Fi but not connected to the printer yet, so I’m connecting BLE and checking which notify characteristic it subscribes to before sending print bytes.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py connect --esp32 http://10.28.8.56`
>
> </details>
>
> BLE connects and writes to `fff1`, but the firmware did not find a notify characteristic on this connection. I’m going to send `ilabel-status` and `ilabel-info` first; these are low-risk and should reveal whether the printer answers the app-style commands.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status --esp32 http://10.28.8.56`
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-info --esp32 http://10.28.8.56`
>
> </details>
>
> The first two probes gave the answer we needed: `ilabel-status` returned `01 30 00 40 02 ...`, which the official app parses as a 576-dot print width (`0x0240`). Our raster probe was still using 384 dots, so I’m correcting the iLabel raster packet width before trying to move paper.
>
> <details><summary>Edited 2 files, ran 1 command</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+9 -4)
> - Wrote `./ESP32-BTN_Printer/README.md` (+1 -1)
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> The width fix compiles. I’m uploading it now; after that I’ll send the iLabel black-stripe test, which should be the first meaningful print/move-paper attempt for this protocol.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> Upload is complete. I’ll wait a moment for Wi-Fi, confirm the bridge is reachable again, then run the status and raster probes one at a time.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `sleep 4 && uv run python ESP32-BTN_Printer/tools/printer_connect.py status --esp32 http://10.28.8.56 --timeout 12`
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status --esp32 http://10.28.8.56`
>
> </details>
>
> The status reply is stable and confirms the 576-dot width. I’m sending `ilabel-black-gap` now because the app text says WP9509/V30+ supports gap label paper, and your screenshot shows WP9509 V38.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-black-gap --esp32 http://10.28.8.56`
>
> </details>
>
> The `ilabel-black-gap` command got real printer replies, including an `A5 ...` response after the print header. One more protocol detail stands out from the app: it requests a larger BLE MTU so each 76-byte raster row is sent as one BLE write. Our firmware was still splitting rows into 20-byte chunks, which can make the printer ignore image data. I’m fixing that packet boundary now.
>
> <details><summary>Edited 1 file, explored 3 files, ran 2 commands</summary>
>
> - Ran `rg -n "requestMtu|requestMTU|getMTU|mtu" ~/Library/Arduino15/packages/esp32/hardware/esp32/3.3.8/libraries/NimBLE-Arduino/src /Users/berloga/Documents/Arduino/libraries/NimBLE-Arduino/src 2>/dev/null | head -n 80`
>
> <details><summary>Explored 3 files</summary>
>
> - Read `~/Documents/Arduino/libraries/NimBLE-Arduino/src/NimBLEClient.cpp`
> - Read `~/Documents/Arduino/libraries/NimBLE-Arduino/src/NimBLEClient.h`
> - Read `~/Documents/Arduino/libraries/NimBLE-Arduino/src/NimBLERemoteValueAttribute.cpp`
>
> </details>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+17 -3)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+46 -0)
>
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> The MTU and single-packet row fix compiles. I’m uploading it, then I’ll repeat `ilabel-status` and `ilabel-black-gap`.
>
> <details><summary>Ran 3 commands</summary>
>
> - Ran `arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
> - Ran `sleep 4 && uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status --esp32 http://10.28.8.56 --timeout 20`
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-black-gap --esp32 http://10.28.8.56 --timeout 20`
>
> </details>
>
> The printer accepted the status command after the MTU change, but the first 76-byte raster row write failed at the BLE write layer. I’m adding a fallback so iLabel packet writes try the official no-response write first, then write-with-response if the BLE stack rejects the larger no-response packet.
>
> <details><summary>Edited 1 file, ran 1 command</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+8 -1)
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly && arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> papper stratst to roll. i had to turn printer off, its got "error" kinda thing. we need to specify type "roll paper" 57 size width. same behavior was on original app.
>
> That behavior matches the app logic: `ilabel-black-gap` told the printer it was gap-label stock, so it likely kept feeding while looking for the gap sensor mark. I’m switching the test path to continuous roll paper only and making the raster test much shorter so it cannot run away.
>
> I’m also removing the gap-paper probe from the automatic probe list. For this printer with roll stock, gap mode is now treated as unsafe because the firmware will feed while trying to find a label gap.
>
> <details><summary>Edited 3 files, explored 1 search, ran 1 command</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+12 -7)
>
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+1 -1)
>
> <details><summary>Explored 1 search</summary>
>
> - Searched for `ilabel-black-gap|ilabel-black|iLabel probes|576-dot` in `README.md`
>
> </details>
>
> - Wrote `./ESP32-BTN_Printer/README.md` (+5 -3)
>
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> The roll-paper-only firmware compiles. I’m uploading it now; after this I’ll only run `ilabel-status` unless you confirm the printer is powered back on and ready for the short roll-paper raster test.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
> - Ran `sleep 4 && uv run python ESP32-BTN_Printer/tools/printer_connect.py status --esp32 http://10.28.8.56 --timeout 12`
>
> </details>
</details>

Good catch. The runaway feed was because we used `ilabel-black-gap`, which sets the iLabel paper type to gap-label mode. On roll paper the printer keeps feeding while looking for a gap, then errors.

I changed the firmware so the safe test is now continuous roll paper only:
- `ilabel-roll` uses paper type `1`
- width stays `576` dots, learned from the printer’s own status reply
- raster test is shortened to 16 rows with very light marks
- `ilabel-black-gap` is disabled in firmware and removed from the CLI/docs path

Uploaded successfully. ESP32 is back online at `http://10.28.8.56`.

When the printer is powered back on and cleared from error state, run only:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status --esp32 http://10.28.8.56
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-roll --esp32 http://10.28.8.56
```

Do not run `ilabel-black-gap` with this roll paper.

> prenter rebooted, lets work

<details><summary>16 previous messages</summary>

> I’ll verify the printer answers `ilabel-status` after reboot, then send only the short continuous-roll test. I’m avoiding gap mode completely now.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status --esp32 http://10.28.8.56 --timeout 20`
>
> </details>
>
> Status is clean: printer replied with the same iLabel status packet, including `0x0240` width. I’m sending `ilabel-roll` now; it is a short continuous-roll raster test, not gap-label mode.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-roll --esp32 http://10.28.8.56 --timeout 20`
>
> </details>
>
> The roll-paper probe completed and the printer replied with `A5 94 00 00 00 00`, then a clean status packet. I’m checking how the official app interprets that `A5` reply so we can tell whether it accepted the print header or is reporting a paper/state condition.
>
> <details><summary>Explored 1 search</summary>
>
> - Searched for `"a5"|A5|f27004h|f27005i|this\.P|this\.O|this\.Q` in `t2.java`
>
> </details>
>
> The app treats `A5` as the print-flow response: it updates progress and then schedules the next data write. Our test was still streaming rows on a fixed delay, so I’m changing it to wait for an `A5` notification after the print header and after each row, matching the app’s flow control more closely.
>
> <details><summary>Edited 2 files, explored 1 file, 1 search</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+22 -1)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+17 -0)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+21 -16)
>
> <details><summary>Explored 1 file, 1 search</summary>
>
> - Searched for `writeIlabelHeader|writeIlabelRow|waitForBleNotification` in `ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
>
> </details>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+6 -1)
>
> </details>
>
> I adjusted the flow-control code so notifications are cleared before each write, then the firmware waits for the printer’s `A5` response. That avoids missing a fast acknowledge and avoids streaming rows faster than the printer accepts them.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly && arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> Upload succeeded with flow-control enabled. I’ll run status again, then the short `ilabel-roll` test; this version waits for `A5` after the header and each row.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `sleep 4 && uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status --esp32 http://10.28.8.56 --timeout 20`
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-roll --esp32 http://10.28.8.56 --timeout 60`
>
> </details>
>
> The header was acknowledged, but the printer did not send `A5` after the first raster row. That means `A5` is likely header/progress flow control, not per-row flow control. I’m keeping the safe continuous-roll paper type and header wait, but removing the per-row acknowledge requirement.
>
> <details><summary>Edited 1 file, ran 1 command</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+0 -7)
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly && arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> Upload is complete. I’ll run the same two commands: status first, then `ilabel-roll`. If paper starts feeding continuously again, power it off; but this test is continuous-roll mode and only 16 rows.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `sleep 4 && uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status --esp32 http://10.28.8.56 --timeout 20 && uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-roll --esp32 http://10.28.8.56 --timeout 30`
>
> </details>
</details>

`ilabel-roll` completed without HTTP/BLE error.

Current result:
- `ilabel-status` works.
- Printer reports width `0x0240` = `576` dots.
- `ilabel-roll` uses continuous roll paper mode, not gap mode.
- Final printer status came back clean.

Did the printer move a small amount or print tiny marks this time? That physical result decides the next step:
- If it printed/moved correctly: we can build actual text/bitmap printing on this protocol.
- If it did nothing: the missing piece is likely row encoding or final/feed command.
- If it fed too much again: we need to lower the test even further and inspect the paper-state byte.

> papper mooved. tiny size and there some line marks!

<details><summary>8 previous messages</summary>

> That confirms the core protocol is correct now: continuous-roll mode, `02` print header, `03` raster rows, 576-dot width. I’m going to replace the line-mark probe with a small raster text test so we can prove we can print controlled content, not just move paper.
>
> <details><summary>Explored 2 files, 1 search</summary>
>
> - Searched for `ilabel-roll|sendIlabelProbe|writeIlabelRow|cleanProtocol` in `ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/tools/printer_connect.py`
>
> </details>
>
> The line-mark proof is enough to move from probing to a real raster payload. I’m adding a fixed `ilabel-text` test that prints `ESP32 OK` as 576-dot bitmap rows using the same continuous-roll protocol.
>
> <details><summary>Edited 3 files</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+143 -0)
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+1 -0)
> - Wrote `./ESP32-BTN_Printer/README.md` (+2 -0)
>
> </details>
>
> The text raster test is implemented as `ilabel-text`, and I updated the helper script/docs so it’s available from the CLI. I’m compiling and uploading it now, then I’ll run status and the text test.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly && arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> Upload succeeded. I’m running a status check and then `ilabel-text`; this should move paper a little more than the mark probe and print `ESP32 OK`.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `sleep 4 && uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status --esp32 http://10.28.8.56 --timeout 20 && uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-text --esp32 http://10.28.8.56 --timeout 40`
>
> </details>
</details>

`ilabel-text` ran successfully.

What changed:
- Added `ilabel-text` protocol to the firmware and CLI.
- It prints fixed raster text: `ESP32 OK`.
- It uses continuous roll paper mode only.
- It waits for the printer’s `A5` header acknowledgement, then streams 576-dot raster rows.

The printer replied cleanly:

```text
A5 94 00 00 00 00
01 30 00 40 02 00 00 00 00 00 01 38 01
```

That means the command flow is accepted. Check the paper now: it should show `ESP32 OK` or at least recognizable blocky letters.

> succses! its printed "ESP32 OK"

<details><summary>27 previous messages</summary>

> Great, that proves the printer’s actual print protocol. I’m going to promote the probe into a real `ilabel` print path now, so `/test-print` can print custom text and `/print?protocol=ilabel` can render receipt text instead of only the fixed `ESP32 OK` sample.
>
> <details><summary>Explored 1 file, 2 searches</summary>
>
> - Searched for `sendIlabelTextProbe|buildIlabelTextRow|ilabelGlyphRow|printReceipt|handleTestPrint|buildReceiptText` in `ESP32_PrinterOnly.ino`
> - Searched for `ilabel` in `printer_connect.py`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
>
> </details>
>
> Context compaction
>
> Source: automatic
> Status: completed
>
> That’s the breakthrough: the printer is accepting the iLabel raster protocol, not ESC/POS or TSPL. I’ll turn the fixed `ESP32 OK` probe into a real roll-paper text print path now, then compile and upload it.
>
> <details><summary>Explored 5 files, 1 search</summary>
>
> - Searched for `sendIlabelTextProbe|buildIlabelTextRow|ilabelGlyphRow|handleTestPrint|printReceipt|choices=|ilabel-text|ilabel-roll|sendIlabelProbe` in `ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/tools/printer_connect.py`
> - Read `./ESP32-BTN_Printer/tools/printer_connect.py`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
>
> </details>
>
> I found one small cleanup too: `/ilabel-test` currently calls the probe twice, so I’ll remove that duplicate while I’m touching the iLabel path. Next patch is narrowly firmware + CLI protocol naming + README examples.
>
> <details><summary>Explored 5 files, 1 search</summary>
>
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/README.md`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Searched for `String cleanProtocolName|String cleanText|String escapeLabelText` in `ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
>
> </details>
>
> I’m editing the firmware so `ilabel` becomes the normal printer protocol: it will render text into 576-dot roll-paper raster rows, wrap lines, and keep the working continuous roll paper type.
>
> <details><summary>Edited 3 files, explored 1 file, 1 search</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+3 -2)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+44 -14)
>
> <details><summary>Explored 4 files</summary>
>
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
>
> </details>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+29 -0)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+2 -0)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+2 -2)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+14 -3)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+64 -10)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+176 -0)
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+3 -0)
>
> <details><summary>Explored 1 search</summary>
>
> - Searched for `sendIlabelTextProbe|buildIlabelTextRow\(|ilabel` in `ESP32_PrinterOnly.ino`
>
> </details>
>
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+4 -0)
>
> - Wrote `./ESP32-BTN_Printer/README.md` (+3 -1)
>
> </details>
>
> The firmware now has a generic iLabel text renderer and the CLI has `--message`, so we can ask the ESP32 to print something specific instead of only the baked-in sample. I’m compiling next; if that passes I’ll upload to the ESP32.
>
> <details><summary>Explored 1 file, ran 1 command</summary>
>
> <details><summary>Explored 3 files</summary>
>
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
>
> </details>
>
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> Compile passed, although the sketch is getting large at 94% of program storage. I’m uploading the new firmware now, then I’ll run a small `HELLO ROLL` print through the new `ilabel` protocol.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `arduino-cli board list`
> - Ran `arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> Upload succeeded and the ESP32 reset. I’m giving Wi-Fi a moment to come back, then I’ll query status and run a short print test with the new route.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `sleep 5 && uv run python ESP32-BTN_Printer/tools/printer_connect.py status --esp32 http://10.28.8.56`
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel --message 'HELLO ROLL' --esp32 http://10.28.8.56`
>
> </details>
>
> The new route reached the ESP32, but failed before printing at MTU negotiation. Since the fixed `ESP32 OK` worked earlier with full-width rows, I’m checking whether this is a firmware regression or just an overly strict MTU check after reconnect.
>
> <details><summary>Explored 1 file, 1 search, ran 1 command</summary>
>
> <details><summary>Explored 2 files, 1 search</summary>
>
> - Searched for `ensureBleMtu|setMTU|getMTU|exchangeMTU|connectPrinter|PRINTER_WRITE_CHUNK_SIZE|printerWritePacket` in `ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
>
> </details>
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel-status --esp32 http://10.28.8.56`
>
> <details><summary>Explored 2 files</summary>
>
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
>
> </details>
>
> </details>
>
> Found the cause: the old fixed probe connected first in `sendIlabelProbe`; the new direct `ilabel` route skipped that first connection before asking for MTU. I’m adding the connection at the start of `sendIlabelText`, then I’ll rebuild and re-upload.
>
> <details><summary>Edited 1 file, ran 1 command</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+5 -0)
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly && arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> </details>
>
> The second compile passed. Upload is in progress now; after the reset I’ll use the exact same `HELLO ROLL` test that just failed.
>
> <details><summary>Ran 1 command</summary>
>
> - Ran `sleep 5 && uv run python ESP32-BTN_Printer/tools/printer_connect.py test --protocol ilabel --message 'HELLO ROLL' --esp32 http://10.28.8.56`
>
> </details>
>
> The `HELLO ROLL` command completed successfully from the ESP32 side and returned the same header/status notifications as the working `ESP32 OK` test. I’m checking the diff now so I can summarize exactly what changed and leave the repo state clear.
>
> <details><summary>Explored 2 files, 1 search, ran 3 commands</summary>
>
> - Ran `git status --short`
>
> - Ran `git diff -- ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino ESP32-BTN_Printer/tools/printer_connect.py ESP32-BTN_Printer/README.md`
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py status --esp32 http://10.28.8.56`
>
> <details><summary>Explored 2 files, 1 search</summary>
>
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/config.example.h`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Searched for `PRINTER_DEFAULT_PROTOCOL` in `config.local.h`
>
> </details>
>
> </details>
>
> One more practical fix: the current firmware still reports `default_protocol: escpos`, so plain `/print` would use the silent path unless a query says `protocol=ilabel`. I’m changing the printer-only default to `ilabel` and re-uploading so the normal receipt endpoint uses the discovered protocol.
>
> <details><summary>Edited 2 files, ran 2 commands</summary>
>
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino` (+1 -1)
> - Wrote `./ESP32-BTN_Printer/ESP32_PrinterOnly/config.example.h` (+2 -2)
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly && arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
> - Ran `sleep 5 && uv run python ESP32-BTN_Printer/tools/printer_connect.py status --esp32 http://10.28.8.56`
>
> </details>
>
> The ESP32 now reports `default_protocol: ilabel`. I’m also changing the helper script’s default protocol to `ilabel`, so `printer_connect.py test` and `sample` use the working path unless you override it.
>
> <details><summary>Edited 1 file, explored 3 files, ran 4 commands</summary>
>
> - Wrote `./ESP32-BTN_Printer/tools/printer_connect.py` (+1 -1)
>
> - Ran `uv run python ESP32-BTN_Printer/tools/printer_connect.py test --message 'DEFAULT OK' --esp32 http://10.28.8.56`
>
> - Ran `git status --short`
>
> - Ran `python3 -m py_compile ESP32-BTN_Printer/tools/printer_connect.py`
>
> - Ran `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
>
> <details><summary>Explored 3 files</summary>
>
> - Read `./ESP32-BTN_Printer/tools/printer_connect.py`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino`
> - Read `./ESP32-BTN_Printer/ESP32_PrinterOnly/config.example.h`
>
> </details>
>
> </details>
</details>

Done. The ESP32 is now running the printer-only firmware with `ilabel` as the default print protocol.

Changed:
- Added generic iLabel roll-paper text printing in [ESP32_PrinterOnly.ino](./ESP32-BTN_Printer/ESP32_PrinterOnly/ESP32_PrinterOnly.ino:1011)
- Routed `/test-print?protocol=ilabel` and `/print` receipt text through that raster path
- Set printer-only default protocol to `ilabel` in [config.example.h](./ESP32-BTN_Printer/ESP32_PrinterOnly/config.example.h:34)
- Added CLI `--message` and defaulted helper protocol to `ilabel` in [printer_connect.py](./ESP32-BTN_Printer/tools/printer_connect.py:99)
- Updated README with the WP9509/iLabel roll-paper commands

Verified:
- `arduino-cli compile` passes
- firmware uploaded to `/dev/cu.usbserial-0001`
- ESP32 status reports `default_protocol: ilabel`
- this command returned `ok: true` with the expected `A5 ... status` notify bytes:

```bash
uv run python ESP32-BTN_Printer/tools/printer_connect.py test --message 'DEFAULT OK' --esp32 http://10.28.8.56
```

I left the unrelated existing repo changes in `src/`, `tests/`, screenshots, and `reports/` untouched.
