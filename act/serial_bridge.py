"""Serial bridge (A08): gateway ESP32 on USB <-> MQTT.

The gateway prints every ESP-NOW message it hears as one JSON line on serial, and
sends every line it reads from serial over ESP-NOW to the device named in "to".

  serial -> MQTT:  {"node","zone","event":"pushing"|"fell"}  -> Report on br/report
                   (pushing = severity 4 "pushing here", fell = severity 5 "someone fell")
                   {"node","hb":1}                           -> heartbeat, counted only
  MQTT -> serial:  br/device/<node> DeviceCommand            -> one line to the gateway

If the internet (MQTT) is down, button reports are kept in a buffer and sent when it
comes back (golden-path step 9); gate commands still reach the signs because the
radio mesh doesn't need the internet.

Run:  python -m act.serial_bridge            (GATEWAY_PORT in .env, e.g. COM5)
Find the port: Arduino IDE -> Tools -> Port, or Device Manager -> Ports (COM & LPT).
"""
import json, os, threading, time
from collections import deque
from typing import Callable, Optional

from common.contracts import Report
from common.timeutil import now_iso

EVENTS = {"pushing": (4, "pushing here"), "fell": (5, "someone fell")}


def parse_line(line: str) -> Optional[Report]:
    """One serial line -> Report for a button press, None for anything else."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        m = json.loads(line)
    except json.JSONDecodeError:
        return None
    if m.get("event") not in EVENTS:
        return None
    sev, text = EVENTS[m["event"]]
    return Report(t=now_iso(), source="volunteer_button", node=m.get("node"), zone=m.get("zone"),
                  text=text, severity=sev)


class Bridge:
    def __init__(self, ser, publish: Callable[[str, object], bool], log: Callable[[str], None] = print):
        """publish(topic, msg) returns True if the message left (MQTT connected)."""
        self.ser = ser
        self.publish = publish
        self.log = log
        self.pending: deque[Report] = deque(maxlen=500)
        self.heartbeats: dict[str, float] = {}
        self.lock = threading.Lock()

    def to_radio(self, payload: bytes):
        """br/device/<node> message from MQTT -> one line to the gateway."""
        line = payload.decode(errors="ignore").strip()
        if line.startswith("{") and len(line) < 200:
            with self.lock:
                self.ser.write((line + "\n").encode())
            self.log(f"bridge: -> radio {line}")

    def flush(self):
        while self.pending:
            if not self.publish("br/report", self.pending[0]):
                return
            self.pending.popleft()

    def handle_line(self, line: str):
        r = parse_line(line)
        if r:
            self.pending.append(r)
            self.log(f"bridge: button {r.node} zone {r.zone}: {r.text}")
            self.flush()
            if self.pending:
                self.log(f"bridge: MQTT down, {len(self.pending)} report(s) buffered")
            return
        try:
            m = json.loads(line)
            if "hb" in m and m.get("node"):
                self.heartbeats[m["node"]] = time.time()
        except (json.JSONDecodeError, TypeError):
            if line.strip():
                self.log(f"gateway: {line.strip()}")      # e.g. "GATEWAY MAC: ..."

    def step(self):
        raw = self.ser.readline()
        if raw:
            self.handle_line(raw.decode(errors="ignore"))
        elif self.pending:
            self.flush()


def main():
    import serial
    from common.bus import make_client, publish

    port = os.environ.get("GATEWAY_PORT", "COM5")
    ser = serial.Serial(port, 115200, timeout=0.1)
    mq = make_client("act-serial-bridge")
    bridge = Bridge(ser, lambda t, m: mq.is_connected() and publish(mq, t, m).rc == 0)
    mq.on_connect = lambda c, u, f, rc, p: (c.subscribe("br/device/#"), bridge.flush())
    mq.on_message = lambda c, u, m: bridge.to_radio(m.payload)
    mq.loop_start()
    print(f"bridge: gateway on {port}, MQTT {os.environ.get('MQTT_HOST')}")
    while True:
        bridge.step()


if __name__ == "__main__":
    main()
