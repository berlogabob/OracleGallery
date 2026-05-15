#include <Arduino.h>

#if __has_include("config.local.h")
#include "config.local.h"
#else
#include "config.example.h"
#endif

#include <ArduinoJson.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiUdp.h>
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

#ifndef BLE_NOTIFY_HEX_LIMIT
#define BLE_NOTIFY_HEX_LIMIT 512
#endif

#ifndef SERIAL_BAUD
#define SERIAL_BAUD 115200
#endif

#ifndef SERIAL_STARTUP_DELAY_MS
#define SERIAL_STARTUP_DELAY_MS 1500
#endif

#ifndef WAKE_PRINTER_ON_BUTTON
#define WAKE_PRINTER_ON_BUTTON 0
#endif

WebServer server(HTTP_PORT);
WiFiUDP udp;

#if USE_CLASSIC_SPP
BluetoothSerial SerialBT;
#else
NimBLEClient* bleClient = nullptr;
NimBLERemoteCharacteristic* printerChar = nullptr;
NimBLERemoteCharacteristic* notifyChar = nullptr;
String bleNotifyHex;
uint32_t bleNotifyPackets = 0;
#endif

int lastRawButtonState = HIGH;
int stableButtonState = HIGH;
uint32_t lastButtonChangeMs = 0;
uint32_t lastWifiCheckMs = 0;
uint32_t lastWakeAttemptMs = 0;
bool wakeRequested = false;

void connectWiFi();
void setupHttpServer();
void handleRoot();
void handleStatus();
void handleStart();
void handleWake();
void handlePrint();
void handleTestPrint();
void handleProbePrint();
void handleNotFound();
void handleButton();
void sendStartUdp();
void requestPrinterWake();
void processWakeRequest();
bool connectPrinter();
bool printerWrite(const uint8_t* data, size_t len);
bool printerWriteByte(uint8_t value);
bool probeWrite(const char* characteristicUuid, const uint8_t* data, size_t len, bool withResponse);
#if !USE_CLASSIC_SPP
void printerNotifyCallback(NimBLERemoteCharacteristic* characteristic, uint8_t* data, size_t len, bool isNotify);
void clearBleNotifications();
String snapshotBleNotifications(uint32_t& packets);
#endif
bool printReceipt(JsonDocument& doc, String& error);
void printLine(const String& line);
void printWrapped(const String& text, uint8_t width = 32);
void printQr(const String& url);
String cleanText(const String& input);
String themesToText(JsonVariant themes);
String measureToText(JsonVariant measures, const char* key);
bool decodeBase64ToPrinter(const char* encoded, String& error);
void setStatusLed(bool on);

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(SERIAL_STARTUP_DELAY_MS);
  Serial.println();
  Serial.println("========================================");
  Serial.println("Oracle ESP32 button/printer bridge starting");
  Serial.printf("Serial baud: %lu\n", static_cast<unsigned long>(SERIAL_BAUD));

  pinMode(BUTTON_PIN, INPUT_PULLUP);
#if ENABLE_STATUS_LED
  pinMode(STATUS_LED_PIN, OUTPUT);
  setStatusLed(false);
#endif

  connectWiFi();
  udp.begin(0);

#if USE_CLASSIC_SPP
  SerialBT.begin("OracleESP32_Printer", true);
  Serial.println("Printer transport: Bluetooth Classic SPP");
#else
  NimBLEDevice::init("OracleESP32_Printer");
  NimBLEDevice::setPower(3);
  Serial.println("Printer transport: BLE client");
#endif

  setupHttpServer();
  Serial.printf("HTTP server ready on port %d\n", HTTP_PORT);
}

void loop() {
  server.handleClient();
  handleButton();
  processWakeRequest();

  const uint32_t now = millis();
  if (now - lastWifiCheckMs > 5000) {
    lastWifiCheckMs = now;
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("Wi-Fi disconnected; reconnecting");
      WiFi.reconnect();
    }
  }
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
  server.on("/start", HTTP_POST, handleStart);
  server.on("/wake", HTTP_POST, handleWake);
  server.on("/test-print", HTTP_POST, handleTestPrint);
  server.on("/probe-print", HTTP_POST, handleProbePrint);
  server.on("/print", HTTP_POST, handlePrint);
  server.onNotFound(handleNotFound);
  server.begin();
}

void handleRoot() {
  server.send(200, "text/plain", "Oracle ESP32 button/printer bridge\nPOST /print JSON to print\nPOST /test-print for plain text\nPOST /probe-print for protocol probing\nPOST /start to send START UDP\n");
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
  body += "\",\"write_char\":\"";
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
  body += "\",\"button_pin\":";
  body += String(BUTTON_PIN);
  body += "}";
  server.send(200, "application/json", body);
}

void handleStart() {
  sendStartUdp();
  requestPrinterWake();
  server.send(202, "application/json", "{\"ok\":true,\"queued\":\"START\"}");
}

void handleWake() {
  requestPrinterWake();
  server.send(202, "application/json", "{\"ok\":true,\"queued\":\"wake\"}");
}

void handleTestPrint() {
  String error;
  DynamicJsonDocument doc(1024);
  doc["session_id"] = "TEST";
  doc["mark_name"] = "BLE TEST";
  doc["oracle_text"] = "Plain text printer test. If you can read this, the ESP32 is writing to the correct BLE characteristic.";
  JsonArray themes = doc.createNestedArray("themes");
  themes.add("test");
  JsonObject measures = doc.createNestedObject("measures");
  measures["intensity"] = 1.0;
  doc["session_url"] = "";
  doc["symbol_escpos_base64"] = "";

  if (!printReceipt(doc, error)) {
    String response = "{\"ok\":false,\"error\":\"";
    response += cleanText(error);
    response += "\"}";
    server.send(503, "application/json", response);
    return;
  }

  server.send(200, "application/json", "{\"ok\":true,\"printed\":true,\"kind\":\"test\"}");
}

void handleProbePrint() {
#if USE_CLASSIC_SPP
  server.send(400, "application/json", "{\"ok\":false,\"error\":\"probe-print is BLE-only\"}");
#else
  struct ProbePayload {
    const char* name;
    const char* bytes;
  };

  const ProbePayload payloads[] = {
    {
      "raw",
      "WP9509 RAW TEXT TEST\r\n"
      "char=%s response=%s\r\n\r\n"
    },
    {
      "escpos",
      "\x1B@"
      "WP9509 ESC/POS TEST\r\n"
      "char=%s response=%s\r\n\r\n\r\n"
    },
    {
      "tspl",
      "SIZE 40 mm,30 mm\r\n"
      "GAP 2 mm,0\r\n"
      "CLS\r\n"
      "TEXT 20,20,\"TSS24.BF2\",0,1,1,\"WP9509 TSPL %s %s\"\r\n"
      "PRINT 1\r\n"
    },
    {
      "cpcl",
      "! 0 200 200 210 1\r\n"
      "TEXT 4 0 30 40 WP9509 CPCL %s %s\r\n"
      "FORM\r\n"
      "PRINT\r\n"
    },
    {
      "zpl",
      "^XA^FO20,20^ADN,18,10^FDWP9509 ZPL %s %s^FS^XZ\r\n"
    },
  };

  const char* characteristics[] = {
    "0000fff1-0000-1000-8000-00805f9b34fb",
    "0000fff2-0000-1000-8000-00805f9b34fb",
  };

  String response = "{\"ok\":true,\"attempts\":[";
  bool first = true;
  for (const char* characteristic : characteristics) {
    for (uint8_t responseMode = 0; responseMode < 2; responseMode++) {
      const bool withResponse = responseMode == 1;
      const char* modeText = withResponse ? "write" : "noresp";
      for (const ProbePayload& payload : payloads) {
        char buffer[240];
        snprintf(buffer, sizeof(buffer), payload.bytes, characteristic + 4, modeText);
        clearBleNotifications();
        const bool ok = probeWrite(characteristic, reinterpret_cast<const uint8_t*>(buffer), strlen(buffer), withResponse);
        delay(350);
        uint32_t notifyPackets = 0;
        const String notifyHex = snapshotBleNotifications(notifyPackets);
        Serial.printf("Probe print %s %s %s: %s\n", characteristic, modeText, payload.name, ok ? "ok" : "failed");
        if (notifyHex.length()) {
          Serial.printf("Probe notify packets=%lu bytes=%s\n", static_cast<unsigned long>(notifyPackets), notifyHex.c_str());
        }

        if (!first) {
          response += ",";
        }
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
        response += "\"";
        response += "}";
      }
    }
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
  if (body.length() > 60000) {
    server.send(413, "application/json", "{\"ok\":false,\"error\":\"JSON body too large\"}");
    return;
  }

  DynamicJsonDocument doc(65536);
  DeserializationError jsonError = deserializeJson(doc, body);
  if (jsonError) {
    String error = "{\"ok\":false,\"error\":\"invalid JSON: ";
    error += jsonError.c_str();
    error += "\"}";
    server.send(400, "application/json", error);
    return;
  }

  String error;
  if (!printReceipt(doc, error)) {
    String response = "{\"ok\":false,\"error\":\"";
    response += cleanText(error);
    response += "\"}";
    server.send(503, "application/json", response);
    return;
  }

  server.send(200, "application/json", "{\"ok\":true,\"printed\":true}");
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

void handleButton() {
  const int raw = digitalRead(BUTTON_PIN);
  const uint32_t now = millis();

  if (raw != lastRawButtonState) {
    lastRawButtonState = raw;
    lastButtonChangeMs = now;
  }

  if (now - lastButtonChangeMs < BUTTON_DEBOUNCE_MS) {
    return;
  }

  if (raw != stableButtonState) {
    stableButtonState = raw;
    if (stableButtonState == LOW) {
      Serial.println("Button pressed: START");
      sendStartUdp();
#if WAKE_PRINTER_ON_BUTTON
      requestPrinterWake();
#endif
    }
  }
}

void sendStartUdp() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Cannot send START; Wi-Fi is not connected");
    return;
  }

  IPAddress target;
  if (!target.fromString(TOUCHDESIGNER_UDP_HOST) && WiFi.hostByName(TOUCHDESIGNER_UDP_HOST, target) != 1) {
    Serial.printf("Cannot resolve UDP host: %s\n", TOUCHDESIGNER_UDP_HOST);
    return;
  }

  udp.beginPacket(target, TOUCHDESIGNER_UDP_PORT);
  udp.print(BUTTON_UDP_MESSAGE);
  udp.endPacket();
  Serial.printf("UDP sent to %s:%d: %s\n", target.toString().c_str(), TOUCHDESIGNER_UDP_PORT, BUTTON_UDP_MESSAGE);
}

void requestPrinterWake() {
  wakeRequested = true;
}

void processWakeRequest() {
  if (!wakeRequested) {
    return;
  }
  const uint32_t now = millis();
  if (now - lastWakeAttemptMs < PRINTER_CONNECT_RETRY_MS) {
    return;
  }
  lastWakeAttemptMs = now;
  wakeRequested = false;

  Serial.println("Attempting printer wake");
  const uint8_t initCommand[] = {0x1B, 0x40};
  if (connectPrinter() && printerWrite(initCommand, sizeof(initCommand))) {
    Serial.println("Printer wake command sent");
  } else {
    Serial.println("Printer wake failed; will retry on next request");
  }
}

bool printReceipt(JsonDocument& doc, String& error) {
  if (!connectPrinter()) {
    error = "printer not connected";
    return false;
  }

  const String sessionId = cleanText(doc["session_id"] | "");
  const String markName = cleanText(doc["mark_name"] | "");
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

  printerWrite(initCommand, sizeof(initCommand));
  printerWrite(alignCenter, sizeof(alignCenter));
  printerWrite(boldOn, sizeof(boldOn));
  printLine("THE ORACLE SPEAKS");
  printerWrite(boldOff, sizeof(boldOff));
  printLine("------------------------------");

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
  printLine("Session: " + sessionId);
  printLine("Symbol: " + markName);
  printLine("");
  printWrapped(oracleText);
  printLine("");
  printWrapped("Themes: " + themes);

  if (intensity.length() || instability.length() || confidence.length()) {
    printLine("");
    printLine("Voice measures:");
    if (intensity.length()) printLine("Intensity: " + intensity);
    if (instability.length()) printLine("Instability: " + instability);
    if (confidence.length()) printLine("Confidence: " + confidence);
  }

  if (sessionUrl.length()) {
    printLine("");
    printLine("Open your mark:");
    printerWrite(alignCenter, sizeof(alignCenter));
    printQr(sessionUrl);
    printerWrite(alignLeft, sizeof(alignLeft));
    printWrapped(sessionUrl);
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
  const size_t encodedLen = strlen(encoded);
  const size_t maxDecodedLen = (encodedLen * 3) / 4 + 4;
  uint8_t* decoded = static_cast<uint8_t*>(malloc(maxDecodedLen));
  if (!decoded) {
    error = "not enough memory for symbol bitmap";
    return false;
  }

  size_t decodedLen = 0;
  const int rc = mbedtls_base64_decode(decoded, maxDecodedLen, &decodedLen, reinterpret_cast<const unsigned char*>(encoded), encodedLen);
  if (rc != 0) {
    free(decoded);
    error = "invalid symbol_escpos_base64";
    return false;
  }

  const bool ok = printerWrite(decoded, decodedLen);
  free(decoded);
  if (!ok) {
    error = "failed to write symbol bitmap";
  }
  return ok;
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

  Serial.println("BLE printer connected");
  return true;
#endif
}

bool printerWrite(const uint8_t* data, size_t len) {
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
    const size_t written = SerialBT.write(data + offset, chunk);
    if (written != chunk) {
      return false;
    }
#else
    if (!printerChar || !printerChar->writeValue(data + offset, chunk, false)) {
      return false;
    }
#endif
    offset += chunk;
    delay(5);
  }
  return true;
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
  (void)data;
  (void)len;
  (void)withResponse;
  return false;
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

  printerChar = selectedChar;
  size_t offset = 0;
  while (offset < len) {
    const size_t chunk = min(static_cast<size_t>(PRINTER_WRITE_CHUNK_SIZE), len - offset);
    if (!printerChar->writeValue(data + offset, chunk, withResponse)) {
      return false;
    }
    offset += chunk;
    delay(withResponse ? 20 : 10);
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
