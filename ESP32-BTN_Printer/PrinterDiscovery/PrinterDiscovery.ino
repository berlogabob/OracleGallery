#include <Arduino.h>
#include <NimBLEDevice.h>

// Edit these before upload if the printer advertises under another name.
#define DISCOVERY_SCAN_SECONDS 10
#define DISCOVERY_NAME_FILTER "9509"
#define DISCOVERY_CONNECT_TO_MATCHES 1

bool matchesFilter(const NimBLEAdvertisedDevice* device);
void printAdvertisement(const NimBLEAdvertisedDevice* device, int index);
String printableName(const NimBLEAdvertisedDevice* device);
void printAdvertisedServices(const NimBLEAdvertisedDevice* device);
void inspectDevice(const NimBLEAdvertisedDevice* device);
void printCharacteristicProperties(const NimBLERemoteCharacteristic* chr);

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("Oracle printer BLE discovery");
  Serial.println("Turn the WP9509 on, keep it near the ESP32, then reset this board.");
  Serial.println();

  NimBLEDevice::init("OraclePrinterDiscovery");
  NimBLEDevice::setPower(3);

  NimBLEScan* scan = NimBLEDevice::getScan();
  scan->setActiveScan(true);
  scan->setInterval(100);
  scan->setWindow(100);

  Serial.printf("Scanning for %d second(s)...\n", DISCOVERY_SCAN_SECONDS);
  NimBLEScanResults results = scan->getResults(DISCOVERY_SCAN_SECONDS * 1000);
  Serial.printf("Found %d BLE device(s)\n\n", results.getCount());

  for (int i = 0; i < results.getCount(); i++) {
    const NimBLEAdvertisedDevice* device = results.getDevice(i);
    printAdvertisement(device, i);
    if (DISCOVERY_CONNECT_TO_MATCHES && matchesFilter(device)) {
      inspectDevice(device);
    }
    Serial.println();
  }

  Serial.println("Discovery complete. Copy the printer address, service UUID, and writable characteristic UUID into config.local.h.");
}

void loop() {
  delay(1000);
}

bool matchesFilter(const NimBLEAdvertisedDevice* device) {
  const String filter = String(DISCOVERY_NAME_FILTER);
  if (!filter.length()) {
    return true;
  }

  String name = printableName(device);
  String address = String(device->getAddress().toString().c_str());
  name.toLowerCase();
  address.toLowerCase();

  String wanted = filter;
  wanted.toLowerCase();
  return name.indexOf(wanted) >= 0 || address.indexOf(wanted) >= 0;
}

void printAdvertisement(const NimBLEAdvertisedDevice* device, int index) {
  Serial.printf("[%d] name='%s' address=%s rssi=%d\n",
                index,
                printableName(device).c_str(),
                device->getAddress().toString().c_str(),
                device->getRSSI());
  printAdvertisedServices(device);
}

String printableName(const NimBLEAdvertisedDevice* device) {
  String raw = String(device->getName().c_str());
  String safe;
  safe.reserve(raw.length());
  for (size_t i = 0; i < raw.length(); i++) {
    const char c = raw.charAt(i);
    safe += (c >= 32 && c <= 126) ? c : '?';
  }
  if (!safe.length()) {
    safe = "(no name)";
  }
  return safe;
}

void printAdvertisedServices(const NimBLEAdvertisedDevice* device) {
  bool printedAny = false;

  if (device->haveServiceUUID()) {
    Serial.print("    advertised service: ");
    Serial.println(device->getServiceUUID().toString().c_str());
    printedAny = true;
  }

  if (device->haveServiceData()) {
    Serial.print("    service data UUID: ");
    Serial.println(device->getServiceDataUUID().toString().c_str());
    printedAny = true;
  }

  if (!printedAny) {
    Serial.println("    no advertised service UUID");
  }
}

void inspectDevice(const NimBLEAdvertisedDevice* device) {
  Serial.println("    connecting for GATT service discovery...");
  NimBLEClient* client = NimBLEDevice::createClient();
  if (!client) {
    Serial.println("    could not create BLE client");
    return;
  }
  client->setConnectTimeout(5 * 1000);

  if (!client->connect(device)) {
    Serial.println("    connect failed");
    NimBLEDevice::deleteClient(client);
    return;
  }

  const std::vector<NimBLERemoteService*>& services = client->getServices(true);
  Serial.printf("    services: %u\n", static_cast<unsigned>(services.size()));
  for (NimBLERemoteService* service : services) {
    Serial.printf("    service %s\n", service->getUUID().toString().c_str());
    const std::vector<NimBLERemoteCharacteristic*>& chars = service->getCharacteristics(true);
    for (NimBLERemoteCharacteristic* chr : chars) {
      Serial.printf("      characteristic %s ", chr->getUUID().toString().c_str());
      printCharacteristicProperties(chr);
      Serial.println();
    }
  }

  client->disconnect();
  NimBLEDevice::deleteClient(client);
}

void printCharacteristicProperties(const NimBLERemoteCharacteristic* chr) {
  Serial.print("[");
  bool printed = false;
  if (chr->canRead()) {
    Serial.print("read");
    printed = true;
  }
  if (chr->canWrite()) {
    if (printed) Serial.print(",");
    Serial.print("write");
    printed = true;
  }
  if (chr->canWriteNoResponse()) {
    if (printed) Serial.print(",");
    Serial.print("write-no-response");
    printed = true;
  }
  if (chr->canNotify()) {
    if (printed) Serial.print(",");
    Serial.print("notify");
    printed = true;
  }
  if (chr->canIndicate()) {
    if (printed) Serial.print(",");
    Serial.print("indicate");
    printed = true;
  }
  if (!printed) {
    Serial.print("no-common-properties");
  }
  Serial.print("]");
}
