"""Serial bridge with a simulated serial port (pyserial loop://) and a fake MQTT."""
import serial

from act.serial_bridge import Bridge, parse_line


def test_parse_button_lines():
    r = parse_line('{"node":"vol-2","zone":"B","event":"pushing"}')
    assert (r.source, r.node, r.zone, r.severity, r.text) == ("volunteer_button", "vol-2", "B", 4, "pushing here")
    assert parse_line('{"node":"vol-1","zone":"C","event":"fell"}').severity == 5
    assert parse_line('{"node":"vol-2","hb":1}') is None
    assert parse_line("GATEWAY MAC: 24:6F:28:00:00:00") is None
    assert parse_line('{"broken') is None


class FakeMQTT:
    def __init__(self):
        self.up, self.sent = True, []

    def __call__(self, topic, msg):
        if self.up:
            self.sent.append((topic, msg))
        return self.up


def test_button_press_reaches_mqtt_through_the_port():
    ser = serial.serial_for_url("loop://", timeout=0.1)
    mq = FakeMQTT()
    b = Bridge(ser, mq, log=lambda s: None)
    ser.write(b'{"node":"vol-2","zone":"B","event":"fell"}\n')
    b.step()
    (topic, r), = mq.sent
    assert topic == "br/report" and r.severity == 5 and r.zone == "B"


def test_reports_buffered_while_offline_then_sent_in_order():
    ser = serial.serial_for_url("loop://", timeout=0.1)
    mq = FakeMQTT()
    mq.up = False
    b = Bridge(ser, mq, log=lambda s: None)
    b.handle_line('{"node":"vol-1","zone":"A","event":"pushing"}')
    b.handle_line('{"node":"vol-2","zone":"B","event":"fell"}')
    assert mq.sent == [] and len(b.pending) == 2
    mq.up = True
    b.flush()
    assert [r.node for _, r in mq.sent] == ["vol-1", "vol-2"] and not b.pending


def test_gate_command_goes_to_radio_and_heartbeat_counted():
    ser = serial.serial_for_url("loop://", timeout=0.1)
    b = Bridge(ser, FakeMQTT(), log=lambda s: None)
    b.to_radio(b'{"to": "gate-3", "cmd": "arrow", "value": "stop"}')
    assert ser.readline() == b'{"to": "gate-3", "cmd": "arrow", "value": "stop"}\n'
    b.handle_line('{"node":"vol-2","hb":1}')
    assert "vol-2" in b.heartbeats
