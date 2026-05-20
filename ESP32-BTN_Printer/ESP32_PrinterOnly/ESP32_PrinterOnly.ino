#include <Arduino.h>

#if __has_include("config.local.h")
#include "config.local.h"
#else
#include "config.example.h"
#endif

#include <ArduinoJson.h>
#include <WebServer.h>
#include <WiFi.h>
#include "mbedtls/base64.h"

#if USE_CLASSIC_SPP
#include "BluetoothSerial.h"
#else
#include <NimBLEDevice.h>
#endif

#ifndef PRINTER_WRITE_CHUNK_SIZE
#define PRINTER_WRITE_CHUNK_SIZE 20
#endif

#ifndef PRINTER_ALT_WRITE_CHAR_UUID
#define PRINTER_ALT_WRITE_CHAR_UUID ""
#endif

#ifndef PRINTER_NOTIFY_CHAR_UUID
#define PRINTER_NOTIFY_CHAR_UUID ""
#endif

#ifndef PRINTER_DEFAULT_PROTOCOL
#define PRINTER_DEFAULT_PROTOCOL "ilabel"
#endif

#ifndef PRINTER_CHUNK_DELAY_MS
#define PRINTER_CHUNK_DELAY_MS 10
#endif

#ifndef PRINTER_RESPONSE_CHUNK_DELAY_MS
#define PRINTER_RESPONSE_CHUNK_DELAY_MS 20
#endif

#ifndef BLE_NOTIFY_HEX_LIMIT
#define BLE_NOTIFY_HEX_LIMIT 512
#endif

#ifndef ILABEL_PRINT_WIDTH_DOTS
#define ILABEL_PRINT_WIDTH_DOTS 576
#endif

#ifndef ILABEL_MARGIN_ROWS
#define ILABEL_MARGIN_ROWS 40
#endif

#ifndef ILABEL_TRAILING_MARGIN_ROWS
#define ILABEL_TRAILING_MARGIN_ROWS (ILABEL_MARGIN_ROWS * 2)
#endif

#ifndef ILABEL_BLE_MTU
#define ILABEL_BLE_MTU ((ILABEL_PRINT_WIDTH_DOTS / 8) + 34)
#endif

#ifndef ILABEL_FLOW_TIMEOUT_MS
#define ILABEL_FLOW_TIMEOUT_MS 2500
#endif

#ifndef BOOT_TEST_PRINT_ENABLED
#define BOOT_TEST_PRINT_ENABLED 1
#endif

#ifndef BOOT_TEST_PRINT_DELAY_MS
#define BOOT_TEST_PRINT_DELAY_MS 5000
#endif

#ifndef BOOT_TEST_PRINT_RETRY_MS
#define BOOT_TEST_PRINT_RETRY_MS 10000
#endif

#ifndef BOOT_TEST_PRINT_MAX_ATTEMPTS
#define BOOT_TEST_PRINT_MAX_ATTEMPTS 6
#endif

#ifndef BOOT_TEST_PRINT_MESSAGE
#define BOOT_TEST_PRINT_MESSAGE "ORACLE PRINTER READY"
#endif

WebServer server(HTTP_PORT);

#if USE_CLASSIC_SPP
BluetoothSerial SerialBT;
#else
NimBLEClient* bleClient = nullptr;
NimBLERemoteCharacteristic* printerChar = nullptr;
NimBLERemoteCharacteristic* notifyChar = nullptr;
String bleNotifyHex;
uint32_t bleNotifyPackets = 0;
#endif

String pendingIlabelRasterRle;
uint16_t pendingIlabelRasterWidth = 0;
uint16_t pendingIlabelRasterHeight = 0;
uint32_t lastWifiCheckMs = 0;
uint32_t nextBootTestPrintMs = 0;
uint8_t bootTestPrintAttempts = 0;
bool bootTestPrinted = false;
bool bootTestPrintExhausted = false;

void connectWiFi();
void setupHttpServer();
void scheduleBootTestPrint();
void handleBootTestPrint();
void handleRoot();
void handleStatus();
void handleConnect();
void handleWake();
void handleTestPrint();
void handleRaw();
void handleIlabelTest();
void handleIlabelRasterBegin();
void handleIlabelRasterChunk();
void handleIlabelRasterPrint();
void handleProbePrint();
void handlePrint();
void handleNotFound();
bool connectPrinter();
bool printerWrite(const uint8_t* data, size_t len);
bool printerWriteMode(const uint8_t* data, size_t len, bool withResponse);
bool printerWritePacket(const uint8_t* data, size_t len, bool withResponse);
bool printerWriteByte(uint8_t value);
bool probeWrite(const char* characteristicUuid, const uint8_t* data, size_t len, bool withResponse);
#if !USE_CLASSIC_SPP
bool ensureBleMtu(uint16_t mtu);
void subscribePrinterNotifications(NimBLERemoteService* service);
void printerNotifyCallback(NimBLERemoteCharacteristic* characteristic, uint8_t* data, size_t len, bool isNotify);
void clearBleNotifications();
String snapshotBleNotifications(uint32_t& packets);
#endif
bool sendProtocolText(const String& protocol, const String& text, String& error, bool withResponse = false, const char* characteristicUuid = "");
String buildProtocolPayload(const String& protocol, const String& text);
String buildCatCommand(uint8_t command, const uint8_t* data, size_t len);
String buildCatCommandD8(uint8_t command, uint8_t data);
String buildCatCommandD16(uint8_t command, uint16_t data);
String buildCatProbePayload(const String& protocol);
uint8_t catCrc8(const uint8_t* data, size_t len);
bool sendIlabelProbe(const String& protocol, String& error, String& notifyHex, uint32_t& notifyPackets);
bool sendIlabelText(const String& text, String& error);
bool sendIlabelRasterRle(const char* encoded, uint16_t sourceWidth, uint16_t height, String& error);
bool writeIlabelByte(uint8_t value, bool withResponse = false);
bool writeIlabelHeader(uint16_t height, uint16_t offset, uint8_t state, uint8_t paperType, uint8_t density, bool withResponse = false);
bool writeIlabelRow(uint16_t offset, const uint8_t* row, size_t rowLen, bool withResponse = false);
uint8_t wrapIlabelText(const String& text, String lines[], uint8_t maxLines, uint8_t charsPerLine);
void buildIlabelTextRow(const String lines[], uint8_t lineCount, uint16_t y, uint8_t* row, size_t rowBytes, uint8_t scale);
uint8_t ilabelGlyphRow(char c, uint8_t row);
void setIlabelPixel(uint8_t* row, size_t rowBytes, uint16_t x);
#if !USE_CLASSIC_SPP
bool waitForBleNotification(const char* prefix, uint32_t timeoutMs);
#endif
String buildReceiptText(JsonDocument& doc);
bool printReceipt(JsonDocument& doc, const String& protocol, String& error);
bool printIlabelReceipt(JsonDocument& doc, String& error);
bool printEscposReceipt(JsonDocument& doc, String& error);
void printLine(const String& line);
void printWrapped(const String& text, uint8_t width = 32);
void printQr(const String& url);
String cleanText(const String& input);
String cleanProtocolName(String value);
String jsonEscape(const String& input);
String escapeLabelText(const String& input);
String themesToText(JsonVariant themes);
String measureToText(JsonVariant measures, const char* key);
bool decodeBase64ToPrinter(const char* encoded, String& error);
bool decodeBase64Alloc(const char* encoded, uint8_t*& decoded, size_t& decodedLen, String& error, const char* label);
bool decodeHexToBytes(const String& hex, uint8_t*& bytes, size_t& len, String& error);
int hexValue(char c);
void setStatusLed(bool on);

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(SERIAL_STARTUP_DELAY_MS);
  Serial.println();
  Serial.println("========================================");
  Serial.println("Oracle ESP32 printer-only bridge starting");
  Serial.printf("Serial baud: %lu\n", static_cast<unsigned long>(SERIAL_BAUD));

#if ENABLE_STATUS_LED
  pinMode(STATUS_LED_PIN, OUTPUT);
  setStatusLed(false);
#endif

  connectWiFi();

#if USE_CLASSIC_SPP
  SerialBT.begin("OracleESP32_PrinterOnly", true);
  Serial.println("Printer transport: Bluetooth Classic SPP");
#else
  NimBLEDevice::init("OracleESP32_PrinterOnly");
  NimBLEDevice::setMTU(ILABEL_BLE_MTU);
  NimBLEDevice::setPower(3);
  Serial.println("Printer transport: BLE client");
#endif

  setupHttpServer();
  Serial.printf("HTTP server ready on port %d\n", HTTP_PORT);
  scheduleBootTestPrint();
}

void loop() {
  server.handleClient();
  handleBootTestPrint();

  const uint32_t now = millis();
  if (now - lastWifiCheckMs > 5000) {
    lastWifiCheckMs = now;
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("Wi-Fi disconnected; reconnecting");
      WiFi.reconnect();
      setStatusLed(false);
    } else {
      setStatusLed(true);
    }
  }
}

void scheduleBootTestPrint() {
#if BOOT_TEST_PRINT_ENABLED
  nextBootTestPrintMs = millis() + BOOT_TEST_PRINT_DELAY_MS;
  bootTestPrintAttempts = 0;
  bootTestPrinted = false;
  bootTestPrintExhausted = false;
  Serial.printf("Boot test print scheduled in %lu ms\n", static_cast<unsigned long>(BOOT_TEST_PRINT_DELAY_MS));
#else
  nextBootTestPrintMs = 0;
  bootTestPrintAttempts = 0;
  bootTestPrinted = false;
  bootTestPrintExhausted = true;
  Serial.println("Boot test print disabled");
#endif
}

void handleBootTestPrint() {
#if BOOT_TEST_PRINT_ENABLED
  if (bootTestPrinted || bootTestPrintExhausted) {
    return;
  }

  const uint32_t now = millis();
  if (static_cast<int32_t>(now - nextBootTestPrintMs) < 0) {
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    nextBootTestPrintMs = now + BOOT_TEST_PRINT_RETRY_MS;
    Serial.println("Boot test print waiting for Wi-Fi");
    return;
  }

  bootTestPrintAttempts++;
  String error;
  Serial.printf("Boot test print attempt %u/%u\n", bootTestPrintAttempts, static_cast<unsigned int>(BOOT_TEST_PRINT_MAX_ATTEMPTS));
  if (sendIlabelText(String(BOOT_TEST_PRINT_MESSAGE), error)) {
    bootTestPrinted = true;
    Serial.println("Boot test print complete");
    return;
  }

  Serial.printf("Boot test print failed: %s\n", error.c_str());
  if (bootTestPrintAttempts >= BOOT_TEST_PRINT_MAX_ATTEMPTS) {
    bootTestPrintExhausted = true;
    Serial.println("Boot test print attempts exhausted");
    return;
  }
  nextBootTestPrintMs = now + BOOT_TEST_PRINT_RETRY_MS;
#endif
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("Joining Wi-Fi SSID '%s'", WIFI_SSID);

  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < WIFI_CONNECT_TIMEOUT_MS) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("Wi-Fi connected: %s\n", WiFi.localIP().toString().c_str());
    setStatusLed(true);
  } else {
    Serial.println("Wi-Fi connection timed out; firmware will keep retrying");
    setStatusLed(false);
  }
}

void setupHttpServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/connect", HTTP_POST, handleConnect);
  server.on("/wake", HTTP_POST, handleWake);
  server.on("/test-print", HTTP_POST, handleTestPrint);
  server.on("/raw", HTTP_POST, handleRaw);
  server.on("/ilabel-test", HTTP_POST, handleIlabelTest);
  server.on("/ilabel-raster-begin", HTTP_POST, handleIlabelRasterBegin);
  server.on("/ilabel-raster-chunk", HTTP_POST, handleIlabelRasterChunk);
  server.on("/ilabel-raster-print", HTTP_POST, handleIlabelRasterPrint);
  server.on("/probe-print", HTTP_POST, handleProbePrint);
  server.on("/print", HTTP_POST, handlePrint);
  server.onNotFound(handleNotFound);
  server.begin();
}

void handleRoot() {
  server.send(
    200,
    "text/plain",
    "Oracle ESP32 printer-only bridge\n"
    "GET  /status\n"
    "POST /connect\n"
    "POST /wake\n"
    "POST /test-print?protocol=escpos\n"
    "POST /raw JSON {\"hex\":\"...\"}\n"
    "POST /ilabel-test?protocol=ilabel-status\n"
    "POST /ilabel-raster-begin?width=576&height=1000\n"
    "POST /ilabel-raster-chunk?data=...\n"
    "POST /ilabel-raster-print\n"
    "POST /probe-print\n"
    "POST /print JSON receipt\n"
  );
}

void handleStatus() {
  String body = "{";
  body += "\"wifi\":\"";
  body += WiFi.status() == WL_CONNECTED ? "connected" : "disconnected";
  body += "\",\"ip\":\"";
  body += WiFi.localIP().toString();
  body += "\",\"printer\":\"";
#if USE_CLASSIC_SPP
  body += SerialBT.connected() ? "connected" : "disconnected";
#else
  body += (bleClient && bleClient->isConnected() && printerChar) ? "connected" : "disconnected";
#endif
  body += "\",\"transport\":\"";
  body += USE_CLASSIC_SPP ? "classic" : "ble";
  body += "\",\"default_protocol\":\"";
  body += PRINTER_DEFAULT_PROTOCOL;
  body += "\",\"boot_test\":\"";
#if BOOT_TEST_PRINT_ENABLED
  if (bootTestPrinted) {
    body += "printed";
  } else if (bootTestPrintExhausted) {
    body += "exhausted";
  } else {
    body += "pending";
  }
#else
  body += "disabled";
#endif
  body += "\",\"boot_test_attempts\":";
  body += String(bootTestPrintAttempts);
  body += ",\"write_char\":\"";
#if USE_CLASSIC_SPP
  body += "classic";
#else
  body += printerChar ? printerChar->getUUID().toString().c_str() : "";
#endif
  body += "\",\"notify_char\":\"";
#if USE_CLASSIC_SPP
  body += "";
#else
  body += notifyChar ? notifyChar->getUUID().toString().c_str() : "";
#endif
  body += "\"}";
  server.send(200, "application/json", body);
}

void handleConnect() {
  const bool ok = connectPrinter();
  String response = "{\"ok\":";
  response += ok ? "true" : "false";
  response += ",\"printer\":\"";
#if USE_CLASSIC_SPP
  response += SerialBT.connected() ? "connected" : "disconnected";
#else
  response += (bleClient && bleClient->isConnected() && printerChar) ? "connected" : "disconnected";
  response += "\",\"write_char\":\"";
  response += printerChar ? printerChar->getUUID().toString().c_str() : "";
  response += "\",\"notify_char\":\"";
  response += notifyChar ? notifyChar->getUUID().toString().c_str() : "";
#endif
  response += "\"}";
  server.send(ok ? 200 : 503, "application/json", response);
}

void handleWake() {
  String error;
  const bool ok = sendProtocolText("escpos", "", error);
  if (!ok) {
    String response = "{\"ok\":false,\"error\":\"";
    response += jsonEscape(error);
    response += "\"}";
    server.send(503, "application/json", response);
    return;
  }
  server.send(200, "application/json", "{\"ok\":true,\"sent\":\"escpos-init\"}");
}

void handleTestPrint() {
  String protocol = cleanProtocolName(server.hasArg("protocol") ? server.arg("protocol") : PRINTER_DEFAULT_PROTOCOL);
  const String message = server.hasArg("message")
    ? server.arg("message")
    : String("Oracle printer test\nprotocol=") + protocol + "\nIf this prints, the ESP32 can write printable bytes.";
  const bool withResponse = server.hasArg("response") && server.arg("response") != "0";
  const String characteristic = server.hasArg("char") ? server.arg("char") : "";

  String error;
  if (protocol == "ilabel" || protocol == "ilabel-text") {
    String notifyHex;
    uint32_t notifyPackets = 0;
#if !USE_CLASSIC_SPP
    clearBleNotifications();
#endif
    const bool ok = sendIlabelText(message, error);
#if !USE_CLASSIC_SPP
    notifyHex = snapshotBleNotifications(notifyPackets);
#endif
    if (!ok) {
      String response = "{\"ok\":false,\"error\":\"";
      response += jsonEscape(error);
      response += "\"}";
      server.send(503, "application/json", response);
      return;
    }

    String response = "{\"ok\":true,\"printed\":true,\"protocol\":\"";
    response += protocol;
    response += "\",\"notify_packets\":";
    response += String(notifyPackets);
    response += ",\"notify\":\"";
    response += notifyHex;
    response += "\"}";
    server.send(200, "application/json", response);
    return;
  }

  if (protocol.startsWith("ilabel")) {
    String notifyHex;
    uint32_t notifyPackets = 0;
    const bool ok = sendIlabelProbe(protocol, error, notifyHex, notifyPackets);
    if (!ok) {
      String response = "{\"ok\":false,\"error\":\"";
      response += jsonEscape(error);
      response += "\"}";
      server.send(503, "application/json", response);
      return;
    }

    String response = "{\"ok\":true,\"printed\":true,\"protocol\":\"";
    response += protocol;
    response += "\",\"notify_packets\":";
    response += String(notifyPackets);
    response += ",\"notify\":\"";
    response += notifyHex;
    response += "\"}";
    server.send(200, "application/json", response);
    return;
  }

  const bool ok = sendProtocolText(protocol, message, error, withResponse, characteristic.c_str());
  if (!ok) {
    String response = "{\"ok\":false,\"error\":\"";
    response += jsonEscape(error);
    response += "\"}";
    server.send(503, "application/json", response);
    return;
  }

  String response = "{\"ok\":true,\"printed\":true,\"protocol\":\"";
  response += protocol;
  response += "\",\"mode\":\"";
  response += withResponse ? "write" : "noresp";
  response += "\"}";
  server.send(200, "application/json", response);
}

void handleRaw() {
  String hex;
  bool withResponse = server.hasArg("response") && server.arg("response") != "0";
  String characteristic = server.hasArg("char") ? server.arg("char") : "";

  if (server.hasArg("hex")) {
    hex = server.arg("hex");
  } else if (server.hasArg("plain")) {
    String body = server.arg("plain");
    body.trim();
    if (body.startsWith("{")) {
      DynamicJsonDocument doc(4096);
      DeserializationError jsonError = deserializeJson(doc, body);
      if (jsonError) {
        String response = "{\"ok\":false,\"error\":\"invalid JSON: ";
        response += jsonEscape(jsonError.c_str());
        response += "\"}";
        server.send(400, "application/json", response);
        return;
      }
      hex = doc["hex"] | "";
      if (doc["response"].is<bool>()) {
        withResponse = doc["response"].as<bool>();
      }
      if (doc["char"].is<const char*>()) {
        characteristic = String(doc["char"].as<const char*>());
      }
    } else {
      hex = body;
    }
  }

  uint8_t* bytes = nullptr;
  size_t len = 0;
  String error;
  if (!decodeHexToBytes(hex, bytes, len, error)) {
    String response = "{\"ok\":false,\"error\":\"";
    response += jsonEscape(error);
    response += "\"}";
    server.send(400, "application/json", response);
    return;
  }

#if !USE_CLASSIC_SPP
  clearBleNotifications();
#endif
  const bool ok = strlen(characteristic.c_str()) > 0
    ? probeWrite(characteristic.c_str(), bytes, len, withResponse)
    : printerWriteMode(bytes, len, withResponse);
  free(bytes);

  if (!ok) {
    server.send(503, "application/json", "{\"ok\":false,\"error\":\"raw write failed\"}");
    return;
  }

  String response = "{\"ok\":true,\"bytes\":";
  response += String(static_cast<unsigned long>(len));
  response += ",\"mode\":\"";
  response += withResponse ? "write" : "noresp";
#if !USE_CLASSIC_SPP
  delay(350);
  uint32_t notifyPackets = 0;
  const String notifyHex = snapshotBleNotifications(notifyPackets);
  response += "\",\"notify_packets\":";
  response += String(notifyPackets);
  response += ",\"notify\":\"";
  response += notifyHex;
#endif
  response += "\"}";
  server.send(200, "application/json", response);
}

void handleIlabelTest() {
  String protocol = cleanProtocolName(server.hasArg("protocol") ? server.arg("protocol") : "ilabel-status");
  String error;
  String notifyHex;
  uint32_t notifyPackets = 0;
  const bool ok = sendIlabelProbe(protocol, error, notifyHex, notifyPackets);
  if (!ok) {
    String response = "{\"ok\":false,\"error\":\"";
    response += jsonEscape(error);
    response += "\"}";
    server.send(503, "application/json", response);
    return;
  }

  String response = "{\"ok\":true,\"protocol\":\"";
  response += protocol;
  response += "\",\"notify_packets\":";
  response += String(notifyPackets);
  response += ",\"notify\":\"";
  response += notifyHex;
  response += "\"}";
  server.send(200, "application/json", response);
}

void handleIlabelRasterBegin() {
  pendingIlabelRasterRle = "";
  pendingIlabelRasterWidth = static_cast<uint16_t>(server.hasArg("width") ? server.arg("width").toInt() : ILABEL_PRINT_WIDTH_DOTS);
  pendingIlabelRasterHeight = static_cast<uint16_t>(server.hasArg("height") ? server.arg("height").toInt() : 0);
  const uint32_t expected = server.hasArg("length") ? static_cast<uint32_t>(server.arg("length").toInt()) : 0;
  if (pendingIlabelRasterWidth == 0 || pendingIlabelRasterWidth > ILABEL_PRINT_WIDTH_DOTS || pendingIlabelRasterWidth % 8 != 0 || pendingIlabelRasterHeight == 0) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"invalid raster dimensions\"}");
    return;
  }
  if (expected > 0) {
    pendingIlabelRasterRle.reserve(expected + 8);
  }
  String response = "{\"ok\":true,\"width\":";
  response += String(pendingIlabelRasterWidth);
  response += ",\"height\":";
  response += String(pendingIlabelRasterHeight);
  response += "}";
  server.send(200, "application/json", response);
}

void handleIlabelRasterChunk() {
  if (pendingIlabelRasterWidth == 0 || pendingIlabelRasterHeight == 0) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"call /ilabel-raster-begin first\"}");
    return;
  }
  if (!server.hasArg("data")) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"missing data chunk\"}");
    return;
  }
  pendingIlabelRasterRle += server.arg("data");
  String response = "{\"ok\":true,\"received\":";
  response += String(static_cast<unsigned long>(pendingIlabelRasterRle.length()));
  response += "}";
  server.send(200, "application/json", response);
}

void handleIlabelRasterPrint() {
  if (pendingIlabelRasterWidth == 0 || pendingIlabelRasterHeight == 0 || pendingIlabelRasterRle.length() == 0) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"no pending iLabel raster\"}");
    return;
  }

  String error;
  const bool ok = sendIlabelRasterRle(pendingIlabelRasterRle.c_str(), pendingIlabelRasterWidth, pendingIlabelRasterHeight, error);
  if (!ok) {
    String response = "{\"ok\":false,\"error\":\"";
    response += jsonEscape(error);
    response += "\"}";
    server.send(503, "application/json", response);
    return;
  }

  pendingIlabelRasterRle = "";
  pendingIlabelRasterWidth = 0;
  pendingIlabelRasterHeight = 0;
  server.send(200, "application/json", "{\"ok\":true,\"printed\":true,\"protocol\":\"ilabel-raster\"}");
}

void handleProbePrint() {
  struct ProbePayload {
    const char* name;
    const char* text;
  };

  const ProbePayload payloads[] = {
    {"raw", "WP9509 RAW TEXT TEST"},
    {"escpos", "WP9509 ESC/POS TEST"},
    {"tspl", "WP9509 TSPL TEST"},
    {"cpcl", "WP9509 CPCL TEST"},
    {"zpl", "WP9509 ZPL TEST"},
    {"catstate", "WP9509 CAT STATE TEST"},
    {"catfeed", "WP9509 CAT FEED TEST"},
    {"catblack", "WP9509 CAT BLACK TEST"},
    {"ilabel", "WP9509 ILABEL TEXT"},
    {"ilabel-status", "WP9509 ILABEL STATUS"},
    {"ilabel-info", "WP9509 ILABEL INFO"},
    {"ilabel-text", "WP9509 ILABEL TEXT"},
    {"ilabel-roll", "WP9509 ILABEL ROLL"},
    {"ilabel-black", "WP9509 ILABEL BLACK"},
  };

#if USE_CLASSIC_SPP
  String response = "{\"ok\":true,\"attempts\":[";
  bool first = true;
  for (const ProbePayload& payload : payloads) {
    String error;
    const bool ok = sendProtocolText(payload.name, payload.text, error);
    if (!first) response += ",";
    first = false;
    response += "{\"transport\":\"classic\",\"protocol\":\"";
    response += payload.name;
    response += "\",\"ok\":";
    response += ok ? "true" : "false";
    response += ",\"error\":\"";
    response += jsonEscape(error);
    response += "\"}";
    delay(350);
  }
  response += "]}";
  server.send(200, "application/json", response);
#else
  const char* characteristics[] = {
    PRINTER_WRITE_CHAR_UUID,
    PRINTER_ALT_WRITE_CHAR_UUID,
  };

  String response = "{\"ok\":true,\"attempts\":[";
  bool first = true;
  for (const char* characteristic : characteristics) {
    if (!strlen(characteristic)) {
      continue;
    }
    for (uint8_t responseMode = 0; responseMode < 2; responseMode++) {
      const bool withResponse = responseMode == 1;
      const char* modeText = withResponse ? "write" : "noresp";
      for (const ProbePayload& payload : payloads) {
        if (String(payload.name).startsWith("ilabel")) {
          continue;
        }
        const String testText = String(payload.text) + "\nchar=" + String(characteristic) + "\nmode=" + modeText;
        const String bytes = buildProtocolPayload(payload.name, testText);
        clearBleNotifications();
        const bool ok = probeWrite(characteristic, reinterpret_cast<const uint8_t*>(bytes.c_str()), bytes.length(), withResponse);
        delay(350);
        uint32_t notifyPackets = 0;
        const String notifyHex = snapshotBleNotifications(notifyPackets);
        Serial.printf("Probe print %s %s %s: %s\n", characteristic, modeText, payload.name, ok ? "ok" : "failed");
        if (notifyHex.length()) {
          Serial.printf("Probe notify packets=%lu bytes=%s\n", static_cast<unsigned long>(notifyPackets), notifyHex.c_str());
        }

        if (!first) response += ",";
        first = false;
        response += "{\"char\":\"";
        response += characteristic;
        response += "\",\"mode\":\"";
        response += modeText;
        response += "\",\"protocol\":\"";
        response += payload.name;
        response += "\",\"ok\":";
        response += ok ? "true" : "false";
        response += ",\"notify_packets\":";
        response += String(notifyPackets);
        response += ",\"notify\":\"";
        response += notifyHex;
        response += "\"}";
      }
    }
  }

  const char* ilabelProtocols[] = {
    "ilabel",
    "ilabel-status",
    "ilabel-info",
    "ilabel-cancel",
    "ilabel-text",
    "ilabel-roll",
    "ilabel-black",
  };
  for (const char* protocol : ilabelProtocols) {
    String error;
    String notifyHex;
    uint32_t notifyPackets = 0;
    const bool ok = sendIlabelProbe(protocol, error, notifyHex, notifyPackets);
    Serial.printf("Probe print %s: %s\n", protocol, ok ? "ok" : "failed");

    if (!first) response += ",";
    first = false;
    response += "{\"char\":\"";
    response += printerChar ? printerChar->getUUID().toString().c_str() : "";
    response += "\",\"mode\":\"sequence\",\"protocol\":\"";
    response += protocol;
    response += "\",\"ok\":";
    response += ok ? "true" : "false";
    response += ",\"notify_packets\":";
    response += String(notifyPackets);
    response += ",\"notify\":\"";
    response += notifyHex;
    response += "\",\"error\":\"";
    response += jsonEscape(error);
    response += "\"}";
    delay(500);
  }

  if (bleClient && bleClient->isConnected()) {
    NimBLERemoteService* service = bleClient->getService(PRINTER_SERVICE_UUID);
    if (service) {
      printerChar = service->getCharacteristic(PRINTER_WRITE_CHAR_UUID);
    }
  }

  response += "]}";
  server.send(200, "application/json", response);
#endif
}

void handlePrint() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"missing JSON body\"}");
    return;
  }

  String body = server.arg("plain");
  if (body.length() > 120000) {
    server.send(413, "application/json", "{\"ok\":false,\"error\":\"JSON body too large\"}");
    return;
  }

  DynamicJsonDocument doc(131072);
  DeserializationError jsonError = deserializeJson(doc, body);
  if (jsonError) {
    String error = "{\"ok\":false,\"error\":\"invalid JSON: ";
    error += jsonEscape(jsonError.c_str());
    error += "\"}";
    server.send(400, "application/json", error);
    return;
  }

  String protocol = cleanProtocolName(server.hasArg("protocol") ? server.arg("protocol") : PRINTER_DEFAULT_PROTOCOL);
  const String sessionUrl = cleanText(doc["session_url"] | "");
  if (!sessionUrl.length()) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"missing session_url for mandatory receipt QR\"}");
    return;
  }
  String error;
  if (!printReceipt(doc, protocol, error)) {
    String response = "{\"ok\":false,\"error\":\"";
    response += jsonEscape(error);
    response += "\"}";
    server.send(503, "application/json", response);
    return;
  }

  String response = "{\"ok\":true,\"printed\":true,\"protocol\":\"";
  response += protocol;
  response += "\"}";
  server.send(200, "application/json", response);
}

void handleNotFound() {
  server.send(404, "application/json", "{\"ok\":false,\"error\":\"not found\"}");
}

#if !USE_CLASSIC_SPP
void clearBleNotifications() {
  bleNotifyHex = "";
  bleNotifyPackets = 0;
}

String snapshotBleNotifications(uint32_t& packets) {
  packets = bleNotifyPackets;
  return bleNotifyHex;
}

bool waitForBleNotification(const char* prefix, uint32_t timeoutMs) {
  const String wanted = String(prefix);
  const uint32_t started = millis();
  while (millis() - started < timeoutMs) {
    if (bleNotifyHex.length()) {
      if (!wanted.length() || bleNotifyHex.startsWith(wanted)) {
        return true;
      }
      Serial.printf("Unexpected BLE notify while waiting for %s: %s\n", prefix, bleNotifyHex.c_str());
      return false;
    }
    delay(10);
  }
  return false;
}

void printerNotifyCallback(NimBLERemoteCharacteristic* characteristic, uint8_t* data, size_t len, bool isNotify) {
  (void)characteristic;
  (void)isNotify;
  bleNotifyPackets++;

  for (size_t i = 0; i < len; i++) {
    if (bleNotifyHex.length() + 3 >= BLE_NOTIFY_HEX_LIMIT) {
      return;
    }
    if (bleNotifyHex.length()) {
      bleNotifyHex += " ";
    }
    char byteHex[3];
    snprintf(byteHex, sizeof(byteHex), "%02X", data[i]);
    bleNotifyHex += byteHex;
  }

}
#endif

bool sendProtocolText(const String& protocol, const String& text, String& error, bool withResponse, const char* characteristicUuid) {
  const String cleanProtocol = cleanProtocolName(protocol);
  const String payload = buildProtocolPayload(cleanProtocol, text);
  if (!payload.length()) {
    error = "unsupported protocol: " + protocol;
    return false;
  }
  if (strlen(characteristicUuid) > 0) {
    if (!probeWrite(characteristicUuid, reinterpret_cast<const uint8_t*>(payload.c_str()), payload.length(), withResponse)) {
      error = "write failed for characteristic " + String(characteristicUuid);
      return false;
    }
    return true;
  }
  if (!printerWriteMode(reinterpret_cast<const uint8_t*>(payload.c_str()), payload.length(), withResponse)) {
    error = "printer write failed";
    return false;
  }
  return true;
}

String buildProtocolPayload(const String& protocol, const String& text) {
  const String clean = cleanText(text);
  String payload;

  if (protocol == "raw") {
    payload = clean;
    payload += "\r\n\r\n";
    return payload;
  }

  if (protocol == "escpos") {
    payload += "\x1B@";
    payload += clean;
    payload += "\n\n\n";
    return payload;
  }

  if (protocol == "tspl") {
    payload += "SIZE 58 mm,40 mm\r\n";
    payload += "GAP 2 mm,0\r\n";
    payload += "CLS\r\n";
    int y = 20;
    String remaining = clean;
    remaining.replace("\r", "\n");
    while (remaining.length() && y <= 300) {
      int next = remaining.indexOf('\n');
      String line = next >= 0 ? remaining.substring(0, next) : remaining;
      line.trim();
      if (line.length()) {
        payload += "TEXT 20,";
        payload += String(y);
        payload += ",\"TSS24.BF2\",0,1,1,\"";
        payload += escapeLabelText(line.substring(0, 34));
        payload += "\"\r\n";
        y += 32;
      }
      if (next < 0) break;
      remaining = remaining.substring(next + 1);
    }
    payload += "PRINT 1\r\n";
    return payload;
  }

  if (protocol == "cpcl") {
    payload += "! 0 200 200 320 1\r\n";
    int y = 30;
    String remaining = clean;
    remaining.replace("\r", "\n");
    while (remaining.length() && y <= 260) {
      int next = remaining.indexOf('\n');
      String line = next >= 0 ? remaining.substring(0, next) : remaining;
      line.trim();
      if (line.length()) {
        payload += "TEXT 4 0 30 ";
        payload += String(y);
        payload += " ";
        payload += escapeLabelText(line.substring(0, 34));
        payload += "\r\n";
        y += 32;
      }
      if (next < 0) break;
      remaining = remaining.substring(next + 1);
    }
    payload += "FORM\r\nPRINT\r\n";
    return payload;
  }

  if (protocol == "zpl") {
    payload += "^XA";
    int y = 30;
    String remaining = clean;
    remaining.replace("\r", "\n");
    while (remaining.length() && y <= 260) {
      int next = remaining.indexOf('\n');
      String line = next >= 0 ? remaining.substring(0, next) : remaining;
      line.trim();
      if (line.length()) {
        payload += "^FO30,";
        payload += String(y);
        payload += "^ADN,18,10^FD";
        payload += escapeLabelText(line.substring(0, 34));
        payload += "^FS";
        y += 32;
      }
      if (next < 0) break;
      remaining = remaining.substring(next + 1);
    }
    payload += "^XZ\r\n";
    return payload;
  }

  if (protocol == "catstate" || protocol == "catfeed" || protocol == "catblack") {
    return buildCatProbePayload(protocol);
  }

  return "";
}

String buildCatCommand(uint8_t command, const uint8_t* data, size_t len) {
  String payload;
  payload.reserve(len + 8);
  payload += static_cast<char>(0x51);
  payload += static_cast<char>(0x78);
  payload += static_cast<char>(command);
  payload += static_cast<char>(0x00);
  payload += static_cast<char>(len & 0xFF);
  payload += static_cast<char>((len >> 8) & 0xFF);
  for (size_t i = 0; i < len; i++) {
    payload += static_cast<char>(data[i]);
  }
  payload += static_cast<char>(catCrc8(data, len));
  payload += static_cast<char>(0xFF);
  return payload;
}

String buildCatCommandD8(uint8_t command, uint8_t data) {
  return buildCatCommand(command, &data, 1);
}

String buildCatCommandD16(uint8_t command, uint16_t data) {
  uint8_t bytes[] = {
    static_cast<uint8_t>(data & 0xFF),
    static_cast<uint8_t>((data >> 8) & 0xFF),
  };
  return buildCatCommand(command, bytes, sizeof(bytes));
}

String buildCatProbePayload(const String& protocol) {
  String payload;

  payload += buildCatCommandD8(0xA3, 0x00);  // request device state
  payload += buildCatCommandD8(0xA4, 0x33);  // quality

  if (protocol == "catstate") {
    payload += buildCatCommandD8(0xA8, 0x00);  // request device info
    return payload;
  }

  if (protocol == "catfeed") {
    payload += buildCatCommandD8(0xA1, 0x50);  // feed paper
    payload += buildCatCommandD8(0xA3, 0x00);
    return payload;
  }

  const uint8_t latticeStart[] = {
    0xAA, 0x55, 0x17, 0x38, 0x44, 0x5F, 0x5F, 0x5F, 0x44, 0x38, 0x2C
  };
  const uint8_t latticeEnd[] = {
    0xAA, 0x55, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x17
  };
  payload += buildCatCommand(0xA6, latticeStart, sizeof(latticeStart));
  payload += buildCatCommandD16(0xAF, 12000); // print energy
  payload += buildCatCommandD8(0xBE, 0x00);   // image mode

  uint8_t blackLine[48];
  memset(blackLine, 0xFF, sizeof(blackLine));
  for (uint8_t i = 0; i < 16; i++) {
    payload += buildCatCommand(0xA2, blackLine, sizeof(blackLine));
  }

  payload += buildCatCommandD8(0xA1, 0x40);
  payload += buildCatCommand(0xA6, latticeEnd, sizeof(latticeEnd));
  payload += buildCatCommandD8(0xA3, 0x00);
  return payload;
}

uint8_t catCrc8(const uint8_t* data, size_t len) {
  uint8_t crc = 0;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; bit++) {
      crc = (crc & 0x80) ? static_cast<uint8_t>((crc << 1) ^ 0x07) : static_cast<uint8_t>(crc << 1);
    }
  }
  return crc;
}

bool sendIlabelProbe(const String& protocol, String& error, String& notifyHex, uint32_t& notifyPackets) {
  notifyHex = "";
  notifyPackets = 0;
  if (!connectPrinter()) {
    error = "printer not connected";
    return false;
  }

#if !USE_CLASSIC_SPP
  clearBleNotifications();
#endif

  const String cleanProtocol = cleanProtocolName(protocol);
  if (cleanProtocol == "ilabel-status") {
    if (!writeIlabelByte(0x01)) {
      error = "failed to write iLabel status command";
      return false;
    }
    delay(700);
  } else if (cleanProtocol == "ilabel-info") {
    if (!writeIlabelByte(0xAC)) {
      error = "failed to write iLabel info command";
      return false;
    }
    delay(700);
  } else if (cleanProtocol == "ilabel-cancel") {
    if (!writeIlabelByte(0x04)) {
      error = "failed to write iLabel cancel command";
      return false;
    }
    delay(700);
  } else if (cleanProtocol == "ilabel" || cleanProtocol == "ilabel-text") {
    if (!sendIlabelText("ESP32 OK", error)) {
      return false;
    }
  } else if (cleanProtocol == "ilabel-roll" || cleanProtocol == "ilabel-black") {
    const uint8_t paperType = 1; // iLabel continuous roll paper.
    const uint16_t height = 16;
    const uint8_t density = 39;
    constexpr size_t rowBytes = ILABEL_PRINT_WIDTH_DOTS / 8;
    uint8_t row[rowBytes];

#if !USE_CLASSIC_SPP
    if (!ensureBleMtu(rowBytes + 4 + 3)) {
      error = "failed to negotiate iLabel BLE MTU";
      return false;
    }
#endif

    if (!writeIlabelByte(0x04)) {
      error = "failed to write iLabel cancel before print";
      return false;
    }
    delay(300);

    if (!writeIlabelByte(0x01)) {
      error = "failed to write iLabel status before print";
      return false;
    }
    delay(500);

#if !USE_CLASSIC_SPP
    clearBleNotifications();
#endif
    if (!writeIlabelHeader(height, 0, 0, paperType, density)) {
      error = "failed to write iLabel print header";
      return false;
    }
#if !USE_CLASSIC_SPP
    if (!waitForBleNotification("A5", ILABEL_FLOW_TIMEOUT_MS)) {
      error = "printer did not acknowledge iLabel print header";
      return false;
    }
#else
    delay(250);
#endif

    for (uint16_t y = 0; y < height; y++) {
      memset(row, 0x00, sizeof(row));
      if ((y % 4) < 2) {
        row[0] = 0xFF;
        row[1] = 0xFF;
        row[rowBytes / 2] = 0xF0;
      }
#if !USE_CLASSIC_SPP
      clearBleNotifications();
#endif
      if (!writeIlabelRow(y, row, sizeof(row))) {
        error = "failed to write iLabel raster row";
        return false;
      }
      delay(20);
    }

    delay(400);
    writeIlabelByte(0x01);
    delay(800);
  } else if (cleanProtocol == "ilabel-black-gap") {
    error = "disabled: gap-label mode can continuously feed roll paper while searching for a label gap";
    return false;
  } else {
    error = "unsupported iLabel protocol: " + protocol;
    return false;
  }

#if !USE_CLASSIC_SPP
  notifyHex = snapshotBleNotifications(notifyPackets);
#else
  (void)notifyHex;
  (void)notifyPackets;
#endif
  return true;
}

bool sendIlabelText(const String& text, String& error) {
  if (!connectPrinter()) {
    error = "printer not connected";
    return false;
  }

  const uint8_t paperType = 1;
  const uint8_t density = 39;
  const uint8_t scale = 3;
  const uint8_t maxLines = 18;
  const uint8_t charsPerLine = ILABEL_PRINT_WIDTH_DOTS / (6 * scale);
  const uint8_t lineHeight = (7 * scale) + 4;
  const uint8_t topMargin = 6;
  const uint8_t bottomMargin = 6;
  String lines[maxLines];
  uint8_t lineCount = wrapIlabelText(text, lines, maxLines, charsPerLine);
  if (lineCount == 0) {
    lineCount = wrapIlabelText("ESP32 OK", lines, maxLines, charsPerLine);
  }
  const uint16_t contentHeight = topMargin + (lineCount * lineHeight) + bottomMargin;
  const uint16_t height = contentHeight + ILABEL_MARGIN_ROWS + ILABEL_TRAILING_MARGIN_ROWS;
  constexpr size_t rowBytes = ILABEL_PRINT_WIDTH_DOTS / 8;
  uint8_t row[rowBytes];

#if !USE_CLASSIC_SPP
  if (!ensureBleMtu(rowBytes + 4 + 3)) {
    error = "failed to negotiate iLabel BLE MTU";
    return false;
  }
#endif

  if (!writeIlabelByte(0x04)) {
    error = "failed to write iLabel cancel before text";
    return false;
  }
  delay(300);

  if (!writeIlabelByte(0x01)) {
    error = "failed to write iLabel status before text";
    return false;
  }
  delay(500);

#if !USE_CLASSIC_SPP
  clearBleNotifications();
#endif
  if (!writeIlabelHeader(height, 0, 0, paperType, density)) {
    error = "failed to write iLabel text header";
    return false;
  }
#if !USE_CLASSIC_SPP
  if (!waitForBleNotification("A5", ILABEL_FLOW_TIMEOUT_MS)) {
    error = "printer did not acknowledge iLabel text header";
    return false;
  }
#else
  delay(250);
#endif

  for (uint16_t y = 0; y < height; y++) {
    if (y < ILABEL_MARGIN_ROWS || y >= ILABEL_MARGIN_ROWS + contentHeight) {
      memset(row, 0x00, rowBytes);
    } else {
      buildIlabelTextRow(lines, lineCount, y - ILABEL_MARGIN_ROWS, row, rowBytes, scale);
    }
    if (!writeIlabelRow(y, row, rowBytes)) {
      error = "failed to write iLabel text row";
      return false;
    }
    delay(20);
  }

  delay(400);
  writeIlabelByte(0x01);
  delay(800);
  return true;
}

bool sendIlabelRasterRle(const char* encoded, uint16_t sourceWidth, uint16_t height, String& error) {
  if (!connectPrinter()) {
    error = "printer not connected";
    return false;
  }
  if (!encoded || !strlen(encoded)) {
    error = "missing receipt_raster_rle_base64 for iLabel receipt";
    return false;
  }
  if (sourceWidth == 0 || sourceWidth > ILABEL_PRINT_WIDTH_DOTS || sourceWidth % 8 != 0 || height == 0) {
    error = "invalid iLabel raster dimensions";
    return false;
  }

  uint8_t* rle = nullptr;
  size_t rleLen = 0;
  if (!decodeBase64Alloc(encoded, rle, rleLen, error, "receipt_raster_rle_base64")) {
    return false;
  }
  if (rleLen == 0 || rleLen % 2 != 0) {
    free(rle);
    error = "invalid iLabel RLE raster";
    return false;
  }

  const uint8_t paperType = 1;
  const uint8_t density = 39;
  constexpr size_t targetRowBytes = ILABEL_PRINT_WIDTH_DOTS / 8;
  const size_t sourceRowBytes = sourceWidth / 8;
  const size_t byteOffset = (targetRowBytes - sourceRowBytes) / 2;
  uint8_t row[targetRowBytes];
  memset(row, 0x00, sizeof(row));

#if !USE_CLASSIC_SPP
  if (!ensureBleMtu(targetRowBytes + 4 + 3)) {
    free(rle);
    error = "failed to negotiate iLabel BLE MTU";
    return false;
  }
#endif

  if (!writeIlabelByte(0x04)) {
    free(rle);
    error = "failed to write iLabel cancel before raster";
    return false;
  }
  delay(300);

  if (!writeIlabelByte(0x01)) {
    free(rle);
    error = "failed to write iLabel status before raster";
    return false;
  }
  delay(500);

#if !USE_CLASSIC_SPP
  clearBleNotifications();
#endif
  const uint16_t totalHeight = height + ILABEL_MARGIN_ROWS + ILABEL_TRAILING_MARGIN_ROWS;
  if (!writeIlabelHeader(totalHeight, 0, 0, paperType, density)) {
    free(rle);
    error = "failed to write iLabel raster header";
    return false;
  }
#if !USE_CLASSIC_SPP
  if (!waitForBleNotification("A5", ILABEL_FLOW_TIMEOUT_MS)) {
    free(rle);
    error = "printer did not acknowledge iLabel raster header";
    return false;
  }
#else
  delay(250);
#endif

  uint16_t y = 0;
  for (; y < ILABEL_MARGIN_ROWS; y++) {
    bool rowOk = false;
    memset(row, 0x00, sizeof(row));
    for (uint8_t attempt = 0; attempt < 3 && !rowOk; attempt++) {
      rowOk = writeIlabelRow(y, row, sizeof(row));
      if (!rowOk) {
        delay(60);
      }
    }
    if (!rowOk) {
      free(rle);
      error = "failed to write iLabel leading margin row ";
      error += String(y);
      return false;
    }
    delay(22);
  }

  uint16_t contentRows = 0;
  size_t sourceByte = 0;
  for (size_t i = 0; i < rleLen && contentRows < height; i += 2) {
    uint8_t count = rle[i];
    const uint8_t value = rle[i + 1];
    while (count-- && contentRows < height) {
      if (sourceByte < sourceRowBytes) {
        row[byteOffset + sourceByte] = value;
      }
      sourceByte++;
      if (sourceByte >= sourceRowBytes) {
        bool rowOk = false;
        for (uint8_t attempt = 0; attempt < 3 && !rowOk; attempt++) {
          rowOk = writeIlabelRow(y, row, sizeof(row));
          if (!rowOk) {
            delay(60);
          }
        }
        if (!rowOk) {
          free(rle);
          error = "failed to write iLabel raster row ";
          error += String(contentRows);
          return false;
        }
        delay(22);
        y++;
        contentRows++;
        sourceByte = 0;
        memset(row, 0x00, sizeof(row));
      }
    }
  }
  free(rle);

  if (contentRows != height || sourceByte != 0) {
    error = "iLabel RLE raster ended before expected height";
    return false;
  }

  for (uint16_t tail = 0; tail < ILABEL_TRAILING_MARGIN_ROWS; tail++, y++) {
    bool rowOk = false;
    memset(row, 0x00, sizeof(row));
    for (uint8_t attempt = 0; attempt < 3 && !rowOk; attempt++) {
      rowOk = writeIlabelRow(y, row, sizeof(row));
      if (!rowOk) {
        delay(60);
      }
    }
    if (!rowOk) {
      error = "failed to write iLabel trailing margin row ";
      error += String(tail);
      return false;
    }
    delay(22);
  }

  delay(400);
  writeIlabelByte(0x01);
  delay(800);
  return true;
}

bool writeIlabelByte(uint8_t value, bool withResponse) {
  return printerWritePacket(&value, 1, withResponse);
}

bool writeIlabelHeader(uint16_t height, uint16_t offset, uint8_t state, uint8_t paperType, uint8_t density, bool withResponse) {
  uint8_t header[] = {
    0x02,
    static_cast<uint8_t>(height & 0xFF),
    static_cast<uint8_t>((height >> 8) & 0xFF),
    static_cast<uint8_t>(offset & 0xFF),
    static_cast<uint8_t>((offset >> 8) & 0xFF),
    state,
    paperType,
    density,
  };
  return printerWritePacket(header, sizeof(header), withResponse);
}

bool writeIlabelRow(uint16_t offset, const uint8_t* row, size_t rowLen, bool withResponse) {
  if (rowLen == 0 || rowLen > 96) {
    return false;
  }

  uint8_t packet[100];
  packet[0] = 0x03;
  packet[1] = static_cast<uint8_t>(offset & 0xFF);
  packet[2] = static_cast<uint8_t>((offset >> 8) & 0xFF);
  packet[3] = 0x01;
  memcpy(packet + 4, row, rowLen);
  return printerWritePacket(packet, rowLen + 4, withResponse);
}

uint8_t wrapIlabelText(const String& text, String lines[], uint8_t maxLines, uint8_t charsPerLine) {
  String normalized = cleanText(text);
  normalized.toUpperCase();
  uint8_t lineCount = 0;
  String line;
  line.reserve(charsPerLine);

  for (size_t i = 0; i < normalized.length() && lineCount < maxLines; i++) {
    char c = normalized.charAt(i);
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      lines[lineCount++] = line;
      line = "";
      continue;
    }
    if (c < 32 || c > 126) {
      c = ' ';
    }
    if (line.length() >= charsPerLine) {
      lines[lineCount++] = line;
      line = "";
      if (lineCount >= maxLines) {
        break;
      }
      while (c == ' ' && i + 1 < normalized.length() && normalized.charAt(i + 1) == ' ') {
        i++;
      }
      if (c == ' ') {
        continue;
      }
    }
    line += c;
  }

  if (line.length() && lineCount < maxLines) {
    lines[lineCount++] = line;
  }
  return lineCount;
}

void buildIlabelTextRow(const String lines[], uint8_t lineCount, uint16_t y, uint8_t* row, size_t rowBytes, uint8_t scale) {
  memset(row, 0x00, rowBytes);

  const uint8_t topMargin = 6;
  const uint8_t lineHeight = (7 * scale) + 4;
  const uint16_t charPitch = 6 * scale;

  if (y < topMargin) {
    return;
  }

  const uint16_t localY = y - topMargin;
  const uint8_t lineIndex = localY / lineHeight;
  if (lineIndex >= lineCount) {
    return;
  }

  const uint8_t rowInLine = localY % lineHeight;
  if (rowInLine >= 7 * scale) {
    return;
  }

  const String& textLine = lines[lineIndex];
  const uint8_t glyphY = rowInLine / scale;
  const uint16_t textWidth = textLine.length() * charPitch;
  const uint16_t x0 = textWidth < ILABEL_PRINT_WIDTH_DOTS ? (ILABEL_PRINT_WIDTH_DOTS - textWidth) / 2 : 0;

  for (uint8_t i = 0; i < textLine.length(); i++) {
    const uint8_t bits = ilabelGlyphRow(textLine.charAt(i), glyphY);
    const uint16_t charX = x0 + i * charPitch;
    for (uint8_t col = 0; col < 5; col++) {
      if (!(bits & (0x10 >> col))) {
        continue;
      }
      for (uint8_t sx = 0; sx < scale; sx++) {
        setIlabelPixel(row, rowBytes, charX + col * scale + sx);
      }
    }
  }
}

uint8_t ilabelGlyphRow(char c, uint8_t row) {
  if (row >= 7) {
    return 0;
  }

  switch (c) {
    case '0': {
      const uint8_t g[] = {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E};
      return g[row];
    }
    case '1': {
      const uint8_t g[] = {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E};
      return g[row];
    }
    case '2': {
      const uint8_t g[] = {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F};
      return g[row];
    }
    case '3': {
      const uint8_t g[] = {0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E};
      return g[row];
    }
    case '4': {
      const uint8_t g[] = {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02};
      return g[row];
    }
    case '5': {
      const uint8_t g[] = {0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E};
      return g[row];
    }
    case '6': {
      const uint8_t g[] = {0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E};
      return g[row];
    }
    case '7': {
      const uint8_t g[] = {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08};
      return g[row];
    }
    case '8': {
      const uint8_t g[] = {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E};
      return g[row];
    }
    case '9': {
      const uint8_t g[] = {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C};
      return g[row];
    }
    case 'A': {
      const uint8_t g[] = {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11};
      return g[row];
    }
    case 'B': {
      const uint8_t g[] = {0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E};
      return g[row];
    }
    case 'C': {
      const uint8_t g[] = {0x0F, 0x10, 0x10, 0x10, 0x10, 0x10, 0x0F};
      return g[row];
    }
    case 'D': {
      const uint8_t g[] = {0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E};
      return g[row];
    }
    case 'E': {
      const uint8_t g[] = {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F};
      return g[row];
    }
    case 'F': {
      const uint8_t g[] = {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10};
      return g[row];
    }
    case 'G': {
      const uint8_t g[] = {0x0F, 0x10, 0x10, 0x13, 0x11, 0x11, 0x0F};
      return g[row];
    }
    case 'H': {
      const uint8_t g[] = {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11};
      return g[row];
    }
    case 'I': {
      const uint8_t g[] = {0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E};
      return g[row];
    }
    case 'J': {
      const uint8_t g[] = {0x07, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0C};
      return g[row];
    }
    case 'K': {
      const uint8_t g[] = {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11};
      return g[row];
    }
    case 'L': {
      const uint8_t g[] = {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F};
      return g[row];
    }
    case 'M': {
      const uint8_t g[] = {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11};
      return g[row];
    }
    case 'N': {
      const uint8_t g[] = {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11};
      return g[row];
    }
    case 'O': {
      const uint8_t g[] = {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E};
      return g[row];
    }
    case 'P': {
      const uint8_t g[] = {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10};
      return g[row];
    }
    case 'Q': {
      const uint8_t g[] = {0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D};
      return g[row];
    }
    case 'R': {
      const uint8_t g[] = {0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11};
      return g[row];
    }
    case 'S': {
      const uint8_t g[] = {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E};
      return g[row];
    }
    case 'T': {
      const uint8_t g[] = {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04};
      return g[row];
    }
    case 'U': {
      const uint8_t g[] = {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E};
      return g[row];
    }
    case 'V': {
      const uint8_t g[] = {0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04};
      return g[row];
    }
    case 'W': {
      const uint8_t g[] = {0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A};
      return g[row];
    }
    case 'X': {
      const uint8_t g[] = {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11};
      return g[row];
    }
    case 'Y': {
      const uint8_t g[] = {0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04};
      return g[row];
    }
    case 'Z': {
      const uint8_t g[] = {0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F};
      return g[row];
    }
    case '-': {
      const uint8_t g[] = {0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00};
      return g[row];
    }
    case '_': {
      const uint8_t g[] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F};
      return g[row];
    }
    case ':': {
      const uint8_t g[] = {0x00, 0x04, 0x04, 0x00, 0x04, 0x04, 0x00};
      return g[row];
    }
    case '.': {
      const uint8_t g[] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C};
      return g[row];
    }
    case ',': {
      const uint8_t g[] = {0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08};
      return g[row];
    }
    case '/': {
      const uint8_t g[] = {0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10};
      return g[row];
    }
    case '%': {
      const uint8_t g[] = {0x19, 0x1A, 0x02, 0x04, 0x08, 0x0B, 0x13};
      return g[row];
    }
    case '\'': {
      const uint8_t g[] = {0x04, 0x04, 0x08, 0x00, 0x00, 0x00, 0x00};
      return g[row];
    }
    case '"': {
      const uint8_t g[] = {0x0A, 0x0A, 0x14, 0x00, 0x00, 0x00, 0x00};
      return g[row];
    }
    case '?': {
      const uint8_t g[] = {0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04};
      return g[row];
    }
    case '!': {
      const uint8_t g[] = {0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04};
      return g[row];
    }
    case '+': {
      const uint8_t g[] = {0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00};
      return g[row];
    }
    case '=': {
      const uint8_t g[] = {0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00};
      return g[row];
    }
    case '(': {
      const uint8_t g[] = {0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02};
      return g[row];
    }
    case ')': {
      const uint8_t g[] = {0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08};
      return g[row];
    }
    default:
      return 0;
  }
}

void setIlabelPixel(uint8_t* row, size_t rowBytes, uint16_t x) {
  const size_t byteIndex = x / 8;
  if (byteIndex >= rowBytes) {
    return;
  }
  row[byteIndex] |= static_cast<uint8_t>(0x80 >> (x % 8));
}

String buildReceiptText(JsonDocument& doc) {
  const String sessionId = cleanText(doc["session_id"] | "");
  const String markName = cleanText(doc["mark_name"] | "");
  const String oracleText = cleanText(doc["oracle_text"] | "");
  const String sessionUrl = cleanText(doc["session_url"] | "");
  const String themes = themesToText(doc["themes"]);
  const String intensity = measureToText(doc["measures"], "intensity");
  const String instability = measureToText(doc["measures"], "instability");
  const String confidence = measureToText(doc["measures"], "confidence");

  String text = "THE ORACLE SPEAKS\n";
  text += "------------------------------\n";
  if (sessionId.length()) text += "Session: " + sessionId + "\n";
  if (markName.length()) text += "Symbol: " + markName + "\n";
  if (oracleText.length()) text += "\n" + oracleText + "\n";
  if (themes.length()) text += "\nThemes: " + themes + "\n";
  if (intensity.length() || instability.length() || confidence.length()) {
    text += "\nVoice measures:\n";
    if (intensity.length()) text += "Intensity: " + intensity + "\n";
    if (instability.length()) text += "Instability: " + instability + "\n";
    if (confidence.length()) text += "Confidence: " + confidence + "\n";
  }
  if (sessionUrl.length()) text += "\n" + sessionUrl + "\n";
  text += "------------------------------\n";
  return text;
}

bool printReceipt(JsonDocument& doc, const String& protocol, String& error) {
  const String cleanProtocol = cleanProtocolName(protocol);
  if (cleanProtocol == "escpos") {
    return printEscposReceipt(doc, error);
  }
  if (cleanProtocol == "ilabel" || cleanProtocol == "ilabel-text") {
    return printIlabelReceipt(doc, error);
  }
  return sendProtocolText(cleanProtocol, buildReceiptText(doc), error);
}

bool printIlabelReceipt(JsonDocument& doc, String& error) {
  const char* raster = doc["receipt_raster_rle_base64"] | "";
  const uint16_t width = doc["ilabel_width_dots"] | ILABEL_PRINT_WIDTH_DOTS;
  const uint16_t height = doc["ilabel_height_dots"] | 0;
  if (!strlen(raster)) {
    error = "missing receipt_raster_rle_base64; iLabel receipt requires full raster QR output";
    return false;
  }
  return sendIlabelRasterRle(raster, width, height, error);
}

bool printEscposReceipt(JsonDocument& doc, String& error) {
  if (!connectPrinter()) {
    error = "printer not connected";
    return false;
  }

  const String sessionId = cleanText(doc["session_id"] | "");
  const String markName = cleanText(doc["mark_name"] | "");
  const String title = cleanText(doc["receipt_title"] | "ORACLE");
  const String subtitle = cleanText(doc["subtitle"] | "THE ORACLE THAT WEARS US");
  const String symbolLabel = cleanText(doc["symbol_label"] | markName);
  const String oracleText = cleanText(doc["oracle_text"] | "");
  const String sessionUrl = cleanText(doc["session_url"] | "");
  const String themes = themesToText(doc["themes"]);
  const String intensity = measureToText(doc["measures"], "intensity");
  const String instability = measureToText(doc["measures"], "instability");
  const String confidence = measureToText(doc["measures"], "confidence");

  const uint8_t initCommand[] = {0x1B, 0x40};
  const uint8_t alignCenter[] = {0x1B, 0x61, 0x01};
  const uint8_t alignLeft[] = {0x1B, 0x61, 0x00};
  const uint8_t boldOn[] = {0x1B, 0x45, 0x01};
  const uint8_t boldOff[] = {0x1B, 0x45, 0x00};
  const uint8_t feed[] = {0x0A};

  const char* fullRasterBytes = doc["receipt_escpos_base64"] | "";
  if (strlen(fullRasterBytes) > 0) {
    printerWrite(initCommand, sizeof(initCommand));
    return decodeBase64ToPrinter(fullRasterBytes, error);
  }

  printerWrite(initCommand, sizeof(initCommand));
  printerWrite(alignCenter, sizeof(alignCenter));
  printerWrite(boldOn, sizeof(boldOn));
  printLine(title);
  printerWrite(boldOff, sizeof(boldOff));
  printLine(subtitle);
  printLine("SESSION " + sessionId);

  const char* symbolBytes = doc["symbol_escpos_base64"] | "";
  if (strlen(symbolBytes) > 0) {
    printerWrite(feed, sizeof(feed));
    if (!decodeBase64ToPrinter(symbolBytes, error)) {
      return false;
    }
    printerWrite(feed, sizeof(feed));
  }

  printerWrite(alignLeft, sizeof(alignLeft));
  printLine("");
  printLine(symbolLabel.length() ? symbolLabel : markName);
  printLine("");
  printLine("WHAT THE ORACLE PERCEIVED");
  printWrapped(oracleText);
  printLine("");
  printLine("WHAT THE SYSTEM MEASURED");
  if (intensity.length() || instability.length() || confidence.length()) {
    if (intensity.length()) printLine("Intensity: " + intensity);
    if (instability.length()) printLine("Instability: " + instability);
    if (confidence.length()) printLine("Confidence: " + confidence);
  }
  printLine("");
  printLine("THEMES");
  printWrapped(themes.length() ? themes : "none");

  if (sessionUrl.length()) {
    printLine("");
    printLine("VIEW YOUR MARK ONLINE");
    printerWrite(alignCenter, sizeof(alignCenter));
    const char* qrBytes = doc["qr_escpos_base64"] | "";
    if (strlen(qrBytes) > 0) {
      if (!decodeBase64ToPrinter(qrBytes, error)) {
        return false;
      }
    } else {
      printQr(sessionUrl);
    }
    printerWrite(alignLeft, sizeof(alignLeft));
    printWrapped(sessionId);
  }

  printLine("");
  printLine("------------------------------");
  printLine("");
  printLine("");
  printLine("");
  return true;
}

void printLine(const String& line) {
  const String safe = cleanText(line);
  printerWrite(reinterpret_cast<const uint8_t*>(safe.c_str()), safe.length());
  printerWriteByte('\n');
}

void printWrapped(const String& text, uint8_t width) {
  String remaining = cleanText(text);
  remaining.trim();
  while (remaining.length() > width) {
    int breakAt = -1;
    for (int i = width; i >= 0; --i) {
      if (remaining.charAt(i) == ' ') {
        breakAt = i;
        break;
      }
    }
    if (breakAt <= 0) {
      breakAt = width;
    }
    printLine(remaining.substring(0, breakAt));
    remaining = remaining.substring(breakAt);
    remaining.trim();
  }
  if (remaining.length()) {
    printLine(remaining);
  }
}

void printQr(const String& url) {
  if (!url.length()) {
    return;
  }

  const uint8_t model[] = {0x1D, 0x28, 0x6B, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00};
  const uint8_t size[] = {0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x43, 0x04};
  const uint8_t errorLevel[] = {0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x45, 0x31};
  printerWrite(model, sizeof(model));
  printerWrite(size, sizeof(size));
  printerWrite(errorLevel, sizeof(errorLevel));

  const uint16_t storeLen = url.length() + 3;
  uint8_t storeHeader[] = {
    0x1D, 0x28, 0x6B,
    static_cast<uint8_t>(storeLen & 0xFF),
    static_cast<uint8_t>((storeLen >> 8) & 0xFF),
    0x31, 0x50, 0x30
  };
  printerWrite(storeHeader, sizeof(storeHeader));
  printerWrite(reinterpret_cast<const uint8_t*>(url.c_str()), url.length());

  const uint8_t printCommand[] = {0x1D, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x51, 0x30};
  printerWrite(printCommand, sizeof(printCommand));
  printerWriteByte('\n');
}

String cleanText(const String& input) {
  String out;
  out.reserve(input.length());

  for (size_t i = 0; i < input.length();) {
    const uint8_t c = static_cast<uint8_t>(input[i]);
    if (c < 0x80) {
      if (c == '\r') {
        i++;
        continue;
      }
      out += static_cast<char>(c);
      i++;
      continue;
    }

    if (i + 2 < input.length() && c == 0xE2 && static_cast<uint8_t>(input[i + 1]) == 0x80) {
      const uint8_t c2 = static_cast<uint8_t>(input[i + 2]);
      if (c2 == 0x98 || c2 == 0x99) {
        out += "'";
      } else if (c2 == 0x9C || c2 == 0x9D) {
        out += "\"";
      } else if (c2 == 0x93 || c2 == 0x94) {
        out += "-";
      } else if (c2 == 0xA6) {
        out += "...";
      } else {
        out += " ";
      }
      i += 3;
      continue;
    }

    if (i + 2 < input.length() && c == 0xE2 && static_cast<uint8_t>(input[i + 1]) == 0x95) {
      out += "-";
      i += 3;
      continue;
    }

    if (i + 1 < input.length() && c == 0xC2 && static_cast<uint8_t>(input[i + 1]) == 0xA0) {
      out += " ";
      i += 2;
      continue;
    }

    if ((c & 0xE0) == 0xC0) {
      i += 2;
    } else if ((c & 0xF0) == 0xE0) {
      i += 3;
    } else if ((c & 0xF8) == 0xF0) {
      i += 4;
    } else {
      i++;
    }
    out += "?";
  }
  return out;
}

String cleanProtocolName(String value) {
  value.trim();
  value.toLowerCase();
  if (!value.length()) {
    return PRINTER_DEFAULT_PROTOCOL;
  }
  return value;
}

String jsonEscape(const String& input) {
  String out;
  out.reserve(input.length() + 8);
  for (size_t i = 0; i < input.length(); i++) {
    const char c = input.charAt(i);
    if (c == '"' || c == '\\') {
      out += '\\';
      out += c;
    } else if (c == '\n') {
      out += "\\n";
    } else if (c == '\r') {
      out += "\\r";
    } else if (static_cast<uint8_t>(c) < 32) {
      out += ' ';
    } else {
      out += c;
    }
  }
  return out;
}

String escapeLabelText(const String& input) {
  String out = cleanText(input);
  out.replace("\"", "'");
  out.replace("\\", "/");
  out.replace("^", " ");
  return out;
}

String themesToText(JsonVariant themes) {
  if (themes.is<JsonArray>()) {
    String result;
    for (JsonVariant item : themes.as<JsonArray>()) {
      if (result.length()) {
        result += ", ";
      }
      result += cleanText(String(item.as<const char*>()));
    }
    return result;
  }
  return cleanText(String(themes.as<const char*>()));
}

String measureToText(JsonVariant measures, const char* key) {
  if (!measures.is<JsonObject>() || !measures[key].is<float>()) {
    return "";
  }
  const float value = measures[key].as<float>();
  return String(static_cast<int>(roundf(value * 100.0f))) + "%";
}

bool decodeBase64ToPrinter(const char* encoded, String& error) {
  uint8_t* decoded = nullptr;
  size_t decodedLen = 0;
  if (!decodeBase64Alloc(encoded, decoded, decodedLen, error, "base64 printer bytes")) {
    return false;
  }

  const bool ok = printerWrite(decoded, decodedLen);
  free(decoded);
  if (!ok) {
    error = "failed to write decoded printer bytes";
  }
  return ok;
}

bool decodeBase64Alloc(const char* encoded, uint8_t*& decoded, size_t& decodedLen, String& error, const char* label) {
  decoded = nullptr;
  decodedLen = 0;
  const size_t encodedLen = strlen(encoded);
  const size_t maxDecodedLen = (encodedLen * 3) / 4 + 4;
  decoded = static_cast<uint8_t*>(malloc(maxDecodedLen));
  if (!decoded) {
    error = "not enough memory for ";
    error += label;
    return false;
  }

  const int rc = mbedtls_base64_decode(decoded, maxDecodedLen, &decodedLen, reinterpret_cast<const unsigned char*>(encoded), encodedLen);
  if (rc != 0) {
    free(decoded);
    decoded = nullptr;
    decodedLen = 0;
    error = "invalid ";
    error += label;
    return false;
  }
  return true;
}

bool decodeHexToBytes(const String& hex, uint8_t*& bytes, size_t& len, String& error) {
  String compact;
  compact.reserve(hex.length());
  for (size_t i = 0; i < hex.length(); i++) {
    const char c = hex.charAt(i);
    if (c == ' ' || c == '\n' || c == '\r' || c == '\t' || c == ':' || c == '-' || c == ',') {
      continue;
    }
    if (i + 1 < hex.length() && c == '0' && (hex.charAt(i + 1) == 'x' || hex.charAt(i + 1) == 'X')) {
      i++;
      continue;
    }
    compact += c;
  }

  if (!compact.length()) {
    error = "missing hex bytes";
    return false;
  }
  if (compact.length() % 2 != 0) {
    error = "hex byte string must contain an even number of hex digits";
    return false;
  }

  len = compact.length() / 2;
  bytes = static_cast<uint8_t*>(malloc(len));
  if (!bytes) {
    error = "not enough memory for raw bytes";
    return false;
  }

  for (size_t i = 0; i < len; i++) {
    const int high = hexValue(compact.charAt(i * 2));
    const int low = hexValue(compact.charAt(i * 2 + 1));
    if (high < 0 || low < 0) {
      free(bytes);
      bytes = nullptr;
      len = 0;
      error = "invalid hex digit";
      return false;
    }
    bytes[i] = static_cast<uint8_t>((high << 4) | low);
  }

  return true;
}

int hexValue(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

#if USE_CLASSIC_SPP
bool parseMac(const char* text, uint8_t out[6]) {
  unsigned int values[6];
  if (sscanf(text, "%x:%x:%x:%x:%x:%x", &values[0], &values[1], &values[2], &values[3], &values[4], &values[5]) != 6) {
    return false;
  }
  for (int i = 0; i < 6; i++) {
    out[i] = static_cast<uint8_t>(values[i]);
  }
  return true;
}
#endif

bool connectPrinter() {
#if USE_CLASSIC_SPP
  if (SerialBT.connected()) {
    return true;
  }

  bool connected = false;
  if (strlen(PRINTER_CLASSIC_MAC) > 0) {
    uint8_t mac[6];
    if (!parseMac(PRINTER_CLASSIC_MAC, mac)) {
      Serial.println("Invalid PRINTER_CLASSIC_MAC");
      return false;
    }
    connected = SerialBT.connect(mac);
  } else {
    connected = SerialBT.connect(PRINTER_CLASSIC_NAME);
  }

  Serial.printf("Classic printer connect: %s\n", connected ? "ok" : "failed");
  return connected;
#else
  if (bleClient && bleClient->isConnected() && printerChar) {
    return true;
  }

  printerChar = nullptr;
  notifyChar = nullptr;
  if (bleClient) {
    if (bleClient->isConnected()) {
      bleClient->disconnect();
    }
    NimBLEDevice::deleteClient(bleClient);
    bleClient = nullptr;
  }

  NimBLEScan* scan = NimBLEDevice::getScan();
  scan->setActiveScan(true);
  scan->setInterval(100);
  scan->setWindow(100);
  Serial.printf("Scanning for BLE printer for %d second(s)\n", PRINTER_BLE_SCAN_SECONDS);
  NimBLEScanResults results = scan->getResults(PRINTER_BLE_SCAN_SECONDS * 1000);

  const NimBLEAdvertisedDevice* selected = nullptr;
  String wantedAddress = String(PRINTER_BLE_ADDRESS);
  wantedAddress.toLowerCase();
  const String wantedPrefix = String(PRINTER_NAME_PREFIX);

  for (int i = 0; i < results.getCount(); i++) {
    const NimBLEAdvertisedDevice* device = results.getDevice(i);
    String address = String(device->getAddress().toString().c_str());
    address.toLowerCase();
    String name = String(device->getName().c_str());

    const bool addressMatch = wantedAddress.length() && address == wantedAddress;
    const bool nameMatch = !wantedAddress.length() && (wantedPrefix.length() == 0 || name.startsWith(wantedPrefix));
    if (addressMatch || nameMatch) {
      selected = device;
      Serial.printf("Selected BLE printer: %s %s\n", name.c_str(), address.c_str());
      break;
    }
  }

  if (!selected) {
    Serial.println("No BLE printer matched config");
    return false;
  }

  bleClient = NimBLEDevice::createClient();
  if (!bleClient) {
    Serial.println("Could not create BLE client");
    return false;
  }
  bleClient->setConnectTimeout(5 * 1000);

  if (!bleClient->connect(selected)) {
    Serial.println("BLE printer connection failed");
    NimBLEDevice::deleteClient(bleClient);
    bleClient = nullptr;
    return false;
  }

  ensureBleMtu(ILABEL_BLE_MTU);

  NimBLERemoteService* service = bleClient->getService(PRINTER_SERVICE_UUID);
  if (!service) {
    Serial.printf("BLE service not found: %s\n", PRINTER_SERVICE_UUID);
    bleClient->disconnect();
    return false;
  }

  printerChar = service->getCharacteristic(PRINTER_WRITE_CHAR_UUID);
  if (!printerChar && strlen(PRINTER_ALT_WRITE_CHAR_UUID) > 0) {
    Serial.printf("Primary write characteristic not found: %s; trying alternate %s\n", PRINTER_WRITE_CHAR_UUID, PRINTER_ALT_WRITE_CHAR_UUID);
    printerChar = service->getCharacteristic(PRINTER_ALT_WRITE_CHAR_UUID);
  }
  if (!printerChar) {
    Serial.printf("BLE write characteristic not found: %s\n", PRINTER_WRITE_CHAR_UUID);
    bleClient->disconnect();
    return false;
  }

  if (!printerChar->canWrite() && !printerChar->canWriteNoResponse()) {
    Serial.println("BLE characteristic is not writable");
    bleClient->disconnect();
    printerChar = nullptr;
    return false;
  }

  subscribePrinterNotifications(service);

  Serial.println("BLE printer connected");
  return true;
#endif
}

#if !USE_CLASSIC_SPP
bool ensureBleMtu(uint16_t mtu) {
  if (!bleClient || !bleClient->isConnected()) {
    return false;
  }
  if (bleClient->getMTU() >= mtu) {
    return true;
  }
  if (!bleClient->exchangeMTU()) {
    Serial.printf("BLE MTU exchange request failed; current=%u target=%u\n", bleClient->getMTU(), mtu);
    return false;
  }
  delay(300);
  Serial.printf("BLE MTU current=%u target=%u\n", bleClient->getMTU(), mtu);
  return bleClient->getMTU() >= mtu;
}

void subscribePrinterNotifications(NimBLERemoteService* service) {
  if (!service) {
    return;
  }

  if (strlen(PRINTER_NOTIFY_CHAR_UUID) > 0) {
    notifyChar = service->getCharacteristic(PRINTER_NOTIFY_CHAR_UUID);
    if (notifyChar && (notifyChar->canNotify() || notifyChar->canIndicate())) {
      clearBleNotifications();
      const bool useNotify = notifyChar->canNotify();
      if (notifyChar->subscribe(useNotify, printerNotifyCallback)) {
        Serial.printf("BLE notify subscribed: %s\n", PRINTER_NOTIFY_CHAR_UUID);
      } else {
        Serial.printf("BLE notify subscribe failed: %s\n", PRINTER_NOTIFY_CHAR_UUID);
        notifyChar = nullptr;
      }
    } else {
      Serial.printf("BLE notify characteristic not available: %s\n", PRINTER_NOTIFY_CHAR_UUID);
      notifyChar = nullptr;
    }
  }

  const std::vector<NimBLERemoteCharacteristic*>& chars = service->getCharacteristics(true);
  for (NimBLERemoteCharacteristic* chr : chars) {
    if (!chr || !(chr->canNotify() || chr->canIndicate())) {
      continue;
    }
    if (notifyChar && chr->getUUID().equals(notifyChar->getUUID())) {
      continue;
    }
    const bool useNotify = chr->canNotify();
    if (chr->subscribe(useNotify, printerNotifyCallback)) {
      Serial.printf("BLE notify subscribed: %s\n", chr->getUUID().toString().c_str());
      if (!notifyChar) {
        notifyChar = chr;
      }
    } else {
      Serial.printf("BLE notify subscribe failed: %s\n", chr->getUUID().toString().c_str());
    }
  }

  printerChar = service->getCharacteristic(PRINTER_WRITE_CHAR_UUID);
  if (!printerChar && strlen(PRINTER_ALT_WRITE_CHAR_UUID) > 0) {
    printerChar = service->getCharacteristic(PRINTER_ALT_WRITE_CHAR_UUID);
  }
}
#endif

bool printerWrite(const uint8_t* data, size_t len) {
  return printerWriteMode(data, len, false);
}

bool printerWriteMode(const uint8_t* data, size_t len, bool withResponse) {
  if (len == 0) {
    return true;
  }
  if (!connectPrinter()) {
    return false;
  }

  size_t offset = 0;
  while (offset < len) {
    const size_t chunk = min(static_cast<size_t>(PRINTER_WRITE_CHUNK_SIZE), len - offset);
#if USE_CLASSIC_SPP
    (void)withResponse;
    const size_t written = SerialBT.write(data + offset, chunk);
    if (written != chunk) {
      return false;
    }
#else
    if (!printerChar) {
      return false;
    }
    if (withResponse && !printerChar->canWrite()) {
      return false;
    }
    if (!withResponse && !printerChar->canWriteNoResponse()) {
      return false;
    }
    if (!printerChar->writeValue(data + offset, chunk, withResponse)) {
      return false;
    }
#endif
    offset += chunk;
    delay(withResponse ? PRINTER_RESPONSE_CHUNK_DELAY_MS : PRINTER_CHUNK_DELAY_MS);
  }
  return true;
}

bool printerWritePacket(const uint8_t* data, size_t len, bool withResponse) {
  if (len == 0) {
    return true;
  }
  if (!connectPrinter()) {
    return false;
  }

#if USE_CLASSIC_SPP
  (void)withResponse;
  return SerialBT.write(data, len) == len;
#else
  if (!printerChar) {
    return false;
  }
  if (withResponse && !printerChar->canWrite()) {
    return false;
  }
  if (!withResponse && !printerChar->canWriteNoResponse()) {
    return false;
  }
  if (bleClient && bleClient->isConnected() && len + 3 > bleClient->getMTU()) {
    return false;
  }
  if (printerChar->writeValue(data, len, withResponse)) {
    return true;
  }
  if (!withResponse && printerChar->canWrite()) {
    delay(PRINTER_RESPONSE_CHUNK_DELAY_MS);
    return printerChar->writeValue(data, len, true);
  }
  return false;
#endif
}

bool printerWriteByte(uint8_t value) {
  return printerWrite(&value, 1);
}

bool probeWrite(const char* characteristicUuid, const uint8_t* data, size_t len, bool withResponse) {
  if (len == 0) {
    return true;
  }

#if USE_CLASSIC_SPP
  (void)characteristicUuid;
  return printerWriteMode(data, len, withResponse);
#else
  if (!connectPrinter()) {
    return false;
  }

  NimBLERemoteService* service = bleClient->getService(PRINTER_SERVICE_UUID);
  if (!service) {
    return false;
  }

  NimBLERemoteCharacteristic* selectedChar = service->getCharacteristic(characteristicUuid);
  if (!selectedChar) {
    return false;
  }
  if (withResponse && !selectedChar->canWrite()) {
    return false;
  }
  if (!withResponse && !selectedChar->canWriteNoResponse()) {
    return false;
  }

  size_t offset = 0;
  while (offset < len) {
    const size_t chunk = min(static_cast<size_t>(PRINTER_WRITE_CHUNK_SIZE), len - offset);
    if (!selectedChar->writeValue(data + offset, chunk, withResponse)) {
      return false;
    }
    offset += chunk;
    delay(withResponse ? PRINTER_RESPONSE_CHUNK_DELAY_MS : PRINTER_CHUNK_DELAY_MS);
  }
  return true;
#endif
}

void setStatusLed(bool on) {
#if ENABLE_STATUS_LED
  digitalWrite(STATUS_LED_PIN, on ? HIGH : LOW);
#else
  (void)on;
#endif
}
