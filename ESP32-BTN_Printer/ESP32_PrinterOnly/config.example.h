#pragma once

// Copy this file to config.local.h and edit the values for the real setup.
// config.local.h is ignored by git so Wi-Fi credentials stay local.

#define WIFI_SSID "Nothing32"
#define WIFI_PASSWORD "CHANGE_ME_IN_CONFIG_LOCAL_H"
#define WIFI_CONNECT_TIMEOUT_MS 20000

#define SERIAL_BAUD 115200
#define SERIAL_STARTUP_DELAY_MS 1500

#define HTTP_PORT 80

// BLE is the default because the WP9509 advertises an app-oriented BLE service.
#define USE_CLASSIC_SPP 0

// Fill these from the PrinterDiscovery sketch output.
#define PRINTER_NAME_PREFIX "9509"
#define PRINTER_BLE_ADDRESS "95:09:25:47:56:b3"
#define PRINTER_SERVICE_UUID "0000fff0-0000-1000-8000-00805f9b34fb"
#define PRINTER_WRITE_CHAR_UUID "0000fff1-0000-1000-8000-00805f9b34fb"
#define PRINTER_ALT_WRITE_CHAR_UUID "0000fff2-0000-1000-8000-00805f9b34fb"
#define PRINTER_NOTIFY_CHAR_UUID "0000fff4-0000-1000-8000-00805f9b34fb"
#define PRINTER_BLE_SCAN_SECONDS 5

// Use this only if PrinterDiscovery or phone tests prove the printer is
// Bluetooth Classic SPP rather than BLE.
#define PRINTER_CLASSIC_NAME "WP9509"
#define PRINTER_CLASSIC_MAC ""

// Default protocol for /test-print and /print.
// WP9509 with iLabel app firmware prints through the proprietary iLabel raster path.
#define PRINTER_DEFAULT_PROTOCOL "ilabel"

#define PRINTER_CONNECT_RETRY_MS 5000
#define PRINTER_WRITE_CHUNK_SIZE 20
#define PRINTER_CHUNK_DELAY_MS 10
#define PRINTER_RESPONSE_CHUNK_DELAY_MS 20
#define BLE_NOTIFY_HEX_LIMIT 512

// 40 rows is about 5 mm at 200 DPI. The trailing margin is doubled so the
// receipt advances far enough beyond the tear edge.
#define ILABEL_MARGIN_ROWS 40
#define ILABEL_TRAILING_MARGIN_ROWS 80

// Print one short iLabel text receipt after each ESP32 cold boot/reset.
#define BOOT_TEST_PRINT_ENABLED 1
#define BOOT_TEST_PRINT_DELAY_MS 5000
#define BOOT_TEST_PRINT_RETRY_MS 10000
#define BOOT_TEST_PRINT_MAX_ATTEMPTS 6
#define BOOT_TEST_PRINT_MESSAGE "ORACLE PRINTER READY"

#define STATUS_LED_PIN 2
#define ENABLE_STATUS_LED 1
