// Breathing Room gate sign (A08): 4 LEDs behind printed paper signs.
//   green = go (value "up"), red = stop, yellow left / yellow right = arrows,
//   "clear" = all off, cmd "blink" = flash the chosen LED.
// Receives {"to":"gate-3","cmd":"arrow","value":"stop"} from the gateway over ESP-NOW.
// Keeps showing the last command if the internet or the laptop goes away.
// Wiring: each LED long leg -> GPIO through a 220-330 ohm resistor, short leg -> GND.
// Arduino IDE 2, esp32 board package 3.x.
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

const char* NODE = "gate-3";
const int GREEN = 25, RED = 26, LEFT = 27, RIGHT = 14;
const int PINS[] = {GREEN, RED, LEFT, RIGHT};
volatile int blinkPin = -1;

void allOff() { for (int p : PINS) digitalWrite(p, LOW); }

void show(const String& msg) {
  if (msg.indexOf(String("\"") + NODE + "\"") < 0) return;   // not for this sign
  int pin = -1;
  if (msg.indexOf("\"stop\"") >= 0) pin = RED;
  else if (msg.indexOf("\"up\"") >= 0) pin = GREEN;
  else if (msg.indexOf("\"left\"") >= 0) pin = LEFT;
  else if (msg.indexOf("\"right\"") >= 0) pin = RIGHT;
  allOff();
  blinkPin = (msg.indexOf("\"blink\"") >= 0) ? pin : -1;
  if (pin >= 0) digitalWrite(pin, HIGH);                    // "clear" leaves all off
  Serial.printf("sign: %s -> pin %d%s\n", msg.c_str(), pin, blinkPin >= 0 ? " (blink)" : "");
}

void onRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  show(String((const char*)data).substring(0, len));
}

void setup() {
  Serial.begin(115200);
  for (int p : PINS) pinMode(p, OUTPUT);
  for (int p : PINS) { digitalWrite(p, HIGH); delay(150); digitalWrite(p, LOW); }   // power-on check
  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) { Serial.println("ESP-NOW init failed"); return; }
  Serial.print("GATE SIGN MAC: "); Serial.println(WiFi.macAddress());   // copy into gateway PEERS
  esp_now_register_recv_cb(onRecv);
  digitalWrite(GREEN, HIGH);                                // start as "go"
}

void loop() {
  if (blinkPin >= 0) { digitalWrite(blinkPin, !digitalRead(blinkPin)); delay(300); }
}
