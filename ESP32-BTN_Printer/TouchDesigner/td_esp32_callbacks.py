"""TouchDesigner callbacks for the Oracle ESP32 button bridge.

Set esp32_bridge/source_switch:
    wifi = 0 -> use USB serial only
    wifi = 1 -> use Wi-Fi UDP only
"""

MAX_LOG_ROWS = 80
START_TOKEN = "START"
FLASH_FRAMES = 90
DEFAULT_COLOR = (0.67, 0.67, 0.67)
FLASH_COLOR = (0.0, 1.0, 0.18)
FLASH_TARGETS = (
    ".",
    "source_switch",
    "esp_ip",
    "udp_in",
    "serial_in",
    "status_log",
)


def onReceive(dat, rowIndex, message, byteData, peer=None):
    """Callback used by both UDP In DAT and Serial DAT."""
    text = _clean_message(message, byteData)
    if not text:
        return

    source = _source_label(dat, peer)
    source_kind = _source_kind(peer)
    selected = _selected_source(dat.parent())

    if _is_start_message(text):
        if source_kind == selected:
            _handle_start(dat, source, text)
        else:
            _append_log(dat, "IGNORED", source, f"selected={selected} message={text}")
    else:
        if source_kind == selected:
            _append_log(dat, "RX", source, text)
    return


def _clean_message(message, byteData):
    if message:
        return str(message).strip()
    if byteData:
        try:
            return bytes(byteData).decode("utf-8", "replace").strip()
        except Exception:
            return repr(byteData)
    return ""


def _source_label(dat, peer):
    if peer is not None and getattr(peer, "address", None):
        return "udp:" + str(peer.address)
    return "serial:" + dat.name


def _source_kind(peer):
    if peer is not None and getattr(peer, "address", None):
        return "wifi"
    return "usb"


def _selected_source(bridge):
    switch = bridge.op("source_switch")
    if switch is None:
        return "usb"

    try:
        channel = switch["wifi"]
        if hasattr(channel, "eval"):
            value = float(channel.eval())
        elif hasattr(channel, "val"):
            value = float(channel.val)
        else:
            value = float(channel)
    except Exception:
        return "usb"

    return "wifi" if value >= 0.5 else "usb"


def _is_start_message(text):
    upper = text.upper()
    return upper == START_TOKEN or "BUTTON PRESSED: START" in upper


def _handle_start(dat, source, text):
    bridge = dat.parent()
    count = int(bridge.fetch("start_count", 0)) + 1
    bridge.store("start_count", count)
    bridge.store("last_start_source", source)
    bridge.store("selected_source", _selected_source(bridge))
    bridge.store("last_start_frame", int(absTime.frame))
    bridge.store("last_start_message", text)

    _update_state_chop(bridge, count)
    _flash_notification(bridge)
    _append_log(dat, "START", source, text)

    hook = bridge.op("on_start")
    if hook is not None:
        run(hook, source, text, delayFrames=1)


def _update_state_chop(bridge, count):
    state = bridge.op("esp_ip")
    if state is None:
        return
    state.par.const0name = "start_count"
    state.par.const0value = count
    state.par.const1name = "last_start_frame"
    state.par.const1value = int(absTime.frame)
    state.par.const2name = "source_is_wifi"
    state.par.const2value = 1 if _selected_source(bridge) == "wifi" else 0


def _flash_notification(bridge):
    paths = []
    for target in FLASH_TARGETS:
        node = bridge if target == "." else bridge.op(target)
        if node is None:
            continue
        node.color = FLASH_COLOR
        paths.append(node.path)

    script = "\n".join(f"op({path!r}).color = {DEFAULT_COLOR!r}" for path in paths)
    if script:
        run(script, delayFrames=FLASH_FRAMES)


def _append_log(dat, event, source, message):
    table = dat.parent().op("status_log")
    if table is None:
        return

    if table.numRows == 0:
        table.appendRow(["frame", "event", "source", "message"])
    elif table[0, 0].val != "frame":
        table.insertRow(["frame", "event", "source", "message"], 0)

    table.appendRow([str(int(absTime.frame)), event, source, message])
    while table.numRows > MAX_LOG_ROWS + 1:
        table.deleteRow(1)

    print(f"Oracle ESP32 [{event}] {source} {message}")
