// Shared ESP-NOW constants for every Breathing Room board (spec Section 7.5).
#pragma once
#include <stdint.h>

// All boards: Wi-Fi channel 1, station mode, never connected to a router.
#define BR_ESPNOW_CHANNEL 1

// Messages are compact JSON strings under 200 bytes (ESP-NOW max payload is 250).
#define BR_MAX_MSG 200

// Heartbeat interval for every device -> gateway: {"node":"vol-2","hb":1}
#define BR_HEARTBEAT_MS 10000

// Gateway ESP32 MAC. Placeholder until Navika flashes the gateway and posts the real one.
static const uint8_t BR_GATEWAY_MAC[6] = {0x24, 0x6F, 0x28, 0x00, 0x00, 0x00};
