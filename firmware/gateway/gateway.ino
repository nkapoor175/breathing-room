// Breathing Room gateway (A08). Plugged into the laptop by USB; act/serial_bridge.py
// connects it to MQTT.
//  - prints every ESP-NOW message it hears as one line on serial
//  - sends every line it reads from serial to the device named in its "to" field
// Arduino IDE 2, esp32 board package 3.x. (Core 2.x: the receive callback is
// onRecv(const uint8_t* mac, const uint8_t* data, int len).)
//
// Steps: 1) flash this, open Serial Monitor at 115200, copy the "GATEWAY MAC" line
// into firmware/common/espnow_msg.h and send it to Shirali (her buttons send to it).
// 2) flash gate_sign, copy its MAC into PEERS below, flash this again.
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

struct Peer { const char* name; uint8_t mac[6]; };
Peer PEERS[] = {
  {"gate-3", {0x24, 0x6F, 0x28, 0x00, 0x00, 0x01}},   // <- the gate sign's MAC goes here
};

void onRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  Serial.write(data, len);
  Serial.write('\n');
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);   // every board uses channel 1
  if (esp_now_init() != ESP_OK) { Serial.println("ESP-NOW init failed"); return; }
  Serial.print("GATEWAY MAC: "); Serial.println(WiFi.macAddress());   // after init, so it isn't zeros
  esp_now_register_recv_cb(onRecv);
  for (auto& p : PEERS) {
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, p.mac, 6);
    peer.channel = 1; peer.encrypt = false;
    esp_now_add_peer(&peer);
  }
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  for (auto& p : PEERS) {
    if (line.indexOf(String("\"to\": \"") + p.name + "\"") >= 0 ||
        line.indexOf(String("\"to\":\"") + p.name + "\"") >= 0) {
      esp_now_send(p.mac, (const uint8_t*)line.c_str(), line.length());
    }
  }
}
