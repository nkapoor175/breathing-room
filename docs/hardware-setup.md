# Hardware setup: gateway + gate sign (step by step)

Goal: two ESP32 boards. The **gate sign** lights a red / green / yellow LED when told to. The **gateway** is plugged into the laptop and passes commands to the gate sign by radio (ESP-NOW, no Wi-Fi router needed). At the end you type one line on the laptop and the red LED turns on.

Time: about 40 minutes the first time.

---

## 0. What you need

| Thing | How many | Notes |
|---|---|---|
| ESP32 dev board | 2 | Classic "ESP32 DevKit / ESP32-WROOM-32" (30 or 38 pins). **If yours says ESP32-S3 or ESP32-C3, stop and tell Navika**: the pin numbers below are different. |
| USB cable | 2 | Must be a **data** cable. Many cables only charge. If the board never shows up as a COM port, try another cable first. |
| LED | 4 | 1 green, 1 red, 2 yellow |
| Resistor 220 Ω to 330 Ω | 4 | One per LED. Without it the LED or the pin can burn out. |
| Breadboard | 1 | |
| Jumper wires | ~10 | Male-to-male if the ESP32 sits on the breadboard |
| Laptop | 1 | Windows is fine |
| Paper + tape (optional) | | Draw a STOP sign, a GO arrow, left/right arrows and tape them over the LEDs so they read on camera |

---

## 1. Install the software (10 min, once)

1. Download **Arduino IDE 2** from https://www.arduino.cc/en/software and install it (all defaults).
2. Open Arduino IDE.
3. Go to **File → Preferences**. In **Additional boards manager URLs** paste:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
   Click **OK**.
4. Go to **Tools → Board → Boards Manager…** (or the board icon on the left).
5. Search **esp32**. Find **"esp32 by Espressif Systems"**. In the version dropdown pick a **3.x** version (e.g. 3.0.x or newer). Click **Install**. It takes a few minutes.
6. **USB driver check:** plug in one ESP32. Open Windows **Device Manager → Ports (COM & LPT)**.
   - If you see something like **"Silicon Labs CP210x … (COM5)"** or **"USB-SERIAL CH340 (COM7)"**: good, note the COM number.
   - If nothing new appears or there's a yellow warning: install the driver for the chip printed on the board near the USB port.
     - CP2102: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers
     - CH340: search "CH340 driver Windows" (from wch.cn)
     Then unplug and replug.

---

## 2. Get the code

- If you have the repo: the files are `firmware/gate_sign/gate_sign.ino` and `firmware/gateway/gateway.ino`.
- If not: go to https://github.com/nkapoor175/breathing-room → green **Code** button → **Download ZIP** → unzip. The files are in the same folders.

Arduino wants each sketch in a folder with the same name (`gate_sign/gate_sign.ino`): that's already how they're stored, so just **File → Open…** the `.ino` file.

---

## 3. Wire the gate sign (10 min). Board unplugged while wiring!

Put ESP32 #1 across the middle gap of the breadboard so each side's pins are in separate rows.

For **each** LED, the path is:

```
ESP32 GPIO pin ──► resistor ──► LED long leg (+)    LED short leg (–) ──► GND
```

| LED | ESP32 pin label | Paper sign on top |
|---|---|---|
| Green | **D25** / **GPIO25** | GO / ↑ |
| Red | **D26** / **GPIO26** | STOP |
| Yellow #1 | **D27** / **GPIO27** | ← LEFT |
| Yellow #2 | **D14** / **GPIO14** | RIGHT → |

How to do it on a breadboard:
1. Find a pin marked **GND** on the ESP32. Run a jumper from it to the breadboard's long **blue (–) rail**. That's your ground line.
2. For the green LED: put the LED's **long leg** in an empty row, the **short leg** in the next row.
3. Put one end of a resistor in the long-leg row, the other end in a new empty row.
4. Jumper from **D25** to that resistor row.
5. Jumper from the **short-leg** row to the **blue (–) rail**.
6. Repeat for red (D26), yellow (D27), yellow (D14).

**LED direction matters.** Long leg = + (towards the pin). Short leg / flat edge of the rim = – (towards GND). If an LED never lights later, flip it.

---

## 4. Flash the gate sign and get its MAC (5 min)

1. Plug ESP32 #1 (the one with LEDs) into the laptop.
2. Open `firmware/gate_sign/gate_sign.ino` in Arduino IDE.
3. **Tools → Board → esp32 → "ESP32 Dev Module"**.
4. **Tools → Port →** the COM port you saw in Device Manager.
5. Click **Upload** (the → arrow, top left).
   - If it sits on `Connecting........` : press and **hold the BOOT button** on the board until the percentage starts, then let go.
   - "Failed to connect / port busy": close any open Serial Monitor and try again; try another cable.
6. When it says **"Done uploading"** / "Hard resetting":
   - The 4 LEDs should flash **one after another**, then **green stays on**. That's the power-on check: wiring works.
   - Any LED that didn't flash: check it's the right way round and in the right pin.
7. Open **Tools → Serial Monitor**. Bottom right set **115200 baud**. Press the board's **EN** (or RST) button once.
8. You'll see a line like:
   `GATE SIGN MAC: 24:6F:28:AB:CD:EF`
   **Copy it** and send it to the team chat.
9. Close the Serial Monitor. Unplug board #1 and **power it from any USB charger / power bank** (it just needs power now) or leave it plugged in.

---

## 5. Put the gate sign's MAC into the gateway sketch (2 min)

1. Open `firmware/gateway/gateway.ino`.
2. Find this line near the top:
   ```cpp
   {"gate-3", {0x24, 0x6F, 0x28, 0x00, 0x00, 0x01}},   // <- the gate sign's MAC goes here
   ```
3. Replace the six numbers with the gate sign's MAC, each part with `0x` in front.
   Example: MAC `24:6F:28:AB:CD:EF` becomes
   ```cpp
   {"gate-3", {0x24, 0x6F, 0x28, 0xAB, 0xCD, 0xEF}},
   ```
4. **File → Save**.

---

## 6. Flash the gateway and get its MAC (5 min)

1. Plug ESP32 #2 (no LEDs, nothing wired) into the laptop.
2. **Tools → Port →** its COM port (a different number from board #1).
3. Board is still "ESP32 Dev Module". Click **Upload** (hold BOOT if it's stuck on Connecting).
4. Open **Serial Monitor**, **115200**, press **EN**.
5. You'll see `GATEWAY MAC: XX:XX:XX:XX:XX:XX`. **Send it to the team chat.** Shirali's volunteer buttons need it, and Navika puts it in `firmware/common/espnow_msg.h`.

---

## 7. Test it yourself, no laptop software needed (2 min)

Keep the gateway's Serial Monitor open.

1. At the bottom of the Serial Monitor, set the line-ending dropdown to **"Newline"**.
2. Type this exactly into the message box and press **Enter**:
   ```
   {"to":"gate-3","cmd":"arrow","value":"stop"}
   ```
   → the **red** LED on the gate sign turns on.
3. Try the others:
   ```
   {"to":"gate-3","cmd":"arrow","value":"up"}
   {"to":"gate-3","cmd":"arrow","value":"left"}
   {"to":"gate-3","cmd":"arrow","value":"right"}
   {"to":"gate-3","cmd":"blink","value":"stop"}
   {"to":"gate-3","cmd":"arrow","value":"clear"}
   ```
   up = green, left/right = yellow, blink = flashing red, clear = all off.

**If nothing happens:**
- Did you re-upload the gateway **after** putting the gate sign's MAC in (step 5)?
- Is the gate sign powered (green LED on)?
- Check the MAC numbers again, a single wrong digit breaks it.
- Open the gate sign's Serial Monitor instead (if it's on the laptop): it prints `sign: … -> pin 26` when a message arrives. Nothing printed = the radio message didn't arrive (MAC or power); something printed but no light = wiring.
- Boards closer together (same table) while testing.

**When step 7 works: hardware done.** 🎉

---

## 8. Connect it to the system (Navika does this, 2 min)

1. **Close the Arduino Serial Monitor** (only one program can use the COM port).
2. In the repo's `.env` set `GATEWAY_PORT=COMx` (the gateway's COM number).
3. Run the demo (`.venv\Scripts\python scripts\demo.py`) and in another terminal:
   ```
   .venv\Scripts\python -m act.serial_bridge
   ```
4. When a plan closes gate G3 and the operator clicks **Approve** on the dashboard, the gate sign turns red.

---

## Quick reference

| Command `value` | LED |
|---|---|
| `stop` | red |
| `up` | green (go) |
| `left` | yellow on D27 |
| `right` | yellow on D14 |
| `clear` | all off |
| `cmd: "blink"` + any value | that LED flashes |

Settings: board **ESP32 Dev Module**, esp32 package **3.x**, Serial Monitor **115200**, line ending **Newline**, Wi-Fi channel **1** (set in code, nothing to do).
